import axios from 'axios'

const request = axios.create({
  baseURL: '',
  timeout: 30000,
})

request.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
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
    return Promise.reject(error)
  },
)

export default request
