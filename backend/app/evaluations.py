"""Fixed fictional cases, with raw per-case outcomes and explicit metric scope."""
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from .config import ROOT_DIR
from .model import extract_requirements, match_requirements, REVIEW_PROMPT_VERSION, review_prompt_hash, ModelError
from .rules import run_consistency_rules
from .schemas import DocumentBlock, Requirement


class EvalRequest(BaseModel):
    with_model: bool = False
    external_processing_consent: bool = False


def stamp():
    return datetime.now(UTC).isoformat()


def blocks(lines, role):
    return [DocumentBlock(id=f'{role}-{i}', block_index=i, block_type='paragraph', heading_level=None,
                page_number=i + 1, location_confidence=1, section_path=None, content=line) for i, line in enumerate(lines)]


def execute_cases(settings, with_model, progress):
    cases = [json.loads(line) for line in (ROOT_DIR / 'evals/cases.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    results, labels = [], ['satisfied', 'partial', 'not_satisfied', 'not_found', 'uncertain']
    tp = fp = fn = recalled = expected_total = incoming = outgoing = 0
    pairs = []
    for case in cases:
        tender, bid = blocks(case['tender'], 'tender'), blocks(case['bid'], 'bid')
        observed = {f.category for f in run_consistency_rules(tender, bid)}
        expected = set(case['consistency'])
        tp += len(observed & expected); fp += len(observed - expected); fn += len(expected - observed)
        result = dict(case_id=case['id'], expected_consistency=sorted(expected), actual_consistency=sorted(observed),
                      passed=observed == expected, missing_requirements=[], matching=[], error=None, structured_output=None,
                      evidence_valid=None, severe_misses=[])
        if with_model:
            expected_total += len(case['requirements'])
            try:
                drafts, tokens_in, tokens_out = extract_requirements(tender, settings)
                incoming += tokens_in; outgoing += tokens_out
                requirements = [Requirement(**draft.model_dump(), id=str(uuid4()), review_id='evaluation', sort_index=i,
                    source_excerpt='\n'.join(b.content for b in tender if b.id in draft.source_block_ids)) for i, draft in enumerate(drafts)]
                matches, tokens_in, tokens_out = match_requirements(requirements, bid, settings)
                incoming += tokens_in; outgoing += tokens_out
                result['structured_output'] = True
                result['evidence_valid'] = all(set(r.source_block_ids) <= {b.id for b in tender} for r in requirements) and all(set(m.draft.bid_evidence_block_ids) <= {b.id for b in m.candidates} for m in matches)
                match_map = {m.draft.requirement_id: m.draft.match_status for m in matches}
                for expected_req in case['requirements']:
                    candidates = [r for r in requirements if f"tender-{expected_req['block']}" in r.source_block_ids and r.category == expected_req['category']]
                    recalled += bool(candidates)
                    # A fixed annotation represents the whole requirement in this source block.
                    # Multiple extracted atoms are scored conservatively, never by best match.
                    statuses = [match_map[r.id] for r in candidates]
                    predicted = statuses[0] if statuses and len(set(statuses)) == 1 else 'uncertain' if statuses else 'not_extracted'
                    pairs.append((expected_req['match'], predicted))
                    result['matching'].append(dict(expected=expected_req['match'], actual=predicted, category=expected_req['category']))
                    if not candidates:
                        result['missing_requirements'].append(expected_req)
                    if expected_req['category'] in ('qualification', 'disqualification') and expected_req['match'] != 'satisfied' and predicted in ('satisfied', 'not_extracted'):
                        result['severe_misses'].append(expected_req)
                    result['passed'] &= predicted == expected_req['match']
            except ModelError as exc:
                result.update(passed=False, error=str(exc), structured_output=False, evidence_valid=False)
                result['missing_requirements'] = case['requirements']
                result['severe_misses'] = [r for r in case['requirements'] if r['category'] in ('qualification', 'disqualification') and r['match'] != 'satisfied']
                pairs.extend((r['match'], 'not_extracted') for r in case['requirements'])
        results.append(result)
        progress(results)
    f1 = []
    for label in labels:
        correct = sum(a == label and b == label for a, b in pairs)
        denominator = sum(a == label for a, _ in pairs) + sum(b == label for _, b in pairs)
        f1.append(2 * correct / denominator if denominator else 0)
    return dict(results=results, metrics=dict(case_pass_rate=sum(r['passed'] for r in results) / len(results),
        consistency_precision=tp / (tp + fp) if tp + fp else 1, consistency_recall=tp / (tp + fn) if tp + fn else 1,
        requirement_recall=recalled / expected_total if with_model else None,
        matching_macro_f1=sum(f1) / len(f1) if with_model else None,
        structured_output_success=sum(r['structured_output'] is True for r in results) / len(results) if with_model else None,
        evidence_block_validity=sum(r['evidence_valid'] is True for r in results) / len(results) if with_model else None,
        severe_misses=sum(len(r['severe_misses']) for r in results) if with_model else None, page_accuracy=None),
        input_tokens=incoming, output_tokens=outgoing, estimated_cost=None,
        limitations='小型虚构文本块评测；不测 PDF/DOCX 页码准确率；要求召回按已标注源块和类别计；匹配按整条标注计，模型拆分原子要求可能降低得分。未配置单价，成本不估算。失败请求的供应商用量可能未计入。')


def create_eval_router(db, settings):
    router = APIRouter(prefix='/api')
    with db.connect() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS eval_runs (id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)')

    @router.on_event('startup')
    def recover():
        with db.connect() as conn:
            for row in conn.execute("SELECT * FROM eval_runs WHERE status='running'").fetchall():
                data = json.loads(row['payload'])
                data.update(status='failed', error='服务中断，请重新运行评测')
                conn.execute("UPDATE eval_runs SET status='failed', payload=? WHERE id=?", (json.dumps(data, ensure_ascii=False), row['id']))

    def save(data):
        with db.connect() as conn:
            conn.execute('UPDATE eval_runs SET status=?, payload=? WHERE id=?', (data['status'], json.dumps(data, ensure_ascii=False), data['id']))

    def run(data, with_model):
        started = time.monotonic()
        try:
            def progress(results):
                data['results'] = results
                save(data)
            data.update(execute_cases(settings, with_model, progress), status='completed')
        except Exception:
            data.update(status='failed', error='评测执行失败')
        data.update(completed_at=stamp(), duration_ms=round((time.monotonic() - started) * 1000))
        save(data)

    @router.post('/eval-runs', status_code=202)
    def create(body: EvalRequest, tasks: BackgroundTasks):
        if body.with_model and settings.model_provider != 'ollama' and not body.external_processing_consent:
            raise HTTPException(422, '请确认使用模型评测虚构样本')
        data = dict(id=str(uuid4()), status='running', created_at=stamp(), with_model=body.with_model,
                    model_name=settings.model_name if body.with_model else None, model_provider=settings.model_provider if body.with_model else None,
                    model_parameters={'temperature': settings.model_temperature, 'batch_chars': settings.model_batch_chars},
                    prompt_version=REVIEW_PROMPT_VERSION, prompt_hash=review_prompt_hash(),
                    dataset_version=hashlib.sha256((ROOT_DIR / 'evals/cases.jsonl').read_bytes()).hexdigest(), results=[])
        try:
            data['git_commit_sha'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT_DIR, timeout=5, stderr=subprocess.DEVNULL).decode().strip()
            data['working_tree_dirty'] = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT_DIR, timeout=5))
        except (OSError, subprocess.SubprocessError):
            data['git_commit_sha'] = None
        with db.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if conn.execute("SELECT 1 FROM eval_runs WHERE status='running'").fetchone():
                raise HTTPException(409, '已有评测正在运行')
            conn.execute('INSERT INTO eval_runs VALUES (?,?,?,?)', (data['id'], data['status'], data['created_at'], json.dumps(data, ensure_ascii=False)))
        tasks.add_task(run, data.copy(), body.with_model)
        return data

    @router.get('/eval-runs')
    def listing():
        with db.connect() as conn:
            return {'items': [json.loads(row['payload']) for row in conn.execute('SELECT payload FROM eval_runs ORDER BY created_at DESC LIMIT 50')]}

    @router.get('/eval-runs/{run_id}')
    def get(run_id: str):
        with db.connect() as conn:
            row = conn.execute('SELECT payload FROM eval_runs WHERE id=?', (run_id,)).fetchone()
        if not row:
            raise HTTPException(404, '评测不存在')
        return json.loads(row['payload'])
    return router
