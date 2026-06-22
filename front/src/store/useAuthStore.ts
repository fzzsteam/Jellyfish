import { create } from 'zustand'
import { AuthService } from '../services/generated'
import type { UserRead } from '../services/generated'

const REFRESH_TOKEN_KEY = 'jellyfish_refresh_token'

type AuthStatus = 'idle' | 'authenticated' | 'unauthenticated'

interface AuthState {
  status: AuthStatus
  user: UserRead | null
  accessToken: string | null
  refreshToken: string | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  refreshAccessToken: () => Promise<string | null>
  initialize: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set, get) => ({
  status: 'idle',
  user: null,
  accessToken: null,
  refreshToken: localStorage.getItem(REFRESH_TOKEN_KEY),

  login: async (username, password) => {
    const res = await AuthService.loginApiV1AuthLoginPost({ requestBody: { username, password } })
    const tokens = res.data
    if (!tokens) throw new Error('登录响应缺少令牌')
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
    set({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token })
    const me = await AuthService.getMeApiV1AuthMeGet({})
    set({ user: me.data ?? null, status: 'authenticated' })
  },

  logout: () => {
    localStorage.removeItem(REFRESH_TOKEN_KEY)
    set({ user: null, accessToken: null, refreshToken: null, status: 'unauthenticated' })
  },

  refreshAccessToken: async () => {
    const refreshToken = get().refreshToken
    if (!refreshToken) {
      get().logout()
      return null
    }
    try {
      const res = await AuthService.refreshApiV1AuthRefreshPost({ requestBody: { refresh_token: refreshToken } })
      const accessToken = res.data?.access_token
      if (!accessToken) throw new Error('刷新响应缺少 access_token')
      set({ accessToken })
      return accessToken
    } catch {
      get().logout()
      return null
    }
  },

  initialize: async () => {
    const refreshToken = get().refreshToken
    if (!refreshToken) {
      set({ status: 'unauthenticated' })
      return
    }
    const accessToken = await get().refreshAccessToken()
    if (!accessToken) return
    try {
      const me = await AuthService.getMeApiV1AuthMeGet({})
      set({ user: me.data ?? null, status: 'authenticated' })
    } catch {
      get().logout()
    }
  },
}))
