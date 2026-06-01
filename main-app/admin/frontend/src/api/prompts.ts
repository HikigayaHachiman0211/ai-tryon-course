import request from '../utils/request'

export function listPrompts() {
  return request.get('/api/admin/prompts')
}

export function getPrompt(id: number) {
  return request.get(`/api/admin/prompts/${id}`)
}

export function updatePrompt(id: number, data: Record<string, unknown>) {
  return request.put(`/api/admin/prompts/${id}`, data)
}

export function testPrompt(id: number, variables: Record<string, string>) {
  return request.post(`/api/admin/prompts/${id}/test`, { variables })
}

export function getVersions(id: number) {
  return request.get(`/api/admin/prompts/${id}/versions`)
}

export function diffVersions(id: number, v1: number, v2: number) {
  return request.get(`/api/admin/prompts/${id}/diff`, { params: { v1, v2 } })
}
