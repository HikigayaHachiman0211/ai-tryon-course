import request from '../utils/request'

export function listPrompts(params?: { category?: string; prompt_type?: string; is_active?: boolean; keyword?: string }) {
  return request.get('/api/admin/prompts', { params })
}

export function getPrompt(id: number) {
  return request.get(`/api/admin/prompts/${id}`)
}

export function updatePrompt(id: number, data: Record<string, unknown>) {
  return request.put(`/api/admin/prompts/${id}`, data)
}

export function testPrompt(id: number, testParams: Record<string, string>) {
  return request.post(`/api/admin/prompts/${id}/test`, { test_params: testParams })
}

export function previewPrompt(content: string, variables: Record<string, string>) {
  return request.post('/api/admin/prompts/preview', { content, variables })
}

export function getVersions(id: number) {
  return request.get(`/api/admin/prompts/${id}/versions`)
}

export function diffVersions(id: number, v1: number, v2: number) {
  return request.get(`/api/admin/prompts/${id}/diff`, { params: { v1, v2 } })
}

export function restoreDefault(id: number) {
  return request.post(`/api/admin/prompts/${id}/restore-default`)
}
