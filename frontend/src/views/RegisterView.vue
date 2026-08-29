<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'

import AuthShell from '@/components/AuthShell.vue'
import { humanizeError, registerUser } from '@/services/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const displayName = ref('')
const email = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')

async function submit(): Promise<void> {
  errorMessage.value = ''
  if (password.value.length < 12) {
    errorMessage.value = '密码至少需要 12 个字符。'
    return
  }
  submitting.value = true
  try {
    await registerUser({
      display_name: displayName.value.trim(),
      email: email.value.trim(),
      password: password.value,
    })
    await auth.login(email.value.trim(), password.value)
    await router.replace('/app')
  } catch (error) {
    errorMessage.value = humanizeError(error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthShell>
    <p class="eyebrow">GET STARTED</p>
    <h2>创建你的账号</h2>
    <p class="auth-form-card__intro">从一个独立、安全的知识库开始。</p>

    <div v-if="errorMessage" class="alert alert--error" role="alert">{{ errorMessage }}</div>

    <form class="form-stack" @submit.prevent="submit">
      <label class="field">
        <span>显示名称</span>
        <input
          v-model="displayName"
          name="displayName"
          minlength="2"
          maxlength="100"
          required
          placeholder="例如：Dawn"
        />
      </label>
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
          autocomplete="new-password"
          minlength="12"
          maxlength="128"
          required
          placeholder="至少 12 个字符"
        />
      </label>
      <button class="button button--primary button--wide" type="submit" :disabled="submitting">
        <span v-if="submitting" class="spinner" aria-hidden="true"></span>
        {{ submitting ? '正在创建…' : '创建并登录' }}
      </button>
    </form>

    <p class="auth-switch">已经有账号？<RouterLink to="/login">返回登录</RouterLink></p>
  </AuthShell>
</template>
