<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { getIngestionJob, humanizeError, listDocuments, uploadDocument } from '@/services/api'
import type { AccessLevel, DocumentItem, IngestionJob } from '@/types/api'

const props = defineProps<{
  token: string
  knowledgeBaseId: string
  accessLevel: AccessLevel
}>()

const emit = defineEmits<{ documentsChanged: [documents: DocumentItem[]] }>()

const documents = ref<DocumentItem[]>([])
const loading = ref(false)
const uploading = ref(false)
const errorMessage = ref('')
const selectedFile = ref<File | null>(null)
const title = ref('')
const latestJob = ref<IngestionJob | null>(null)
let pollTimer: ReturnType<typeof setTimeout> | null = null

const canUpload = computed(() => props.accessLevel === 'owner' || props.accessLevel === 'editor')
const stageLabels: Record<string, string> = {
  queued: '等待处理',
  parsing: '解析文档',
  chunking: '文本分块',
  embedding: '生成向量',
  indexing: '写入索引',
  completed: '处理完成',
  failed: '处理失败',
}

watch(
  () => props.knowledgeBaseId,
  async () => {
    stopPolling()
    latestJob.value = null
    await loadDocuments()
  },
  { immediate: true },
)

onBeforeUnmount(stopPolling)

async function loadDocuments(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    documents.value = await listDocuments(props.token, props.knowledgeBaseId)
    emit('documentsChanged', documents.value)
  } catch (error) {
    errorMessage.value = humanizeError(error)
  } finally {
    loading.value = false
  }
}

function chooseFile(event: Event): void {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
  if (selectedFile.value && !title.value) {
    title.value = selectedFile.value.name.replace(/\.[^.]+$/, '')
  }
}

async function submitUpload(): Promise<void> {
  if (!selectedFile.value) {
    errorMessage.value = '请先选择 PDF、DOCX 或 Markdown 文件。'
    return
  }
  uploading.value = true
  errorMessage.value = ''
  try {
    const response = await uploadDocument(
      props.token,
      props.knowledgeBaseId,
      selectedFile.value,
      title.value,
    )
    latestJob.value = response.ingestion_job
    selectedFile.value = null
    title.value = ''
    await loadDocuments()
    schedulePoll()
  } catch (error) {
    errorMessage.value = humanizeError(error)
  } finally {
    uploading.value = false
  }
}

function schedulePoll(): void {
  stopPolling()
  if (!latestJob.value || ['completed', 'failed'].includes(latestJob.value.status)) return
  pollTimer = setTimeout(async () => {
    try {
      if (!latestJob.value) return
      latestJob.value = await getIngestionJob(props.token, latestJob.value.id)
      if (latestJob.value.status === 'completed') await loadDocuments()
    } catch (error) {
      errorMessage.value = humanizeError(error)
    }
    schedulePoll()
  }, 2000)
}

function stopPolling(): void {
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = null
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' }).format(
    new Date(value),
  )
}
</script>

<template>
  <section class="panel document-panel document-panel--workspace" aria-labelledby="documents-title">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">KNOWLEDGE SOURCES</p>
        <h2 id="documents-title">知识文档管理</h2>
      </div>
      <div class="panel-heading__meta">
        <span class="count-badge">{{ documents.length }} 份</span
        ><span class="index-badge">混合索引</span>
      </div>
    </div>

    <div v-if="errorMessage" class="alert alert--error" role="alert">{{ errorMessage }}</div>

    <form v-if="canUpload" class="upload-box" @submit.prevent="submitUpload">
      <label class="upload-drop">
        <input class="sr-only" type="file" accept=".pdf,.docx,.md" @change="chooseFile" />
        <span class="upload-drop__icon" aria-hidden="true">↥</span>
        <span>
          <strong>{{ selectedFile ? selectedFile.name : '选择文档上传' }}</strong>
          <small>PDF、DOCX 或 Markdown，最大 20 MB</small>
        </span>
      </label>
      <div v-if="selectedFile" class="upload-details">
        <label class="field field--compact">
          <span>文档标题</span>
          <input v-model="title" maxlength="200" required />
        </label>
        <button class="button button--primary" type="submit" :disabled="uploading">
          {{ uploading ? '上传中…' : '确认上传' }}
        </button>
      </div>
    </form>

    <div v-if="latestJob" class="job-card" :class="`job-card--${latestJob.status}`">
      <div class="job-card__row">
        <strong>{{ stageLabels[latestJob.stage] ?? latestJob.stage }}</strong>
        <span>{{ latestJob.progress }}%</span>
      </div>
      <div class="progress-track"><span :style="{ width: `${latestJob.progress}%` }"></span></div>
      <p v-if="latestJob.status === 'queued'">请在后端终端运行文档处理工作进程，页面会自动更新。</p>
      <p v-if="latestJob.error_message" class="job-card__error">{{ latestJob.error_message }}</p>
    </div>

    <div class="document-table-heading" aria-hidden="true">
      <span>文档名称</span><span>更新时间</span><span>索引状态</span>
    </div>
    <div v-if="loading" class="content-loading">正在读取文档…</div>
    <ul v-else-if="documents.length" class="document-list">
      <li v-for="document in documents" :key="document.id">
        <span class="file-icon" aria-hidden="true">文</span>
        <span class="document-list__content">
          <strong>{{ document.title }}</strong>
        </span>
        <time>{{ formatDate(document.created_at) }}</time>
        <span class="status-dot"><i aria-hidden="true"></i> 已收录</span>
      </li>
    </ul>
    <div v-else class="empty-state empty-state--small">
      <span aria-hidden="true">▤</span>
      <strong>还没有文档</strong>
      <p>
        {{
          canUpload ? '上传第一份企业资料，完成处理后即可提问。' : '知识库所有者还没有上传资料。'
        }}
      </p>
    </div>
  </section>
</template>
