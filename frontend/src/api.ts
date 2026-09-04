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

export interface RequirementCheck {
  id: string
  requirement_id: string
  match_status: 'satisfied' | 'partial' | 'not_satisfied' | 'not_found' | 'uncertain'
  reason: string
  confidence: number
}

export interface Finding {
  id: string
  category: 'amount' | 'date' | 'project_name' | 'duration'
  risk_level: 'high' | 'medium' | 'low'
  title: string
  description: string
  suggestion: string
  confidence: number
}

export interface ReviewRun {
  id: string
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
  status: 'running' | 'awaiting_review' | 'failed'
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
): Promise<ReviewRun> {
  const response = await fetch('/api/reviews', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tender_document_id: tenderDocumentId,
      bid_document_id: bidDocumentId,
    }),
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(body.detail || `AI 审查失败（HTTP ${response.status}）`)
  }
  return response.json() as Promise<ReviewRun>
}

export async function listReviews(): Promise<{ items: ReviewHistoryItem[]; total: number }> {
  const response = await fetch('/api/reviews')
  if (!response.ok) throw new Error(`获取审查历史失败（HTTP ${response.status}）`)
  return response.json() as Promise<{ items: ReviewHistoryItem[]; total: number }>
}
