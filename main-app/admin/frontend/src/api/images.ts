import request from '../utils/request'

export type BlobScope = 'products' | 'samples' | 'media'

export function listImages(params: Record<string, unknown>) {
  return request.get('/api/admin/images', { params })
}

export function uploadImage(file: File, scope: BlobScope = 'products') {
  const form = new FormData()
  form.append('file', file)
  return request.post('/api/admin/images/upload', form, { params: { scope } })
}

export function deleteImage(name: string, scope: BlobScope = 'products') {
  return request.delete('/api/admin/images', { params: { name, scope } })
}

export function getOrphans(params?: { refresh?: boolean }) {
  return request.get('/api/admin/images/orphans', { params })
}
