<script setup lang="ts">
import { ref, watch } from 'vue'

import { humanizeError, streamAnswer } from '@/services/api'
import type { AnswerCitation } from '@/types/api'

const props = defineProps<{ token: string; knowledgeBaseId: string; knowledgeBaseName: string }>()

const question = ref('')
const answering = ref(false)
const answer = ref('')
const citations = ref<AnswerCitation[]>([])
const model = ref('')
const refused = ref(false)
const errorMessage = ref('')

watch(
  () => props.knowledgeBaseId,
  () => {
    question.value = ''
    answer.value = ''
    citations.value = []
    model.value = ''
    refused.value = false
    errorMessage.value = ''
  },
)

async function ask(): Promise<void> {
  const cleaned = question.value.trim()
  if (cleaned.length < 2 || answering.value) return
  answering.value = true
  answer.value = ''
  citations.value = []
  model.value = ''
  refused.value = false
  errorMessage.value = ''
  try {
    const result = await streamAnswer(props.token, props.knowledgeBaseId, cleaned, (delta) => {
      answer.value += delta
    })
    citations.value = result.citations
    model.value = result.model
    refused.value = result.refused
  } catch (error) {
    errorMessage.value = humanizeError(error)
  } finally {
    answering.value = false
  }
}

function useSuggestion(value: string): void {
  question.value = value
}
</script>

<template>
  <section class="panel answer-panel" aria-labelledby="answer-title">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">GROUNDED ANSWER</p>
        <h2 id="answer-title">向知识库提问</h2>
      </div>
      <span class="model-badge"><i aria-hidden="true"></i> DeepSeek</span>
    </div>

    <div v-if="errorMessage" class="alert alert--error" role="alert">{{ errorMessage }}</div>

    <div v-if="!answer && !answering" class="answer-welcome">
      <div class="answer-orb" aria-hidden="true"><span>知</span></div>
      <h3>我会依据“{{ knowledgeBaseName }}”中的内容回答</h3>
      <p>每个结论都应带有来源编号；资料不足时会明确拒答。</p>
      <div class="suggestions">
        <button type="button" @click="useSuggestion('请总结这份知识库的核心内容')">
          总结核心内容
        </button>
        <button type="button" @click="useSuggestion('有哪些需要特别注意的规定？')">
          查找重要规定
        </button>
      </div>
    </div>

    <div
      v-else
      class="answer-result"
      :class="{ 'answer-result--refused': refused }"
      aria-live="polite"
    >
      <div class="answer-result__label">
        <span class="answer-avatar" aria-hidden="true">知</span>
        <span
          ><strong>知识助手</strong><small>{{ model || '正在组织答案…' }}</small></span
        >
      </div>
      <p class="answer-copy">
        {{ answer }}<span v-if="answering" class="typing-caret" aria-hidden="true"></span>
      </p>

      <div v-if="citations.length" class="citation-list">
        <p class="citation-list__heading">来源依据 · {{ citations.length }}</p>
        <details v-for="citation in citations" :key="citation.chunk_id">
          <summary>
            <span class="citation-number">{{ citation.citation }}</span>
            <span
              ><strong>{{ citation.document_title }}</strong
              ><small
                >{{ citation.original_filename }} · 版本 {{ citation.version_number }}</small
              ></span
            >
            <span aria-hidden="true">⌄</span>
          </summary>
          <blockquote>{{ citation.quoted_text }}</blockquote>
        </details>
      </div>
    </div>

    <form class="question-box" @submit.prevent="ask">
      <label>
        <span class="sr-only">输入问题</span>
        <textarea
          v-model="question"
          rows="3"
          minlength="2"
          maxlength="500"
          required
          placeholder="输入你想了解的问题…"
          @keydown.ctrl.enter="ask"
        ></textarea>
      </label>
      <div class="question-box__footer">
        <small>{{ question.length }}/500 · Ctrl + Enter 发送</small>
        <button
          class="send-button"
          type="submit"
          :disabled="answering || question.trim().length < 2"
          aria-label="发送问题"
        >
          <span v-if="answering" class="spinner" aria-hidden="true"></span
          ><span v-else aria-hidden="true">↑</span>
        </button>
      </div>
    </form>
  </section>
</template>
