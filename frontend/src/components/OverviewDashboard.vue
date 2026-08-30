<script setup lang="ts">
import { computed } from 'vue'

import type { KnowledgeBase, ReadinessStatus, WorkspaceSection } from '@/types/api'

const props = defineProps<{
  knowledgeBases: KnowledgeBase[]
  documentCounts: Record<string, number>
  readiness: ReadinessStatus | null
  loading: boolean
  userName: string
}>()

const emit = defineEmits<{ navigate: [section: WorkspaceSection] }>()

const totalDocuments = computed(() =>
  Object.values(props.documentCounts).reduce((total, count) => total + count, 0),
)
const ownedKnowledgeBases = computed(
  () => props.knowledgeBases.filter((item) => item.access_level === 'owner').length,
)
const recentKnowledgeBases = computed(() =>
  [...props.knowledgeBases]
    .sort((left, right) => right.created_at.localeCompare(left.created_at))
    .slice(0, 4),
)

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' }).format(
    new Date(value),
  )
}
</script>

<template>
  <div class="overview-page">
    <section class="overview-hero">
      <div>
        <p class="eyebrow eyebrow--light">ENTERPRISE KNOWLEDGE WORKSPACE</p>
        <h2>{{ userName }}，欢迎回来</h2>
        <p>集中管理企业资料、观察索引状态，并通过可追溯引用获得可靠答案。</p>
        <div class="overview-hero__actions">
          <button class="button button--mint" type="button" @click="emit('navigate', 'documents')">
            上传知识文档
          </button>
          <button class="button button--ghost-light" type="button" @click="emit('navigate', 'qa')">
            开始知识问答
          </button>
        </div>
      </div>
      <div class="hero-orbit" aria-hidden="true"><span>知</span><i></i><b></b></div>
    </section>

    <section class="stat-grid" aria-label="知识资产统计">
      <article class="stat-card">
        <span class="stat-card__icon stat-card__icon--green">库</span>
        <div>
          <small>知识空间</small><strong>{{ loading ? '—' : knowledgeBases.length }}</strong>
        </div>
        <p>{{ ownedKnowledgeBases }} 个由我创建</p>
      </article>
      <article class="stat-card">
        <span class="stat-card__icon stat-card__icon--blue">文</span>
        <div>
          <small>已收录文档</small><strong>{{ loading ? '—' : totalDocuments }}</strong>
        </div>
        <p>支持 PDF、DOCX、Markdown</p>
      </article>
      <article class="stat-card">
        <span class="stat-card__icon stat-card__icon--amber">检</span>
        <div><small>检索方式</small><strong>混合</strong></div>
        <p>全文检索 + 向量检索</p>
      </article>
      <article class="stat-card">
        <span
          class="stat-card__icon"
          :class="readiness?.status === 'ready' ? 'stat-card__icon--green' : 'stat-card__icon--red'"
          >服</span
        >
        <div>
          <small>服务状态</small
          ><strong>{{ readiness?.status === 'ready' ? '正常' : '检查中' }}</strong>
        </div>
        <p>数据库 {{ readiness?.checks.database === 'up' ? '已连接' : '等待连接' }}</p>
      </article>
    </section>

    <div class="overview-columns">
      <section class="overview-card overview-card--wide">
        <div class="section-heading">
          <div>
            <p class="eyebrow">KNOWLEDGE SPACES</p>
            <h3>最近知识空间</h3>
          </div>
          <button class="text-button" type="button" @click="emit('navigate', 'knowledge')">
            查看全部 →
          </button>
        </div>
        <div v-if="recentKnowledgeBases.length" class="recent-space-list">
          <button
            v-for="item in recentKnowledgeBases"
            :key="item.id"
            type="button"
            @click="emit('navigate', 'knowledge')"
          >
            <span class="space-monogram">{{ item.name.slice(0, 1) }}</span>
            <span
              ><strong>{{ item.name }}</strong
              ><small>{{ item.description || '尚未填写知识空间说明' }}</small></span
            >
            <span class="space-meta"
              ><strong>{{ documentCounts[item.id] ?? 0 }}</strong
              ><small>份文档</small></span
            >
            <time>{{ formatDate(item.created_at) }}</time>
          </button>
        </div>
        <div v-else class="empty-state empty-state--small">
          <span aria-hidden="true">◇</span><strong>还没有知识空间</strong>
          <p>先创建一个知识库，再上传企业资料。</p>
        </div>
      </section>

      <section class="overview-card">
        <div class="section-heading">
          <div>
            <p class="eyebrow">QUICK START</p>
            <h3>常用工作</h3>
          </div>
        </div>
        <div class="quick-action-list">
          <button type="button" @click="emit('navigate', 'knowledge')">
            <span>01</span><strong>组织知识空间</strong><small>按业务域拆分资料边界</small>
          </button>
          <button type="button" @click="emit('navigate', 'documents')">
            <span>02</span><strong>导入与索引</strong><small>跟踪解析、分块和向量化</small>
          </button>
          <button type="button" @click="emit('navigate', 'qa')">
            <span>03</span><strong>验证问答效果</strong><small>检查回答和来源引用</small>
          </button>
        </div>
      </section>
    </div>

    <section class="pipeline-card">
      <div>
        <p class="eyebrow">INGESTION PIPELINE</p>
        <h3>知识进入系统的路径</h3>
      </div>
      <ol>
        <li><span>1</span><strong>文件校验</strong><small>格式与大小</small></li>
        <li><span>2</span><strong>内容解析</strong><small>提取结构化文本</small></li>
        <li><span>3</span><strong>语义分块</strong><small>保留上下文边界</small></li>
        <li><span>4</span><strong>生成向量</strong><small>建立语义表示</small></li>
        <li><span>5</span><strong>混合索引</strong><small>等待检索与问答</small></li>
      </ol>
    </section>
  </div>
</template>
