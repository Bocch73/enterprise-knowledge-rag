import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { getCurrentUser, loginUser } from '@/services/api'
import type { User } from '@/types/api'

const TOKEN_KEY = 'enterprise-rag-access-token'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(sessionStorage.getItem(TOKEN_KEY) ?? '')
  const user = ref<User | null>(null)
  const isAuthenticated = computed(() => Boolean(token.value && user.value))

  async function login(email: string, password: string): Promise<void> {
    const response = await loginUser(email, password)
    token.value = response.access_token
    sessionStorage.setItem(TOKEN_KEY, token.value)
    try {
      user.value = await getCurrentUser(token.value)
    } catch (error) {
      logout()
      throw error
    }
  }

  async function restore(): Promise<void> {
    if (!token.value) return
    try {
      user.value = await getCurrentUser(token.value)
    } catch {
      logout()
    }
  }

  function logout(): void {
    token.value = ''
    user.value = null
    sessionStorage.removeItem(TOKEN_KEY)
  }

  return { token, user, isAuthenticated, login, restore, logout }
})
