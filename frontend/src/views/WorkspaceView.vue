<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import AnswerPanel from '@/components/AnswerPanel.vue'
import DocumentPanel from '@/components/DocumentPanel.vue'
import KnowledgeSidebar from '@/components/KnowledgeSidebar.vue'
import { createKnowledgeBase, humanizeError, listKnowledgeBases } from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import type { KnowledgeBase } from '@/types/api'

const auth = useAuthStore()
const router = useRouter()
const knowledgeBases = ref<KnowledgeBase[]>([])
const selectedId = ref('')
const loading = ref(false)
const creating = ref(false)
const errorMessage = ref('')

const selected = computed(
  () => knowledgeBases.value.find((item) => item.id === selectedId.value) ?? null,
)

onMounted(loadKnowledgeBases)

async function loadKnowledgeBases(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    knowledgeBases.value = await listKnowledgeBases(auth.token)
    if (!knowledgeBases.value.some((item) => item.id === selectedId.value)) {
      selectedId.value = knowledgeBases.value[0]?.id ?? ''
    }
  } catch (error) {
    errorMessage.value = humanizeError(error)
  } finally {
    loading.value = false
  }
}

async function create(input: { name: string; description: string | null }): Promise<void> {
  creating.value = true
  errorMessage.value = ''
  try {
    const created = await createKnowledgeBase(auth.token, input)
    knowledgeBases.value = [...knowledgeBases.value, created]
    selectedId.value = created.id
  } catch (error) {
    errorMessage.value = humanizeError(error)
  } finally {
    creating.value = false
  }
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
      @select="selectedId = $event"
      @create="create"
    />

    <section class="workspace-main">
      <header class="workspace-header">
        <div>
          <p class="workspace-header__crumb">工作台 / {{ selected?.name ?? '知识库' }}</p>
          <h1>{{ selected?.name ?? '企业知识工作台' }}</h1>
          <p v-if="selected?.description">{{ selected.description }}</p>
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

      <div v-if="selected" class="workspace-grid">
        <DocumentPanel
          :key="`documents-${selected.id}`"
          :token="auth.token"
          :knowledge-base-id="selected.id"
          :access-level="selected.access_level"
        />
        <AnswerPanel
          :key="`answer-${selected.id}`"
          :token="auth.token"
          :knowledge-base-id="selected.id"
          :knowledge-base-name="selected.name"
        />
      </div>

      <div v-else-if="!loading" class="workspace-empty">
        <span aria-hidden="true">知</span>
        <h2>从第一个知识库开始</h2>
        <p>点击左侧“＋”，创建一个用于归档企业资料的安全空间。</p>
      </div>
    </section>
  </main>
</template>
