<script setup lang="ts">
import { ref, watch } from 'vue'

import type { KnowledgeBase } from '@/types/api'

const props = defineProps<{
  knowledgeBases: KnowledgeBase[]
  selectedId: string
  loading: boolean
  creating: boolean
}>()

const emit = defineEmits<{
  select: [id: string]
  create: [input: { name: string; description: string | null }]
}>()

const showForm = ref(false)
const name = ref('')
const description = ref('')
const previousCount = ref(props.knowledgeBases.length)

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
</script>

<template>
  <aside class="workspace-sidebar">
    <div class="brand brand--light brand--workspace">
      <span class="brand__mark" aria-hidden="true">知</span><span>知序</span>
    </div>

    <div class="sidebar-heading">
      <span>我的知识库</span>
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
          {{ creating ? '创建中…' : '创建' }}
        </button>
      </div>
    </form>

    <div v-if="loading" class="sidebar-loading">正在载入…</div>
    <nav v-else class="knowledge-list" aria-label="知识库列表">
      <button
        v-for="item in knowledgeBases"
        :key="item.id"
        type="button"
        class="knowledge-item"
        :class="{ 'knowledge-item--active': item.id === selectedId }"
        @click="emit('select', item.id)"
      >
        <span class="knowledge-item__icon" aria-hidden="true">{{ item.name.slice(0, 1) }}</span>
        <span class="knowledge-item__text">
          <strong>{{ item.name }}</strong>
          <small>{{
            item.access_level === 'owner'
              ? '所有者'
              : item.access_level === 'editor'
                ? '编辑者'
                : '查看者'
          }}</small>
        </span>
        <span aria-hidden="true">›</span>
      </button>
      <p v-if="knowledgeBases.length === 0" class="sidebar-empty">
        还没有知识库<br />点击上方加号创建
      </p>
    </nav>

    <div class="sidebar-note"><span aria-hidden="true">●</span> PostgreSQL · DeepSeek 已连接</div>
  </aside>
</template>
