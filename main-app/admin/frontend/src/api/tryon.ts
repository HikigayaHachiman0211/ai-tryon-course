import request from '../utils/request'

export function listTasks(params: Record<string, unknown>) {
  return request.get('/api/admin/tryon-tasks', { params })
}

export function getTaskStats() {
  return request.get('/api/admin/tryon-tasks/stats')
}

export function getTask(id: string) {
  return request.get(`/api/admin/tryon-tasks/${id}`)
}

export function retryTask(id: string) {
  return request.post(`/api/admin/tryon-tasks/${id}/retry`)
}
