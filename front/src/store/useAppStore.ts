import { create } from 'zustand'
import type { SupportedLanguage } from '../i18n'

interface AppState {
  siderCollapsed: boolean
  language: SupportedLanguage
  setLanguage: (lang: SupportedLanguage) => void
  toggleSider: () => void
}

export const useAppStore = create<AppState>((set) => ({
  siderCollapsed: false,
  language: 'zh-CN',
  setLanguage: (lang) => set(() => ({ language: lang })),
  toggleSider: () =>
    set((state) => ({
      siderCollapsed: !state.siderCollapsed,
    })),
}))
