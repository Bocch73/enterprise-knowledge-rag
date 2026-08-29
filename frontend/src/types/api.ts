export type AccessLevel = 'owner' | 'editor' | 'viewer'
export type JobStatus = 'queued' | 'running' | 'completed' | 'failed'
export type JobStage =
  'queued' | 'parsing' | 'chunking' | 'embedding' | 'indexing' | 'completed' | 'failed'

export interface User {
  id: string
  email: string
  display_name: string
  is_active: boolean
  roles: string[]
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
}

export interface KnowledgeBase {
  id: string
  name: string
  description: string | null
  owner_id: string
  access_level: AccessLevel
  created_at: string
}

export interface DocumentItem {
  id: string
  knowledge_base_id: string
  title: string
  created_by_id: string
  created_at: string
}

export interface DocumentVersion {
  id: string
  document_id: string
  version_number: number
  original_filename: string
  media_type: string
  size_bytes: number
  sha256: string
  uploaded_by_id: string
  created_at: string
}

export interface IngestionJob {
  id: string
  document_version_id: string
  status: JobStatus
  stage: JobStage
  progress: number
  attempt_count: number
  max_attempts: number
  retryable: boolean
  error_code: string | null
  error_message: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface DocumentUploadResponse {
  document: DocumentItem
  version: DocumentVersion
  ingestion_job: IngestionJob
}

export interface AnswerCitation {
  citation: string
  chunk_id: string
  document_id: string
  document_title: string
  document_version_id: string
  version_number: number
  original_filename: string
  chunk_index: number
  start_offset: number
  end_offset: number
  quoted_text: string
}

export interface AnswerStreamResult {
  answerId: string
  model: string
  refused: boolean
  citations: AnswerCitation[]
}

export interface ApiErrorDetail {
  code: string
  message: string
  request_id: string
  details: Array<Record<string, unknown>> | null
}

export interface ApiErrorResponse {
  error: ApiErrorDetail
}
