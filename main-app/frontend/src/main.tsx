import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { i18nReady } from './i18n'
import './index.css'
import App from './App.tsx'

const root = createRoot(document.getElementById('root')!)
const renderApp = () => root.render(
  <StrictMode>
    <App />
  </StrictMode>,
)

root.render(<div className="app-loading-fallback">AI 羽绒服推荐平台 · 加载中...</div>)
void i18nReady.then(renderApp).catch(() => renderApp())
