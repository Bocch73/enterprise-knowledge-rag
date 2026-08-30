<script setup lang="ts">
import { ref, watch } from 'vue'

import type { KnowledgeBase, WorkspaceSection } from '@/types/api'

const props = withDefaults(
  defineProps<{
    knowledgeBases: KnowledgeBase[]
    selectedId: string
    loading: boolean
    creating: boolean
    activeSection?: WorkspaceSection
    documentCount?: number
  }>(),
  { activeSection: 'overview', documentCount: 0 },
)

const emit = defineEmits<{
  select: [id: string]
  create: [input: { name: string; description: string | null }]
  navigate: [section: WorkspaceSection]
}>()

const showForm = ref(false)
const name = ref('')
const description = ref('')
const previousCount = ref(props.knowledgeBases.length)

const navigation: Array<{ id: WorkspaceSection; label: string; hint: string }> = [
  { id: 'overview', label: '概览', hint: '全局状态' },
  { id: 'knowledge', label: '知识库', hint: '空间管理' },
  { id: 'documents', label: '文档中心', hint: '上传与索引' },
  { id: 'qa', label: '问答实验室', hint: '检索与引用' },
]

watch(
  () => props.knowledgeBases.length,
  (count) => {
    if (count > previousCount.value) {
      name.value = ''
      description.value = ''
      showForm.value = false
    }
    previousCount.value = count
  },
)

function submit(): void {
  const cleanName = name.value.trim()
  if (cleanName.length < 2) return
  emit('create', { name: cleanName, description: description.value.trim() || null })
}

function selectKnowledgeBase(id: string): void {
  emit('select', id)
  emit('navigate', 'documents')
}
</script>

<template>
  <aside class="workspace-sidebar">
    <div class="brand brand--light brand--workspace">
      <span class="brand__mark" aria-hidden="true">知</span>
      <span><strong>知序</strong><small>Knowledge OS</small></span>
    </div>

    <nav class="primary-nav" aria-label="工作台主导航">
      <button
        v-for="(item, index) in navigation"
        :key="item.id"
        type="button"
        class="primary-nav__item"
        :class="{ 'primary-nav__item--active': activeSection === item.id }"
        @click="emit('navigate', item.id)"
      >
        <span class="primary-nav__icon" aria-hidden="true">
          <svg v-if="index === 0" viewBox="0 0 24 24">
            <path d="M4 13h6V4H4v9Zm0 7h6v-4H4v4Zm10 0h6v-9h-6v9Zm0-16v4h6V4h-6Z" />
          </svg>
          <svg v-else-if="index === 1" viewBox="0 0 24 24">
            <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5v-16Z" />
            <path d="M4 18.5A2.5 2.5 0 0 1 6.5 16H20" />
          </svg>
          <svg v-else-if="index === 2" viewBox="0 0 24 24">
            <path d="M6 3h9l4 4v14H6V3Z" />
            <path d="M14 3v5h5M9 13h7M9 17h7" />
          </svg>
          <svg v-else viewBox="0 0 24 24">
            <path d="M4 5h16v11H8l-4 4V5Z" />
            <path d="M8 9h8M8 12h5" />
          </svg>
        </span>
        <span class="primary-nav__copy"
          ><strong>{{ item.label }}</strong
          ><small>{{ item.hint }}</small></span
        >
        <span v-if="item.id === 'knowledge'" class="primary-nav__count">{{
          knowledgeBases.length
        }}</span>
        <span v-else-if="item.id === 'documents'" class="primary-nav__count">{{
          documentCount
        }}</span>
      </button>
    </nav>

    <div class="sidebar-divider"></div>

    <div class="sidebar-heading">
      <span>知识空间</span>
      <button
        class="icon-button"
        type="button"
        aria-label="创建知识库"
        @click="showForm = !showForm"
      >
        ＋
      </button>
    </div>

    <form v-if="showForm" class="quick-create" @submit.prevent="submit">
      <label>
        <span class="sr-only">知识库名称</span>
        <input
          v-model="name"
          minlength="2"
          maxlength="200"
          required
          placeholder="知识库名称"
          autofocus
        />
      </label>
      <label>
        <span class="sr-only">知识库说明</span>
        <textarea
          v-model="description"
          maxlength="2000"
          rows="2"
          placeholder="一句话说明（可选）"
        ></textarea>
      </label>
      <div class="quick-create__actions">
        <button type="button" class="text-button text-button--light" @click="showForm = false">
          取消
        </button>
        <button type="submit" class="button button--small button--mint" :disabled="creating">
          {{ creating ? '创建中…' : '创建空间' }}
        </button>
      </div>
    </form>

    <div v-if="loading" class="sidebar-loading">正在载入知识空间…</div>
    <nav v-else class="knowledge-list" aria-label="知识库列表">
      <button
        v-for="item in knowledgeBases"
        :key="item.id"
        type="button"
        class="knowledge-item"
        :class="{ 'knowledge-item--active': item.id === selectedId }"
        @click="selectKnowledgeBase(item.id)"
      >
        <span class="knowledge-item__icon" aria-hidden="true">{{ item.name.slice(0, 1) }}</span>
        <span class="knowledge-item__text">
          <strong>{{ item.name }}</strong>
          <small>{{ item.access_level === 'owner' ? '我创建的' : '与我共享' }}</small>
        </span>
        <span aria-hidden="true">›</span>
      </button>
      <p v-if="knowledgeBases.length === 0" class="sidebar-empty">
        暂无知识空间<br />点击加号创建第一个
      </p>
    </nav>

    <div class="sidebar-note">
      <span aria-hidden="true">●</span>
      <span><strong>本地开发环境</strong><small>PostgreSQL · DeepSeek</small></span>
    </div>
  </aside>
</template>
