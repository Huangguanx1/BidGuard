"""Durable fixed review workflow. Only IDs are stored in graph state."""
import json
import threading
from datetime import UTC, datetime
from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .model import ModelError, extract_requirements, match_requirements, review_prompt_hash
from .rules import run_consistency_rules
from .schemas import Evidence, FindingDraft


def now():
    return datetime.now(UTC).isoformat()


class State(TypedDict):
    review_id: str


def evidence(block, role):
    return Evidence(block_id=block.id, page_number=block.page_number, excerpt=block.content[:500],
                    document_role=role, location_confidence=block.location_confidence)


def requirement_findings(requirements, checks):
    by_id = {item.id: item for item in requirements}
    findings = []
    for check in checks:
        if check.match_status == 'satisfied':
            continue
        requirement = by_id[check.requirement_id]
        high = requirement.category in ('qualification', 'disqualification') and requirement.mandatory and check.match_status in ('not_found', 'not_satisfied')
        risk = 'high' if high else 'medium' if requirement.mandatory or requirement.category == 'scoring' else 'low'
        findings.append(FindingDraft(type='requirement_risk', category=requirement.category,
            requirement_check_id=check.id, risk_level=risk, title=requirement.title,
            description=check.reason, suggestion='对照招标原文补充或修正投标响应，并由人工核实。',
            evidence=check.tender_evidence + check.bid_evidence, confidence=check.confidence))
    return findings


