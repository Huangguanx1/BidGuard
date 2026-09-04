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

