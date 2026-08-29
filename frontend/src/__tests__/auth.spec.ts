import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getCurrentUser, loginUser } from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import type { TokenResponse, User } from '@/types/api'

vi.mock('@/services/api', () => ({
  getCurrentUser: vi.fn<(token: string) => Promise<User>>(),
  loginUser: vi.fn<(email: string, password: string) => Promise<TokenResponse>>(),
}))

const user = {
  id: 'user-1',
  email: 'dawn@example.com',
  display_name: 'Dawn',
  is_active: true,
  roles: ['member'],
  created_at: '2026-08-28T00:00:00Z',
}

describe('authentication store', () => {
  beforeEach(() => {
    sessionStorage.clear()
    setActivePinia(createPinia())
    vi.mocked(loginUser).mockReset()
    vi.mocked(getCurrentUser).mockReset()
  })

  it('stores a successful login only in session storage', async () => {
    vi.mocked(loginUser).mockResolvedValue({
      access_token: 'token-1',
      token_type: 'bearer',
      expires_in: 1800,
    })
    vi.mocked(getCurrentUser).mockResolvedValue(user)
    const auth = useAuthStore()

    await auth.login('dawn@example.com', 'password')

    expect(auth.isAuthenticated).toBe(true)
    expect(auth.user?.display_name).toBe('Dawn')
    expect(sessionStorage.getItem('enterprise-rag-access-token')).toBe('token-1')
    expect(localStorage.getItem('enterprise-rag-access-token')).toBeNull()
  })

  it('clears an expired restored session', async () => {
    sessionStorage.setItem('enterprise-rag-access-token', 'expired-token')
    vi.mocked(getCurrentUser).mockRejectedValue(new Error('expired'))
    setActivePinia(createPinia())
    const auth = useAuthStore()

    await auth.restore()

    expect(auth.token).toBe('')
    expect(auth.user).toBeNull()
    expect(sessionStorage.getItem('enterprise-rag-access-token')).toBeNull()
  })

  it('rolls back a token when loading the current user fails after login', async () => {
    vi.mocked(loginUser).mockResolvedValue({
      access_token: 'token-2',
      token_type: 'bearer',
      expires_in: 1800,
    })
    vi.mocked(getCurrentUser).mockRejectedValue(new Error('profile unavailable'))
    const auth = useAuthStore()

    await expect(auth.login('dawn@example.com', 'password')).rejects.toThrow('profile unavailable')

    expect(auth.token).toBe('')
    expect(sessionStorage.getItem('enterprise-rag-access-token')).toBeNull()
  })
})
