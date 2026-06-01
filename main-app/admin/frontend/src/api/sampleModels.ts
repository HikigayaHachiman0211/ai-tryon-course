import request from '../utils/request'

export function listSampleModels(params: Record<string, unknown>) {
  return request.get('/api/admin/sample-models', { params })
}

export function getSampleModel(id: number) {
  return request.get(`/api/admin/sample-models/${id}`)
}

export function uploadSampleModel(formData: FormData) {
  return request.post('/api/admin/sample-models/upload', formData)
}

export function updateSampleModel(id: number, data: Record<string, unknown>) {
  return request.put(`/api/admin/sample-models/${id}`, data)
}

export function replaceModelImage(id: number, file: File) {
  const form = new FormData()
  form.append('image', file)
  return request.put(`/api/admin/sample-models/${id}/replace-image`, form)
}

export function deleteSampleModel(id: number) {
  return request.delete(`/api/admin/sample-models/${id}`)
}

export function batchDeleteModels(ids: number[]) {
  return request.delete('/api/admin/sample-models/batch', { data: { ids } })
}

export function reorderModels(items: { id: number; display_order: number }[]) {
  return request.put('/api/admin/sample-models/reorder', { items })
}

export function batchStatus(ids: number[], is_active: boolean) {
  return request.put('/api/admin/sample-models/batch-status', { ids, is_active })
}
