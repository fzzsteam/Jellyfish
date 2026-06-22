import { OpenAPI } from './generated'
import { useAuthStore } from '../store/useAuthStore'

declare global {
  interface Window {
    __ENV?: {
      BACKEND_URL?: string
    }
  }
}

/**
 * 初始化由 OpenAPI 生成的请求客户端。
 *
 * 说明：
 * - 生成接口的路径已包含 `/api/v1/...`，因此 BASE 默认应为空串（同源）或完整后端地址。
 * - 本地开发默认直连 `http://localhost:8000`。
 */
export function initOpenAPI(base: string = '') {
  OpenAPI.BASE = base
  OpenAPI.TOKEN = async () => useAuthStore.getState().accessToken ?? ''
}

const AUTH_PATH_PREFIX = '/api/v1/auth/'

function installFetchInterceptor() {
  const originalFetch = window.fetch.bind(window)

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await originalFetch(input, init)
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url

    if (response.status === 401 && !url.includes(AUTH_PATH_PREFIX)) {
      const newToken = await useAuthStore.getState().refreshAccessToken()
      if (newToken) {
        const retryHeaders = new Headers(init?.headers)
        retryHeaders.set('Authorization', `Bearer ${newToken}`)
        return originalFetch(input, { ...init, headers: retryHeaders })
      }
    }

    return response
  }
}

const runtimeBackendUrl = window.__ENV?.BACKEND_URL
const buildtimeBackendUrl = import.meta.env.VITE_BACKEND_URL
const defaultBackendUrl = 'http://localhost:8000'

initOpenAPI(runtimeBackendUrl ?? buildtimeBackendUrl ?? defaultBackendUrl)
installFetchInterceptor()
