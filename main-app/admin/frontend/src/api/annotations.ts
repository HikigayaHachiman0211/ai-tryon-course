import request from '../utils/request'

export function listAnnotations(params: Record<string, unknown>) {
  return request.get('/api/admin/annotations', { params })
}

export function getAnnotationStats() {
  return request.get('/api/admin/annotations/stats')
}

export function getAnnotation(productId: number) {
  return request.get(`/api/admin/annotations/${productId}`)
}

export function updateAnnotation(productId: number, data: Record<string, unknown>) {
  return request.put(`/api/admin/annotations/${productId}`, data)
}

export function approveAnnotation(productId: number) {
  return request.post(`/api/admin/annotations/${productId}/approve`)
}

export function rejectAnnotation(productId: number, reason: string) {
  return request.post(`/api/admin/annotations/${productId}/reject`, null, { params: { reason } })
}

export function batchApprove(productIds: number[]) {
  return request.post('/api/admin/annotations/batch-approve', { product_ids: productIds })
}

export function batchAssign(productIds: number[], assignee: string) {
  return request.post('/api/admin/annotations/batch-assign', { product_ids: productIds, assignee })
}

export function batchBrandFix(oldBrand: string, newBrand: string, productIds: number[]) {
  return request.post('/api/admin/annotations/batch-brand-fix', { old_brand: oldBrand, new_brand: newBrand, product_ids: productIds })
}

export function recomputeConfidence() {
  return request.post('/api/admin/annotations/recompute-confidence')
}

export function exportAnnotations(format = 'json') {
  return request.post('/api/admin/annotations/export', null, { params: { format } })
}

export function getQualityReport() {
  return request.get('/api/admin/annotations/quality-report')
}

export function syncDatabaseJson() {
  return request.post('/api/admin/annotations/sync-database-json')
}
