import request from '../utils/request'

export function listProfiles(params: Record<string, unknown>) {
  return request.get('/api/admin/profiles', { params })
}

export function getProfile(id: number) {
  return request.get(`/api/admin/profiles/${id}`)
}

export function getProfileStats() {
  return request.get('/api/admin/profiles/stats')
}

export function getProfileTryonResults(id: number) {
  return request.get(`/api/admin/profiles/${id}/tryon-results`)
}
