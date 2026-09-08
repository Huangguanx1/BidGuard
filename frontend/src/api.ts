export interface DocumentSummary {
  id: string
  original_name: string
  file_type: 'docx' | 'pdf'
  file_size: number
  page_count: number
  text_char_count: number
  warnings: string[]
  heading_count: number
  paragraph_count: number
  table_count: number
}

export interface Requirement {
  id: string
  category: 'qualification' | 'disqualification' | 'scoring' | 'timeline' | 'materials'
  title: string
  description: string
  mandatory: boolean
  source_excerpt: string
  confidence: number
}

export interface Evidence {
  block_id: string
  page_number: number | null
  excerpt: string
  document_role: 'tender' | 'bid'
  location_confidence: number
}

export interface RequirementCheck {
  id: string
  requirement_id: string
  match_status: 'satisfied' | 'partial' | 'not_satisfied' | 'not_found' | 'uncertain'
  reason: string
  confidence: number
  tender_evidence: Evidence[]
  bid_evidence: Evidence[]
  searched_block_ids: string[]
}

export interface Finding {
  id: string
  category: string
  risk_level: 'high' | 'medium' | 'low'
  title: string
  description: string
  suggestion: string
  confidence: number
  type: 'consistency' | 'requirement_risk'
  evidence: Evidence[]
  review_status: 'pending' | 'confirmed' | 'ignored' | 'modified'
  override: { title: string; description: string; risk_level: 'high' | 'medium' | 'low'; suggestion: string } | null
  reviewer_note: string | null
}

export interface ReviewRun {
  id: string
  name: string
  status: 'queued' | 'running' | 'awaiting_review' | 'completed' | 'failed'
  current_stage: string
  progress: number
  run_attempt: number
  error_message: string | null
  tender_document_id: string
  bid_document_id: string
  model_name: string
  input_tokens: number
  output_tokens: number
  requirements: Requirement[]
  requirement_checks: RequirementCheck[]
  findings: Finding[]
}

export interface ReviewHistoryItem {
  id: string
  name: string
  status: ReviewRun['status']
  current_stage: string
  model_name: string
  input_tokens: number
  output_tokens: number
  finding_count: number
  high_risk_count: number
  created_at: string
  updated_at: string
  tender_file_name: string
  bid_file_name: string
  error_message?: string | null
}

interface ApiErrorBody {
  detail?: string
}

export async function uploadDocument(file: File): Promise<DocumentSummary> {
  const form = new FormData()
  form.append('file', file)
  const response = await fetch('/api/documents', { method: 'POST', body: form })
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(body.detail || `上传失败（HTTP ${response.status}）`)
  }
  return response.json() as Promise<DocumentSummary>
}

export async function createReview(
  tenderDocumentId: string,
  bidDocumentId: string,
  consent = false,
): Promise<ReviewRun> {
  const response = await fetch('/api/reviews', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tender_document_id: tenderDocumentId,
      bid_document_id: bidDocumentId,
      external_processing_consent: consent,
    }),
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(body.detail || `AI 审查失败（HTTP ${response.status}）`)
  }
  return response.json() as Promise<ReviewRun>
}

export async function listReviews(offset = 0): Promise<{ items: ReviewHistoryItem[]; total: number }> {
  const response = await fetch(`/api/reviews?offset=${offset}&limit=20`)
  if (!response.ok) throw new Error(`获取审查历史失败（HTTP ${response.status}）`)
  return response.json() as Promise<{ items: ReviewHistoryItem[]; total: number }>
}

export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(typeof error.detail === 'string' ? error.detail : `请求失败（HTTP ${response.status}），请检查输入`)
  }
  return response.json() as Promise<T>
}

export const categoryLabels: Record<string, string> = { qualification: '资格条件', disqualification: '废标条款', scoring: '评分标准', timeline: '时间节点', materials: '材料要求', amount: '金额', date: '日期', project_name: '项目名称', duration: '工期' }
export const statusLabels = { queued: '排队中', running: '执行中', awaiting_review: '待人工复核', completed: '已完成', failed: '失败' }
export const matchLabels = { satisfied: '满足', partial: '部分满足', not_satisfied: '不满足', not_found: '未找到', uncertain: '待确认' }
export const reviewLabels = { pending: '待确认', confirmed: '已确认', ignored: '已忽略', modified: '已修改' }
export const riskLabels = { high: '高', medium: '中', low: '低' }
