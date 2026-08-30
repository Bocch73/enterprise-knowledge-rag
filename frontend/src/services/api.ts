import type {
  AnswerCitation,
  AnswerStreamResult,
  ApiErrorResponse,
  DocumentItem,
  DocumentUploadResponse,
  IngestionJob,
  KnowledgeBase,
  ReadinessStatus,
  TokenResponse,
  User,
} from '@/types/api'

const API_PREFIX = import.meta.env.VITE_API_PREFIX ?? '/api/v1'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null

  constructor(
    message: string,
    status: number,
    code = 'unknown_error',
    requestId: string | null = null,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body instanceof URLSearchParams)
    headers.set('Content-Type', 'application/x-www-form-urlencoded;charset=UTF-8')
  else if (options.body && !(options.body instanceof FormData))
    headers.set('Content-Type', 'application/json')

  const response = await fetch(`${API_PREFIX}${path}`, { ...options, headers })
  if (!response.ok) throw await toApiError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const payload = (await response.json()) as ApiErrorResponse
    if (payload.error?.message) {
      return new ApiError(
        payload.error.message,
        response.status,
        payload.error.code,
        payload.error.request_id,
      )
    }
  } catch {
    // A proxy or network boundary can return a non-JSON error page.
  }
  return new ApiError(`请求失败（HTTP ${response.status}）`, response.status)
}

export function humanizeError(error: unknown): string {
  if (error instanceof ApiError) {
    const requestSuffix = error.requestId ? `（请求编号：${error.requestId}）` : ''
    return `${translateErrorCode(error.code, error.message)}${requestSuffix}`
  }
  if (error instanceof TypeError) return '无法连接后端服务，请确认后端已经启动。'
  return error instanceof Error ? error.message : '发生未知错误，请稍后重试。'
}

function translateErrorCode(code: string, fallback: string): string {
  const messages: Record<string, string> = {
    authentication_failed: '邮箱或密码不正确。',
    authentication_required: '登录已失效，请重新登录。',
    email_already_registered: '这个邮箱已经注册。',
    generation_provider_unavailable: '回答模型暂时不可用，请稍后重试。',
    generation_rate_limited: '回答请求过多，请稍后重试。',
    generation_timeout: '回答模型响应超时，请稍后重试。',
    knowledge_base_not_found: '知识库不存在，或你没有访问权限。',
    permission_denied: '你没有执行此操作的权限。',
    request_validation_error: '填写内容不符合要求，请检查后重试。',
  }
  return messages[code] ?? fallback
}

export async function registerUser(input: {
  email: string
  display_name: string
  password: string
}): Promise<User> {
  return request<User>('/auth/register', { method: 'POST', body: JSON.stringify(input) })
}

export async function loginUser(email: string, password: string): Promise<TokenResponse> {
  const body = new URLSearchParams({ username: email, password })
  return request<TokenResponse>('/auth/login', { method: 'POST', body })
}

export async function getCurrentUser(token: string): Promise<User> {
  return request<User>('/auth/me', {}, token)
}

export async function getReadiness(): Promise<ReadinessStatus> {
  return request<ReadinessStatus>('/health/ready')
}

export async function listKnowledgeBases(token: string): Promise<KnowledgeBase[]> {
  return request<KnowledgeBase[]>('/knowledge-bases', {}, token)
}

export async function createKnowledgeBase(
  token: string,
  input: { name: string; description: string | null },
): Promise<KnowledgeBase> {
  return request<KnowledgeBase>(
    '/knowledge-bases',
    { method: 'POST', body: JSON.stringify(input) },
    token,
  )
}

export async function listDocuments(
  token: string,
  knowledgeBaseId: string,
): Promise<DocumentItem[]> {
  return request<DocumentItem[]>(`/knowledge-bases/${knowledgeBaseId}/documents`, {}, token)
}

export async function uploadDocument(
  token: string,
  knowledgeBaseId: string,
  file: File,
  title: string,
): Promise<DocumentUploadResponse> {
  const body = new FormData()
  body.append('file', file)
  if (title.trim()) body.append('title', title.trim())
  return request<DocumentUploadResponse>(
    `/knowledge-bases/${knowledgeBaseId}/documents`,
    { method: 'POST', body },
    token,
  )
}

export async function getIngestionJob(token: string, jobId: string): Promise<IngestionJob> {
  return request<IngestionJob>(`/ingestion-jobs/${jobId}`, {}, token)
}

export async function streamAnswer(
  token: string,
  knowledgeBaseId: string,
  question: string,
  onDelta: (text: string) => void,
): Promise<AnswerStreamResult> {
  const response = await fetch(`${API_PREFIX}/knowledge-bases/${knowledgeBaseId}/answers/stream`, {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ question, top_k: 5 }),
  })
  if (!response.ok) throw await toApiError(response)
  if (!response.body) throw new ApiError('浏览器没有收到回答数据流。', 502, 'empty_stream')

  const result: AnswerStreamResult = { answerId: '', model: '', refused: false, citations: [] }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    blocks.filter(Boolean).forEach((block) => applyServerEvent(block, result, onDelta))
    if (done) break
  }
  if (buffer.trim()) applyServerEvent(buffer, result, onDelta)
  if (!result.answerId) throw new ApiError('回答数据流缺少完成事件。', 502, 'incomplete_stream')
  return result
}

function applyServerEvent(
  block: string,
  result: AnswerStreamResult,
  onDelta: (text: string) => void,
): void {
  const lines = block.split('\n')
  const event = lines
    .find((line) => line.startsWith('event:'))
    ?.slice(6)
    .trim()
  const dataText = lines
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n')
  if (!event || !dataText) return

  const data = JSON.parse(dataText) as Record<string, unknown>
  if (event === 'answer_delta' && typeof data.text === 'string') onDelta(data.text)
  if (event === 'citations' && Array.isArray(data.items))
    result.citations = data.items as AnswerCitation[]
  if (event === 'done') {
    result.answerId = typeof data.answer_id === 'string' ? data.answer_id : ''
    result.model = typeof data.model === 'string' ? data.model : ''
    result.refused = data.refused === true
  }
}
