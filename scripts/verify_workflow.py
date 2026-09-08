"""Offline integration check: no external model calls or user data changes."""
import json
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.schemas import RequirementDraft, RequirementMatchDraft, FindingUpdate, FindingOverride
from backend.app.model import ModelError, RequirementMatchResult
from backend.app.reports import report_bytes
import backend.app.workflow as module


def main():
    with tempfile.TemporaryDirectory() as directory:
        settings = Settings(_env_file=None, app_data_dir=Path(directory), model_base_url='http://localhost/v1', model_name='offline', model_api_key='fixture')
        db = Database(Path(directory) / 'test.db')
        for role, text in [('tender', '必须提供营业执照'), ('bid', '未提供营业执照')]:
            db.insert_document(dict(id=role, original_name=role+'.pdf', stored_path=role+'.pdf', sha256='fixture', file_type='pdf', file_size=10,
                page_count=1, text_char_count=len(text), parse_warnings='[]', heading_count=0, paragraph_count=1, table_count=0, created_at=module.now()),
                [dict(id=role+'-block', document_id=role, block_index=0, block_type='paragraph', heading_level=None, page_number=1, location_confidence=1,
                    section_path=None, content=text, search_text=text)])
        rid = str(uuid4())
        db.insert_review(dict(id=rid, name='离线恢复验证', tender_document_id='tender', bid_document_id='bid', model_provider='openai_compatible',
            model_base_url=settings.model_base_url, model_name=settings.model_name, prompt_version='fixture', prompt_hash=module.review_prompt_hash(),
            model_parameters=json.dumps({'temperature': settings.model_temperature, 'batch_chars': settings.model_batch_chars}), created_at=module.now()))
        calls = {'extract': 0, 'match': 0}
        def extract(*args):
            calls['extract'] += 1
            return [RequirementDraft(category='qualification', title='营业执照', description='必须提供营业执照', mandatory=True, source_block_ids=['tender-block'], confidence=.9)], 10, 5
        def match(requirements, bid, settings):
            calls['match'] += 1
            if calls['match'] == 1:
                raise ModelError('模拟进程中断后的匹配失败')
            return [RequirementMatchResult(draft=RequirementMatchDraft(requirement_id=requirements[0].id, match_status='not_satisfied',
                        reason='明确未提供', bid_evidence_block_ids=['bid-block'], confidence=.9), candidates=bid)], 20, 10
        module.extract_requirements, module.match_requirements = extract, match
        workflow = module.ReviewWorkflow(db, settings)
        workflow.run(rid)
        assert db.get_review(rid)['status'] == 'failed'
        assert len(db.list_requirements(rid)) == 1
        assert db.claim_retry(rid) and not db.claim_retry(rid)
        # A fresh workflow object simulates process restart with on-disk checkpoints.
        workflow = module.ReviewWorkflow(db, settings)
        workflow.run(rid)
        assert db.get_review(rid)['status'] == 'awaiting_review', db.get_review(rid)['error_message']
        assert calls == {'extract': 1, 'match': 2}, calls
        assert len(db.list_requirement_checks(rid)) == 1
        finding = db.list_findings(rid)[0]
        assert finding.type == 'requirement_risk' and finding.risk_level == 'high'
        try:
            workflow.finalize(rid)
            raise AssertionError('Pending finalization was accepted')
        except ValueError:
            pass
        db.update_finding(finding.id, FindingUpdate(review_status='ignored'))
        db.update_finding(finding.id, FindingUpdate(review_status='pending'))
        db.update_finding(finding.id, FindingUpdate(review_status='modified', reviewer_note='离线人工修改验证',
            override=FindingOverride(title='需补充执照', description='请补齐证明材料', risk_level='medium', suggestion='补交有效执照')))
        workflow.finalize(rid)
        row = db.get_review(rid)
        assert row['status'] == 'completed'
        frozen = json.loads(row['report_snapshot'])
        assert frozen['findings'][0]['effective']['risk_level'] == 'medium'
        assert frozen['findings'][0]['risk_level'] == 'high'
        assert frozen['summary']['high_risk_findings'] == 0
        assert row['input_tokens'] == 30 and row['output_tokens'] == 15
        assert not db.claim_retry(rid)
        try:
            db.update_finding(finding.id, FindingUpdate(review_status='ignored'))
            raise AssertionError('Frozen edit was accepted')
        except ValueError:
            pass
        workflow.finalize(rid)
        assert db.get_review(rid)['report_snapshot'] == row['report_snapshot']
        assert report_bytes(frozen, 'docx')[0] == report_bytes(frozen, 'docx')[0]
        assert report_bytes(frozen, 'json')[0] == report_bytes(frozen, 'json')[0]
        print('PASS: checkpoint recovery, duplicate retry rejection, risk matrix, pending gate, edits, freeze, deterministic reports')


if __name__ == '__main__':
    main()
