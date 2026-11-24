import request from '../utils/request'

export type RecoveryMethod = 'security_question' | 'recovery_key'

export interface RecoveryOptionsResponse {
  has_security_question: boolean
  security_question: string | null
  has_recovery_key: boolean
}

export function login(username: string, password: string) {
  return request.post('/api/auth/login', { username, password })
}

export function getMe() {
  return request.get('/api/auth/me')
}

export function changePassword(current_password: string, new_password: string) {
  return request.post('/api/auth/change-password', { current_password, new_password })
}

export function getRecoveryOptions(username: string) {
  return request.get<RecoveryOptionsResponse>('/api/auth/recovery-options', { params: { username } })
}

export function resetPassword(payload: {
  username: string
  method: RecoveryMethod
  proof: string
  new_password: string
}) {
  return request.post('/api/auth/reset-password', payload)
}

export function saveRecoveryQuestion(payload: {
  current_password: string
  security_question: string
  security_answer: string
}) {
  return request.post('/api/auth/recovery-question', payload)
}
