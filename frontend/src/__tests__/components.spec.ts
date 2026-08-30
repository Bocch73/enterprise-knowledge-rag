import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import AnswerPanel from '@/components/AnswerPanel.vue'
import KnowledgeCatalog from '@/components/KnowledgeCatalog.vue'
import KnowledgeSidebar from '@/components/KnowledgeSidebar.vue'
import OverviewDashboard from '@/components/OverviewDashboard.vue'
import { streamAnswer } from '@/services/api'
import type { AnswerStreamResult } from '@/types/api'

vi.mock('@/services/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/services/api')>()
  return {
    ...original,
    streamAnswer:
      vi.fn<
        (
          token: string,
          knowledgeBaseId: string,
          question: string,
          onDelta: (text: string) => void,
        ) => Promise<AnswerStreamResult>
      >(),
  }
})

const knowledgeBase = {
  id: 'kb-1',
  name: '员工制度',
  description: '制度与流程',
  owner_id: 'user-1',
  access_level: 'owner' as const,
  created_at: '2026-08-28T00:00:00Z',
}

describe('knowledge sidebar', () => {
  it('selects an existing base and emits validated creation data', async () => {
    const wrapper = mount(KnowledgeSidebar, {
      props: { knowledgeBases: [knowledgeBase], selectedId: '', loading: false, creating: false },
    })

    await wrapper.get('.knowledge-item').trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual(['kb-1'])

    await wrapper.get('.icon-button').trigger('click')
    await wrapper.get('input').setValue('安全制度')
    await wrapper.get('textarea').setValue('企业安全要求')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('create')?.[0]).toEqual([
      { name: '安全制度', description: '企业安全要求' },
    ])
  })
})

describe('layered workspace', () => {
  it('renders real overview totals and routes quick actions', async () => {
    const wrapper = mount(OverviewDashboard, {
      props: {
        knowledgeBases: [knowledgeBase],
        documentCounts: { 'kb-1': 3 },
        readiness: { status: 'ready', checks: { application: 'up', database: 'up' } },
        loading: false,
        userName: 'Dawn',
      },
    })

    expect(wrapper.text()).toContain('Dawn，欢迎回来')
    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).toContain('数据库 已连接')
    await wrapper.get('.overview-hero__actions .button--mint').trigger('click')
    expect(wrapper.emitted('navigate')?.[0]).toEqual(['documents'])
  })

  it('searches knowledge spaces and opens their document center', async () => {
    const wrapper = mount(KnowledgeCatalog, {
      props: {
        knowledgeBases: [knowledgeBase],
        documentCounts: { 'kb-1': 2 },
        selectedId: 'kb-1',
        creating: false,
      },
    })

    expect(wrapper.text()).toContain('2 份')
    await wrapper.get('input[type="search"]').setValue('不存在')
    expect(wrapper.text()).toContain('没有匹配的知识库')
    await wrapper.get('input[type="search"]').setValue('员工')
    await wrapper.get('.knowledge-card footer button').trigger('click')
    expect(wrapper.emitted('openDocuments')?.[0]).toEqual(['kb-1'])
  })
})

describe('answer panel', () => {
  it('renders streamed text and expandable citation evidence', async () => {
    vi.mocked(streamAnswer).mockImplementation(
      async (_token, _knowledgeBaseId, _question, onDelta) => {
        onDelta('员工需要每九十天轮换密码。[S1]')
        return {
          answerId: 'answer-1',
          model: 'deepseek-v4-flash',
          refused: false,
          citations: [
            {
              citation: 'S1',
              chunk_id: 'chunk-1',
              document_id: 'document-1',
              document_title: '安全制度',
              document_version_id: 'version-1',
              version_number: 1,
              original_filename: 'security.md',
              chunk_index: 0,
              start_offset: 0,
              end_offset: 30,
              quoted_text: '密码必须每九十天轮换。',
            },
          ],
        }
      },
    )
    const wrapper = mount(AnswerPanel, {
      props: { token: 'token', knowledgeBaseId: 'kb-1', knowledgeBaseName: '员工制度' },
    })

    await wrapper.get('textarea').setValue('密码规则是什么？')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('员工需要每九十天轮换密码。[S1]')
    expect(wrapper.text()).toContain('安全制度')
    expect(wrapper.text()).toContain('deepseek-v4-flash')
  })
})
