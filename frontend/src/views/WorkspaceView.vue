<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import AnswerPanel from '@/components/AnswerPanel.vue'
import DocumentPanel from '@/components/DocumentPanel.vue'
import KnowledgeCatalog from '@/components/KnowledgeCatalog.vue'
import KnowledgeSidebar from '@/components/KnowledgeSidebar.vue'
import OverviewDashboard from '@/components/OverviewDashboard.vue'
import {
  createKnowledgeBase,
  getReadiness,
  humanizeError,
  listDocuments,
  listKnowledgeBases,
} from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import type { DocumentItem, KnowledgeBase, ReadinessStatus, WorkspaceSection } from '@/types/api'

const auth = useAuthStore()
const router = useRouter()
const activeSection = ref<WorkspaceSection>('overview')
const knowledgeBases = ref<KnowledgeBase[]>([])
const selectedId = ref('')
const documentCounts = ref<Record<string, number>>({})
const readiness = ref<ReadinessStatus | null>(null)
const loading = ref(false)
const creating = ref(false)
const errorMessage = ref('')

const selected = computed(
  () => knowledgeBases.value.find((item) => item.id === selectedId.value) ?? null,
)
const totalDocuments = computed(() =>
  Object.values(documentCounts.value).reduce((total, count) => total + count, 0),
)
const pageCopy = computed(() => {
  const pages: Record<WorkspaceSection, { eyebrow: string; title: string; description: string }> = {
    overview: {
      eyebrow: '工作台 / 概览',
      title: '企业知识总览',
      description: '从全局视角查看知识空间、文档资产和服务健康状态。',
    },
    knowledge: {
      eyebrow: '知识资产 / 知识库',
      title: '知识库管理',
      description: '按业务边界组织资料，并为不同团队保留清晰的数据访问范围。',
    },
    documents: {
      eyebrow: `知识资产 / ${selected.value?.name ?? '文档中心'}`,
      title: '文档中心',
      description: selected.value?.description || '上传、跟踪并管理进入检索系统的企业资料。',
    },
    qa: {
      eyebrow: `问答实验室 / ${selected.value?.name ?? '选择知识库'}`,
      title: '知识问答实验室',
      description: '选择明确的知识范围，验证回答质量，并展开检查每一条来源依据。',
    },
  }
  return pages[activeSection.value]
})

onMounted(loadWorkspace)

async function loadWorkspace(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    const [items, health] = await Promise.all([listKnowledgeBases(auth.token), getReadiness()])
    knowledgeBases.value = items
    readiness.value = health
    if (!items.some((item) => item.id === selectedId.value)) selectedId.value = items[0]?.id ?? ''
    await loadDocumentCounts(items)
  } catch (error) {
    errorMessage.value = humanizeError(error)
  } finally {
    loading.value = false
  }
}

async function loadDocumentCounts(items: KnowledgeBase[]): Promise<void> {
  const results = await Promise.allSettled(
    items.map(async (item) => ({
      id: item.id,
      documents: await listDocuments(auth.token, item.id),
    })),
  )
  const counts: Record<string, number> = {}
  results.forEach((result) => {
    if (result.status === 'fulfilled') counts[result.value.id] = result.value.documents.length
  })
  documentCounts.value = counts
}

async function create(input: { name: string; description: string | null }): Promise<void> {
  creating.value = true
  errorMessage.value = ''
  try {
    const created = await createKnowledgeBase(auth.token, input)
    knowledgeBases.value = [...knowledgeBases.value, created]
    documentCounts.value = { ...documentCounts.value, [created.id]: 0 }
    selectedId.value = created.id
    activeSection.value = 'documents'
  } catch (error) {
    errorMessage.value = humanizeError(error)
  } finally {
    creating.value = false
  }
}

function updateDocuments(knowledgeBaseId: string, documents: DocumentItem[]): void {
  documentCounts.value = { ...documentCounts.value, [knowledgeBaseId]: documents.length }
}

function selectKnowledgeBase(id: string): void {
  selectedId.value = id
}

function openDocuments(id: string): void {
  selectedId.value = id
  activeSection.value = 'documents'
}

async function logout(): Promise<void> {
  auth.logout()
  await router.replace('/login')
}
</script>

<template>
  <main class="workspace-shell">
    <KnowledgeSidebar
      :knowledge-bases="knowledgeBases"
      :selected-id="selectedId"
      :loading="loading"
      :creating="creating"
      :active-section="activeSection"
      :document-count="totalDocuments"
      @select="selectKnowledgeBase"
      @create="create"
      @navigate="activeSection = $event"
    />

    <section class="workspace-main">
      <header class="workspace-header">
        <div>
          <p class="workspace-header__crumb">{{ pageCopy.eyebrow }}</p>
          <h1>{{ pageCopy.title }}</h1>
          <p>{{ pageCopy.description }}</p>
        </div>
        <div class="user-menu">
          <span class="user-avatar" aria-hidden="true">{{
            auth.user?.display_name.slice(0, 1)
          }}</span>
          <span
            ><strong>{{ auth.user?.display_name }}</strong
            ><small>{{ auth.user?.email }}</small></span
          >
          <button class="text-button" type="button" @click="logout">退出</button>
        </div>
      </header>

      <div v-if="errorMessage" class="workspace-alert alert alert--error" role="alert">
        {{ errorMessage }}
      </div>

      <OverviewDashboard
        v-if="activeSection === 'overview'"
        :knowledge-bases="knowledgeBases"
        :document-counts="documentCounts"
        :readiness="readiness"
        :loading="loading"
        :user-name="auth.user?.display_name ?? '你好'"
        @navigate="activeSection = $event"
      />

      <KnowledgeCatalog
        v-else-if="activeSection === 'knowledge'"
        :knowledge-bases="knowledgeBases"
        :document-counts="documentCounts"
        :selected-id="selectedId"
        :creating="creating"
        @select="selectKnowledgeBase"
        @create="create"
        @open-documents="openDocuments"
      />

      <template v-else-if="selected">
        <div class="context-toolbar">
          <label
            ><span>当前知识范围</span
            ><select v-model="selectedId" aria-label="当前知识库">
              <option v-for="item in knowledgeBases" :key="item.id" :value="item.id">
                {{ item.name }}
              </option>
            </select></label
          >
          <span class="context-toolbar__meta"
            ><i aria-hidden="true"></i>{{ documentCounts[selected.id] ?? 0 }} 份文档 ·
            {{ selected.access_level === 'owner' ? '所有者权限' : '共享访问' }}</span
          >
        </div>

        <DocumentPanel
          v-if="activeSection === 'documents'"
          :key="`documents-${selected.id}`"
          :token="auth.token"
          :knowledge-base-id="selected.id"
          :access-level="selected.access_level"
          @documents-changed="updateDocuments(selected.id, $event)"
        />
        <AnswerPanel
          v-else
          :key="`answer-${selected.id}`"
          :token="auth.token"
          :knowledge-base-id="selected.id"
          :knowledge-base-name="selected.name"
        />
      </template>

      <div v-else-if="!loading" class="workspace-empty">
        <span aria-hidden="true">知</span>
        <h2>先创建一个知识库</h2>
        <p>知识库是文档权限与检索范围的基本边界。</p>
        <button class="button button--primary" type="button" @click="activeSection = 'knowledge'">
          前往知识库管理
        </button>
      </div>
    </section>
  </main>
</template>
