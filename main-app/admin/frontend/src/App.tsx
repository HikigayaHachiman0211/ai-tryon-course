import { Routes, Route, Navigate } from 'react-router-dom'
import AuthGuard from './components/AuthGuard'
import AdminLayout from './components/AdminLayout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import ProductsPage from './pages/ProductsPage'
import ProductEditPage from './pages/ProductEditPage'
import HistoryPage from './pages/HistoryPage'
import SystemPage from './pages/SystemPage'
import ImagesPage from './pages/ImagesPage'
import TryonTasksPage from './pages/TryonTasksPage'
import PromptsPage from './pages/PromptsPage'
import AnnotationsPage from './pages/AnnotationsPage'
import ProfilesPage from './pages/ProfilesPage'
import SampleModelsPage from './pages/SampleModelsPage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <AuthGuard>
            <AdminLayout />
          </AuthGuard>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/products" element={<ProductsPage />} />
        <Route path="/products/:id" element={<ProductEditPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/system" element={<SystemPage />} />
        <Route path="/images" element={<ImagesPage />} />
        <Route path="/tryon-tasks" element={<TryonTasksPage />} />
        <Route path="/prompts" element={<PromptsPage />} />
        <Route path="/annotations" element={<AnnotationsPage />} />
        <Route path="/profiles" element={<ProfilesPage />} />
        <Route path="/sample-models" element={<SampleModelsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
