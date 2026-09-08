import json
from uuid import uuid4
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import Response

from .model import REVIEW_PROMPT_VERSION, review_prompt_hash
from .schemas import ReviewCreate, ReviewRunResponse, FindingUpdate
from .workflow import ReviewWorkflow, now
from .reports import report_bytes


def create_review_router(db, settings):
    router = APIRouter(prefix='/api')
    workflow = ReviewWorkflow(db, settings)

    @router.on_event('startup')
    def recover():
        db.recover_interrupted()

    def row_or_404(review_id):
        row = db.get_review(review_id)
        if not row:
            raise HTTPException(404, '审查不存在')
        return row

    def detail(review_id):
        return ReviewRunResponse(**row_or_404(review_id), requirements=db.list_requirements(review_id),
            requirement_checks=db.list_requirement_checks(review_id), findings=db.list_findings(review_id))

    @router.post('/reviews', response_model=ReviewRunResponse, status_code=202)
    def create(body: ReviewCreate, tasks: BackgroundTasks):
        if body.tender_document_id == body.bid_document_id:
            raise HTTPException(422, '招标文件和投标文件不能相同')
        tender, bid = db.get_document(body.tender_document_id), db.get_document(body.bid_document_id)
        if not tender or not bid:
            raise HTTPException(404, '招标文件或投标文件不存在')
        if settings.model_provider != 'ollama' and not body.external_processing_consent:
            raise HTTPException(422, '请先同意将候选文档片段发送给配置的模型服务')
        if not settings.model_base_url or not settings.model_name or (settings.model_provider != 'ollama' and not settings.model_api_key):
            raise HTTPException(422, '模型配置不完整，请配置后重启后端')
        rid = str(uuid4())
        db.insert_review(dict(id=rid, name=body.name or f'{tender.original_name} / {bid.original_name}'[:100],
            tender_document_id=tender.id, bid_document_id=bid.id, model_provider=settings.model_provider,
            model_base_url=settings.model_base_url, model_name=settings.model_name, prompt_version=REVIEW_PROMPT_VERSION,
            prompt_hash=review_prompt_hash(), model_parameters=json.dumps(dict(temperature=settings.model_temperature,
                batch_chars=settings.model_batch_chars)), created_at=now()))
        result = detail(rid)
        tasks.add_task(workflow.run, rid)
        return result

    @router.get('/reviews/{review_id}', response_model=ReviewRunResponse)
    def get_review(review_id: str):
        return detail(review_id)

    @router.post('/reviews/{review_id}/retry', response_model=ReviewRunResponse, status_code=202)
    def retry(review_id: str, tasks: BackgroundTasks):
        row_or_404(review_id)
        if not db.claim_retry(review_id):
            raise HTTPException(409, '仅失败的审查允许重试')
        result = detail(review_id)
        tasks.add_task(workflow.run, review_id)
        return result

    @router.get('/reviews/{review_id}/requirements')
    def requirements(review_id: str):
        row_or_404(review_id)
        return db.list_requirements(review_id)

    @router.get('/reviews/{review_id}/requirement-checks')
    def checks(review_id: str):
        row_or_404(review_id)
        return db.list_requirement_checks(review_id)

    @router.get('/reviews/{review_id}/findings')
    def findings(review_id: str):
        row_or_404(review_id)
        return db.list_findings(review_id)

    @router.patch('/findings/{finding_id}', response_model=ReviewRunResponse)
    def update(finding_id: str, body: FindingUpdate):
        try:
            with workflow.lock:
                rid = db.update_finding(finding_id, body)
            return detail(rid)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @router.post('/reviews/{review_id}/finalize', response_model=ReviewRunResponse)
    def finalize(review_id: str):
        row_or_404(review_id)
        try:
            workflow.finalize(review_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return detail(review_id)

    @router.get('/reviews/{review_id}/report')
    def report(review_id: str, format: Literal['json', 'docx'] = 'json'):
        row = row_or_404(review_id)
        if row['status'] != 'completed' or not row['report_snapshot']:
            raise HTTPException(409, '完成所有人工复核后才能下载报告')
        content, media = report_bytes(json.loads(row['report_snapshot']), format)
        return Response(content, media_type=media,
                        headers={'Content-Disposition': f'attachment; filename="BidGuard-{review_id}.{format}"'})

    return router
