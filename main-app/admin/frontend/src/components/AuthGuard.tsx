import { Navigate, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

export default function AuthGuard({ children }: { children: ReactNode }) {
  useTranslation('common')
  const location = useLocation()
  const token = localStorage.getItem('admin_token')

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }
  return <>{children}</>
}
