<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import AuthShell from '@/components/AuthShell.vue'
import { humanizeError } from '@/services/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const email = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')

async function submit(): Promise<void> {
  errorMessage.value = ''
  submitting.value = true
  try {
    await auth.login(email.value.trim(), password.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/app'
    await router.replace(redirect)
  } catch (error) {
    errorMessage.value = humanizeError(error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthShell>
    <p class="eyebrow">WELCOME BACK</p>
    <h2>登录工作台</h2>
    <p class="auth-form-card__intro">使用企业账号继续访问你的知识库。</p>

    <div v-if="errorMessage" class="alert alert--error" role="alert">{{ errorMessage }}</div>

    <form class="form-stack" @submit.prevent="submit">
      <label class="field">
        <span>邮箱</span>
        <input
          v-model="email"
          name="email"
          type="email"
          autocomplete="email"
          required
          placeholder="name@company.com"
        />
      </label>
      <label class="field">
        <span>密码</span>
        <input
          v-model="password"
          name="password"
          type="password"
          autocomplete="current-password"
          required
          placeholder="输入你的密码"
        />
      </label>
      <button class="button button--primary button--wide" type="submit" :disabled="submitting">
        <span v-if="submitting" class="spinner" aria-hidden="true"></span>
        {{ submitting ? '正在验证…' : '登录' }}
      </button>
    </form>

    <p class="auth-switch">还没有账号？<RouterLink to="/register">创建账号</RouterLink></p>
    <p class="security-hint"><span aria-hidden="true">◇</span> 访问令牌只保留在当前浏览器标签页</p>
  </AuthShell>
</template>
