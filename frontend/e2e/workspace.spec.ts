import { expect, test } from '@playwright/test'

const user = {
  id: 'user-1',
  email: 'dawn@example.com',
  display_name: 'Dawn',
  is_active: true,
  roles: ['member'],
  created_at: '2026-08-28T00:00:00Z',
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/auth/login', (route) =>
    route.fulfill({ json: { access_token: 'token-1', token_type: 'bearer', expires_in: 1800 } }),
  )
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: user }))
  await page.route('**/api/v1/knowledge-bases', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 201,
        json: {
          id: 'kb-2',
          name: '产品手册',
          description: '产品资料',
          owner_id: 'user-1',
          access_level: 'owner',
          created_at: '2026-08-28T00:00:00Z',
        },
      })
      return
    }
    await route.fulfill({
      json: [
        {
          id: 'kb-1',
          name: '员工制度',
          description: '制度与流程',
          owner_id: 'user-1',
          access_level: 'owner',
          created_at: '2026-08-28T00:00:00Z',
        },
      ],
    })
  })
  await page.route('**/api/v1/knowledge-bases/*/documents', (route) =>
    route.fulfill({
      json: [
        {
          id: 'document-1',
          knowledge_base_id: 'kb-1',
          title: '信息安全制度',
          created_by_id: 'user-1',
          created_at: '2026-08-28T00:00:00Z',
        },
      ],
    }),
  )
  await page.route('**/api/v1/knowledge-bases/*/answers/stream', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body:
        'event: answer_delta\ndata: {"text":"员工必须每九十天轮换密码。[S1]"}\n\n' +
        'event: citations\ndata: {"items":[{"citation":"S1","chunk_id":"chunk-1","document_id":"document-1","document_title":"信息安全制度","document_version_id":"version-1","version_number":1,"original_filename":"security.md","chunk_index":0,"start_offset":0,"end_offset":30,"quoted_text":"密码必须每九十天轮换。"}]}\n\n' +
        'event: done\ndata: {"answer_id":"answer-1","model":"deepseek-v4-flash","refused":false}\n\n',
    }),
  )
})

test('logs in and renders a cited knowledge-base answer', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('邮箱').fill('dawn@example.com')
  await page.getByLabel('密码').fill('long-enough-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()

  await expect(page.getByRole('heading', { name: '员工制度', level: 1 })).toBeVisible()
  await expect(page.getByText('信息安全制度')).toBeVisible()
  await page.getByLabel('输入问题').fill('密码规则是什么？')
  await page.getByLabel('发送问题').click()

  await expect(page.getByText('员工必须每九十天轮换密码。[S1]')).toBeVisible()
  await expect(page.getByText('security.md · 版本 1')).toBeVisible()
})

test('creates a new knowledge base from the sidebar', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('邮箱').fill('dawn@example.com')
  await page.getByLabel('密码').fill('long-enough-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()

  await page.getByLabel('创建知识库').click()
  await page.getByLabel('知识库名称').fill('产品手册')
  await page.getByLabel('知识库说明').fill('产品资料')
  await page.getByRole('button', { name: '创建', exact: true }).click()

  await expect(page.getByRole('heading', { name: '产品手册', level: 1 })).toBeVisible()
})
