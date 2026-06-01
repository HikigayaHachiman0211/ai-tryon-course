import request from '../utils/request'

export function listImages(params: Record<string, unknown>) {
  return request.get('/api/admin/images', { params })
}

export function uploadImage(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request.post('/api/admin/images/upload', form)
}

export function deleteImage(name: string) {
  return request.delete('/api/admin/images', { params: { name } })
}

export function getOrphans() {
  return request.get('/api/admin/images/orphans')
}
