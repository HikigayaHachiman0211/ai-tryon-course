import request from '../utils/request'

export function getOverview() {
  return request.get('/api/admin/dashboard/overview')
}

export function getTrends(days = 7) {
  return request.get('/api/admin/dashboard/trends', { params: { days } })
}

export function getTopPreferences() {
  return request.get('/api/admin/dashboard/top-preferences')
}
