import request from '../utils/request'

export function listHistory(params: Record<string, unknown>) {
  return request.get('/api/admin/history', { params })
}

export function getHistory(id: string) {
  return request.get(`/api/admin/history/${id}`)
}

export function deleteHistory(id: string) {
  return request.delete(`/api/admin/history/${id}`)
}
