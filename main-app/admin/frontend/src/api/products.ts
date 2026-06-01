import request from '../utils/request'

export function listProducts(params: Record<string, unknown>) {
  return request.get('/api/admin/products', { params })
}

export function getProduct(id: number) {
  return request.get(`/api/admin/products/${id}`)
}

export function createProduct(data: Record<string, unknown>) {
  return request.post('/api/admin/products', data)
}

export function updateProduct(id: number, data: Record<string, unknown>) {
  return request.put(`/api/admin/products/${id}`, data)
}

export function deleteProduct(id: number) {
  return request.delete(`/api/admin/products/${id}`)
}

export function batchDelete(ids: number[]) {
  return request.post('/api/admin/products/batch-delete', { ids })
}

export function importProducts(data: Record<string, unknown>[]) {
  return request.post('/api/admin/products/import-json', data)
}

export function uploadImage(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request.post('/api/admin/products/upload-image', form)
}

export function getMissingLinks() {
  return request.get('/api/admin/products/missing-links')
}

export function importLinks(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request.post('/api/admin/products/import-links', form)
}

export function validateLinks(ids: number[]) {
  return request.post('/api/admin/products/validate-links', { product_ids: ids })
}
