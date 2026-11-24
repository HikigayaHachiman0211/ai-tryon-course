import axios from 'axios'
import { detectInitialLocale } from '../i18n/locale'

const request = axios.create({
  baseURL: '',
  timeout: 30000,
})

request.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  config.headers['Accept-Language'] = detectInitialLocale()
  return config
})

request.interceptors.response.use(
  (response) => response,
  (error) => {
    const isLoginRequest = error.config?.url === '/api/auth/login'
    if (error.response?.status === 401 && !isLoginRequest) {
      localStorage.removeItem('admin_token')
      window.location.hash = ''
      window.location.href = '/login'
    }
    if (error.response?.data && typeof error.response.data === 'object') {
      const body = error.response.data as { code?: string; request_id?: string }
      error.code = body.code || error.code
      error.requestId = body.request_id
    }
    return Promise.reject(error)
  },
)

export default request