class ReviewWorkflow:
    def __init__(self, database, settings):
        self.db, self.settings = database, settings
        self.queue = threading.Semaphore(1)
        self.lock = threading.RLock()

    def graph(self, saver):
        graph = StateGraph(State)
        for name, node in [('validate', self.validate), ('extract', self.extract), ('match', self.match),
                           ('findings', self.findings), ('human', self.human), ('freeze', self.freeze)]:
            graph.add_node(name, node)
        for start, end in zip([START, 'validate', 'extract', 'match', 'findings', 'human', 'freeze'],
                              ['validate', 'extract', 'match', 'findings', 'human', 'freeze', END]):
            graph.add_edge(start, end)
        return graph.compile(checkpointer=saver)

    def run(self, review_id):
        with self.queue:
            try:
                row = self.db.get_review(review_id)
                if row['status'] != 'queued':
                    return
                parameters = json.loads(row['model_parameters'])
                if (row['model_name'] != self.settings.model_name or row['model_base_url'] != self.settings.model_base_url
                    or row['model_provider'] != self.settings.model_provider or row['prompt_hash'] != review_prompt_hash()
                    or parameters.get('temperature') != self.settings.model_temperature
                    or parameters.get('batch_chars') != self.settings.model_batch_chars):
                    raise ModelError('模型配置已变化，请新建审查以保留准确的模型记录')
                with SqliteSaver.from_conn_string(str(self.settings.app_data_dir / 'checkpoints.db')) as saver:
                    graph = self.graph(saver)
                    config = {'configurable': {'thread_id': review_id}}
                    state = graph.get_state(config)
                    graph.invoke(None if state.values else {'review_id': review_id}, config)
                self.db.set_stage(review_id, 'human_review', 95, 'awaiting_review')
            except Exception as exc:
                message = str(exc) if isinstance(exc, ModelError) else '审查执行失败，已保留检查点，可重试'
                self.db.fail_review(review_id, message, now())

    def validate(self, state):
        rid = state['review_id']
        self.db.set_stage(rid, 'validating_documents', 5)
        row = self.db.get_review(rid)
        for key in ('tender_document_id', 'bid_document_id'):
            if not self.db.get_document(row[key]) or not self.db.get_all_blocks(row[key]):
                raise ModelError('文档或解析块不存在')
        return {}

    def extract(self, state):
        rid = state['review_id']
        self.db.set_stage(rid, 'extracting_requirements', 15)
        if self.db.list_requirements(rid):
            return {}
        blocks = self.db.get_all_blocks(self.db.get_review(rid)['tender_document_id'])
        mapping = {b.id: b for b in blocks}
        drafts, incoming, outgoing = extract_requirements(blocks, self.settings)
        rows = []
        for draft in drafts:
            sources = [mapping[key] for key in draft.source_block_ids]
            rows.append(dict(id=str(uuid4()), review_id=rid, **draft.model_dump(exclude={'source_block_ids', 'mandatory'}),
                source_block_ids=json.dumps(draft.source_block_ids), mandatory=int(draft.mandatory),
                sort_index=min(b.block_index for b in sources), source_excerpt='\n'.join(b.content for b in sources)[:1000]))
        self.db.complete_requirement_extraction(rid, rows, incoming, outgoing, now())
        return {}

    def match(self, state):
        rid = state['review_id']
        self.db.set_stage(rid, 'matching_responses', 45)
        if self.db.list_requirement_checks(rid):
            return {}
        row = self.db.get_review(rid)
        tender = {b.id: b for b in self.db.get_all_blocks(row['tender_document_id'])}
        requirements = self.db.list_requirements(rid)
        req_map = {r.id: r for r in requirements}
        matches, incoming, outgoing = match_requirements(requirements, self.db.get_all_blocks(row['bid_document_id']), self.settings)
        rows = []
        for match in matches:
            candidates = {b.id: b for b in match.candidates}
            req = req_map[match.draft.requirement_id]
            rows.append(dict(id=str(uuid4()), review_id=rid, requirement_id=req.id,
                match_status=match.draft.match_status, reason=match.draft.reason, confidence=match.draft.confidence,
                tender_evidence=json.dumps([evidence(tender[key], 'tender').model_dump() for key in req.source_block_ids], ensure_ascii=False),
                bid_evidence=json.dumps([evidence(candidates[key], 'bid').model_dump() for key in match.draft.bid_evidence_block_ids], ensure_ascii=False),
                searched_block_ids=json.dumps(list(candidates))))
        self.db.complete_requirement_matching(rid, rows, incoming, outgoing, now())
        return {}

    def findings(self, state):
        rid = state['review_id']
        self.db.set_stage(rid, 'checking_evidence', 80)
        row = self.db.get_review(rid)
        tender = self.db.get_all_blocks(row['tender_document_id'])
        bid = self.db.get_all_blocks(row['bid_document_id'])
        maps = {'tender': {b.id: b for b in tender}, 'bid': {b.id: b for b in bid}}
        checks = self.db.list_requirement_checks(rid)
        findings = run_consistency_rules(tender, bid)
        for risk in requirement_findings(self.db.list_requirements(rid), checks):
            # Merge a timeline finding only when both sides cite exactly the same
            # source blocks as a date/duration rule. The full check remains stored.
            duplicate = next((f for f in findings if risk.category == 'timeline' and f.category in ('date', 'duration')
                              and {e.block_id for e in f.evidence} == {e.block_id for e in risk.evidence}), None)
            if duplicate and duplicate.requirement_check_id is None:
                duplicate.requirement_check_id = risk.requirement_check_id
            else:
                findings.append(risk)
        for item in [e for check in checks for e in check.tender_evidence + check.bid_evidence] + [e for finding in findings for e in finding.evidence]:
            block = maps.get(item.document_role, {}).get(item.block_id)
            if not block or not item.page_number or item.page_number != block.page_number or item.excerpt not in block.content:
                raise ModelError('证据未通过原文或页码校验，请检查文档解析结果')
        rows = [dict(id=str(uuid4()), review_id=rid, **finding.model_dump(exclude={'evidence'}),
                     evidence=json.dumps([e.model_dump() for e in finding.evidence], ensure_ascii=False)) for finding in findings]
        self.db.complete_consistency_check(rid, rows, now())
        return {}

    def human(self, state):
        interrupt({'review_id': state['review_id'], 'action': 'human_review'})
        return {}

    def freeze(self, state):
        from .reports import build_snapshot
        self.db.freeze(state['review_id'], lambda: build_snapshot(self.db, state['review_id']))
        return {}

    def finalize(self, review_id):
        with self.lock:
            row = self.db.get_review(review_id)
            if row['status'] == 'completed':
                return
            if row['status'] != 'awaiting_review':
                raise ValueError('当前审查尚未进入人工复核')
            if any(f.review_status == 'pending' for f in self.db.list_findings(review_id)):
                raise ValueError('请先处理所有待确认问题')
            with SqliteSaver.from_conn_string(str(self.settings.app_data_dir / 'checkpoints.db')) as saver:
                graph = self.graph(saver)
                config = {'configurable': {'thread_id': review_id}}
                if graph.get_state(config).values:
                    graph.invoke(Command(resume=True), config)
                else:
                    self.freeze({'review_id': review_id})
