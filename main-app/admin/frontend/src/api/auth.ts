import request from '../utils/request'

export function login(username: string, password: string) {
  return request.post('/api/auth/login', { username, password })
}

export function getMe() {
  return request.get('/api/auth/me')
}

export function changePassword(old_password: string, new_password: string) {
  return request.post('/api/auth/change-password', { old_password, new_password })
}
