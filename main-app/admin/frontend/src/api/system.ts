import request from '../utils/request'

export function getHealth() {
  return request.get('/api/admin/system/health')
}

export function getErrors() {
  return request.get('/api/admin/system/errors')
}

export function getConfig() {
  return request.get('/api/admin/system/config')
}

export function getDbStats() {
  return request.get('/api/admin/system/db-stats')
}
