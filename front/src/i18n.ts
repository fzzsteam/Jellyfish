import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import zhLayout from './locales/zh-CN/layout.json'
import zhCommon from './locales/zh-CN/common.json'
import zhSettings from './locales/zh-CN/settings.json'
import zhNotFound from './locales/zh-CN/notFound.json'
import enLayout from './locales/en-US/layout.json'
import enCommon from './locales/en-US/common.json'
import enSettings from './locales/en-US/settings.json'
import enNotFound from './locales/en-US/notFound.json'

export type SupportedLanguage = 'zh-CN' | 'en-US'

const resources = {
  'zh-CN': {
    common: zhCommon,
    layout: zhLayout,
    settings: zhSettings,
    notFound: zhNotFound,
  },
  'en-US': {
    common: enCommon,
    layout: enLayout,
    settings: enSettings,
    notFound: enNotFound,
  },
}

i18n.use(initReactI18next).init({
  resources,
  // 项目为中文应用：默认且固定使用简体中文。
  // 不再使用浏览器语言自动检测，避免出现「Antd 中文 / i18n 英文」割裂；
  // 如未来需要多语言切换，再改为由 useAppStore.language 驱动 changeLanguage。
  lng: 'zh-CN',
  fallbackLng: 'zh-CN',
  supportedLngs: ['zh-CN', 'en-US'],
  ns: ['common', 'layout', 'settings', 'notFound'],
  defaultNS: 'layout',
  interpolation: {
    escapeValue: false,
  },
})

export default i18n
