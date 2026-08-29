import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ApiError,
  createKnowledgeBase,
  getCurrentUser,
  getIngestionJob,
  humanizeError,
  listDocuments,
  listKnowledgeBases,
  loginUser,
  registerUser,
  streamAnswer,
  uploadDocument,
} from '@/services/api'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('API service', () => {
  it('sends login credentials as an OAuth form', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({ access_token: 'token-1', token_type: 'bearer', expires_in: 1800 }),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(loginUser('dawn@example.com', 'long-password')).resolves.toMatchObject({
      access_token: 'token-1',
    })
    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(options.body)).toContain('username=dawn%40example.com')
    expect(String(options.body)).toContain('password=long-password')
  })

  it('adds bearer authentication and JSON content type', async () => {
    const created = {
      id: 'kb-1',
      name: '员工制度',
      description: null,
      owner_id: 'user-1',
      access_level: 'owner',
      created_at: '2026-08-28T00:00:00Z',
    }
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify(created), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await createKnowledgeBase('secret-token', { name: '员工制度', description: null })

    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = new Headers(options.headers)
    expect(headers.get('Authorization')).toBe('Bearer secret-token')
    expect(headers.get('Content-Type')).toBe('application/json')
  })

  it('parses answer deltas, citations, and the done event across chunks', async () => {
    const encoder = new TextEncoder()
    const chunks = [
      'event: answer_delta\ndata: {"text":"每九十天"}\n\nevent: answer_',
      'delta\ndata: {"text":"轮换密码。[S1]"}\n\nevent: citations\ndata: {"items":[{"citation":"S1","chunk_id":"chunk-1"}]}\n\n',
      'event: done\ndata: {"answer_id":"answer-1","model":"deepseek-v4-flash","refused":false}\n\n',
    ]
    const stream = new ReadableStream({
      start(controller) {
        chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)))
        controller.close()
      },
    })
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
        ),
    )
    let answer = ''

    const result = await streamAnswer('token', 'kb-1', '密码规则是什么？', (delta) => {
      answer += delta
    })

    expect(answer).toBe('每九十天轮换密码。[S1]')
    expect(result.answerId).toBe('answer-1')
    expect(result.model).toBe('deepseek-v4-flash')
    expect(result.citations[0]?.citation).toBe('S1')
  })

  it('translates safe application errors and includes the request id', () => {
    expect(
      humanizeError(new ApiError('upstream text', 401, 'authentication_failed', 'request-123')),
    ).toBe('邮箱或密码不正确。（请求编号：request-123）')
  })

  it('covers the typed request helpers for registration, lists, upload, and jobs', async () => {
    const responses = [
      { id: 'user-1', display_name: 'Dawn' },
      { id: 'user-1', display_name: 'Dawn' },
      [],
      [],
      {
        document: { id: 'document-1' },
        version: { id: 'version-1' },
        ingestion_job: { id: 'job-1' },
      },
      { id: 'job-1', status: 'queued' },
    ]
    const fetchMock = vi.fn<typeof fetch>()
    responses.forEach((payload, index) => {
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify(payload), {
          status: index === 0 || index === 4 ? 201 : 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    })
    vi.stubGlobal('fetch', fetchMock)

    await registerUser({
      email: 'dawn@example.com',
      display_name: 'Dawn',
      password: 'long-password',
    })
    await getCurrentUser('token')
    await listKnowledgeBases('token')
    await listDocuments('token', 'kb-1')
    await uploadDocument('token', 'kb-1', new File(['policy'], 'policy.md'), '制度')
    await getIngestionJob('token', 'job-1')

    const uploadOptions = fetchMock.mock.calls[4]?.[1]
    expect(uploadOptions?.body).toBeInstanceOf(FormData)
    expect(new Headers(uploadOptions?.headers).has('Content-Type')).toBe(false)
  })

  it('uses the structured backend error and safe network fallbacks', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error: {
              code: 'permission_denied',
              message: 'raw permission message',
              request_id: 'req-1',
              details: null,
            },
          }),
          { status: 403, headers: { 'Content-Type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(new Response('<html>proxy error</html>', { status: 502 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(listKnowledgeBases('token')).rejects.toMatchObject({
      code: 'permission_denied',
      requestId: 'req-1',
    })
    await expect(listKnowledgeBases('token')).rejects.toMatchObject({
      code: 'unknown_error',
      status: 502,
    })
    expect(humanizeError(new TypeError('network'))).toContain('无法连接后端')
    expect(humanizeError(new Error('plain error'))).toBe('plain error')
    expect(humanizeError(null)).toContain('未知错误')
  })

  it('rejects an answer stream without a done event', async () => {
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          new TextEncoder().encode('event: answer_delta\ndata: {"text":"半个答案"}\n\n'),
        )
        controller.close()
      },
    })
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(new Response(stream, { status: 200 })),
    )

    await expect(streamAnswer('token', 'kb-1', '问题', () => undefined)).rejects.toMatchObject({
      code: 'incomplete_stream',
    })
  })
})
