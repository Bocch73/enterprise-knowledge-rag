<script setup lang="ts">
import { computed, ref } from 'vue'

import type { KnowledgeBase } from '@/types/api'

const props = defineProps<{
  knowledgeBases: KnowledgeBase[]
  documentCounts: Record<string, number>
  selectedId: string
  creating: boolean
}>()

const emit = defineEmits<{
  select: [id: string]
  create: [input: { name: string; description: string | null }]
  openDocuments: [id: string]
}>()

const query = ref('')
const accessFilter = ref<'all' | 'owner' | 'shared'>('all')
const accessFilters: Array<{ id: 'all' | 'owner' | 'shared'; label: string }> = [
  { id: 'all', label: '全部' },
  { id: 'owner', label: '我创建的' },
  { id: 'shared', label: '与我共享' },
]
const showCreate = ref(false)
const name = ref('')
const description = ref('')

const filtered = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  return props.knowledgeBases.filter((item) => {
    const matchesQuery =
      !keyword || `${item.name} ${item.description ?? ''}`.toLocaleLowerCase().includes(keyword)
    const matchesAccess =
      accessFilter.value === 'all' ||
      (accessFilter.value === 'owner' && item.access_level === 'owner') ||
      (accessFilter.value === 'shared' && item.access_level !== 'owner')
    return matchesQuery && matchesAccess
  })
})

function submit(): void {
  const cleanName = name.value.trim()
  if (cleanName.length < 2) return
  emit('create', { name: cleanName, description: description.value.trim() || null })
  name.value = ''
  description.value = ''
  showCreate.value = false
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(new Date(value))
}
</script>

<template>
  <div class="catalog-page">
    <div class="catalog-toolbar">
      <label class="catalog-search">
        <span aria-hidden="true">⌕</span><span class="sr-only">搜索知识库</span>
        <input v-model="query" type="search" placeholder="搜索名称或说明" />
      </label>
      <div class="segmented-control" aria-label="知识库权限筛选">
        <button
          v-for="item in accessFilters"
          :key="item.id"
          type="button"
          :class="{ active: accessFilter === item.id }"
          @click="accessFilter = item.id"
        >
          {{ item.label }}
        </button>
      </div>
      <button class="button button--primary" type="button" @click="showCreate = !showCreate">
        ＋ 新建知识库
      </button>
    </div>

    <form v-if="showCreate" class="catalog-create" @submit.prevent="submit">
      <div>
        <p class="eyebrow">NEW KNOWLEDGE SPACE</p>
        <h3>创建知识空间</h3>
        <p>建议按部门、产品或制度域拆分，权限和检索边界会更清晰。</p>
      </div>
      <label class="field"
        ><span>名称</span
        ><input
          v-model="name"
          minlength="2"
          maxlength="200"
          required
          placeholder="例如：人力资源制度"
      /></label>
      <label class="field"
        ><span>说明</span
        ><input v-model="description" maxlength="2000" placeholder="这个空间包含什么资料？"
      /></label>
      <div class="catalog-create__actions">
        <button class="text-button" type="button" @click="showCreate = false">取消</button
        ><button class="button button--primary" type="submit" :disabled="creating">
          {{ creating ? '创建中…' : '确认创建' }}
        </button>
      </div>
    </form>

    <div class="catalog-summary">
      <span>共 {{ filtered.length }} 个知识空间</span><span>知识库之间保持独立权限和检索边界</span>
    </div>

    <div v-if="filtered.length" class="knowledge-card-grid">
      <article
        v-for="item in filtered"
        :key="item.id"
        class="knowledge-card"
        :class="{ 'knowledge-card--selected': item.id === selectedId }"
        @click="emit('select', item.id)"
      >
        <div class="knowledge-card__top">
          <span class="space-monogram space-monogram--large">{{ item.name.slice(0, 1) }}</span
          ><span class="access-badge">{{
            item.access_level === 'owner'
              ? '所有者'
              : item.access_level === 'editor'
                ? '编辑者'
                : '查看者'
          }}</span>
        </div>
        <h3>{{ item.name }}</h3>
        <p>{{ item.description || '尚未填写说明，可上传文档后开始构建知识资产。' }}</p>
        <dl>
          <div>
            <dt>文档</dt>
            <dd>{{ documentCounts[item.id] ?? 0 }} 份</dd>
          </div>
          <div>
            <dt>检索</dt>
            <dd>混合检索</dd>
          </div>
        </dl>
        <footer>
          <time>创建于 {{ formatDate(item.created_at) }}</time
          ><button type="button" @click.stop="emit('openDocuments', item.id)">管理文档 →</button>
        </footer>
      </article>
    </div>
    <div v-else class="catalog-empty">
      <span aria-hidden="true">⌕</span>
      <h3>没有匹配的知识库</h3>
      <p>调整搜索条件，或创建一个新的知识空间。</p>
    </div>
  </div>
</template>
