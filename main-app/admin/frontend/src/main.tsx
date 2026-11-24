import React, { useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import { createRoot, type Root } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { App as AntdApp, ConfigProvider, unstableSetRender } from 'antd'
import dayjs from 'dayjs'
import App from './App'
import './index.css'
import adminI18n, { adminI18nReady } from './i18n'
import { antdLocales, dayjsLocales } from './i18n/antdLocale'
import { DEFAULT_LOCALE, type AppLocale } from './i18n/locale'

// Ant Design v5 static message/notification/modal helpers rely on ReactDOM.render
// unless unstableSetRender is wired to react-dom/client createRoot under React 19.
unstableSetRender((node, container) => {
  const containerWithRoot = container as (Element | DocumentFragment) & { _reactRoot?: Root }
  containerWithRoot._reactRoot ||= createRoot(container)
  const root = containerWithRoot._reactRoot
  root.render(node)
  return async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
    root.unmount()
  }
})

const theme = {
  token: {
    colorPrimary: '#0071e3',
    borderRadius: 10,
    fontFamily: '-apple-system, "SF Pro Display", "SF Pro Text", "Helvetica Neue", Arial, sans-serif',
    colorBgLayout: '#f5f5f7',
    colorBgContainer: '#ffffff',
    colorText: '#1d1d1f',
  },
}

function AdminRoot() {
  const [language, setLanguage] = useState(adminI18n.language)
  useEffect(() => {
    const update = (next: string) => setLanguage(next)
    adminI18n.on('languageChanged', update)
    return () => { adminI18n.off('languageChanged', update) }
  }, [])
  const locale = (language as AppLocale) in antdLocales ? language as AppLocale : DEFAULT_LOCALE
  dayjs.locale(dayjsLocales[locale])
  return (
    <React.StrictMode>
      <ConfigProvider theme={theme} locale={antdLocales[locale]}>
        <AntdApp>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </AntdApp>
      </ConfigProvider>
    </React.StrictMode>
  )
}

void adminI18nReady.then(() => {
  ReactDOM.createRoot(document.getElementById('root')!).render(<AdminRoot />)
})
