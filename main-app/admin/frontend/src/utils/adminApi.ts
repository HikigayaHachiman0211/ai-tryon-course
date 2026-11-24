export type AdminApiEnv = {
  VITE_ADMIN_API_BASE_URL?: string
  VITE_ADMIN_API_URL?: string
}

export function resolveAdminApiBaseUrl(env: AdminApiEnv): string {
  return (env.VITE_ADMIN_API_BASE_URL || env.VITE_ADMIN_API_URL || '').trim()
}
