import zhCN from 'antd/locale/zh_CN'
import enUS from 'antd/locale/en_US'
import jaJP from 'antd/locale/ja_JP'
import type { AppLocale } from './locale'

export const antdLocales = { 'zh-CN': zhCN, en: enUS, ja: jaJP } as const
export const dayjsLocales: Record<AppLocale, string> = { 'zh-CN': 'zh-cn', en: 'en', ja: 'ja' }
