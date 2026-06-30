import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { I18nProvider } from './i18n'
import { AuthProvider } from './auth/AuthContext'
import { AuthQuerySync } from './auth/AuthQuerySync'
import { AppLayout } from './components/layout/AppLayout'
import { LoginPage, RegisterPage } from './pages/AuthPages'
import { GoogleAuthCallbackPage } from './pages/GoogleAuthCallbackPage'
import { OnboardingPage } from './pages/OnboardingPage'
import { DashboardPage } from './pages/DashboardPage'
import { CatalogPage } from './pages/CatalogPage'
import { TranscriptPage } from './pages/TranscriptPage'
import { ProgressPage } from './pages/ProgressPage'
import { PlansPage } from './pages/PlansPage'
import { PlanDetailPage } from './pages/PlanDetailPage'
import { PlanBuilderPage } from './pages/PlanBuilderPage'
import { RisksPage } from './pages/RisksPage'
import { AdvisorPage } from './pages/AdvisorPage'
import { ProfilePage } from './pages/ProfilePage'
import { SharedPlanPage } from './pages/SharedPlanPage'
import { ProtectedRoute, PublicOnlyRoute, ProfileGuard } from './routes/Guards'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
})

export default function App() {
  return (
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <AuthQuerySync />
          <BrowserRouter>
            <Routes>
              <Route element={<PublicOnlyRoute />}>
                <Route path="/login" element={<LoginPage />} />
                <Route path="/register" element={<RegisterPage />} />
              </Route>

              <Route path="/auth/callback" element={<GoogleAuthCallbackPage />} />

              <Route path="/shared/plans/:token" element={<SharedPlanPage />} />

              <Route element={<ProtectedRoute />}>
                <Route path="/onboarding" element={<OnboardingPage />} />
                <Route element={<ProfileGuard />}>
                  <Route element={<AppLayout />}>
                    <Route index element={<DashboardPage />} />
                    <Route path="catalog" element={<CatalogPage />} />
                    <Route path="transcript" element={<TranscriptPage />} />
                    <Route path="progress" element={<ProgressPage />} />
                    <Route path="plans" element={<PlansPage />} />
                    <Route path="plans/new" element={<PlanBuilderPage />} />
                    <Route path="plans/:id/edit" element={<PlanBuilderPage />} />
                    <Route path="plans/:id" element={<PlanDetailPage />} />
                    <Route path="risks" element={<RisksPage />} />
                    <Route path="advisor" element={<AdvisorPage />} />
                    <Route path="profile" element={<ProfilePage />} />
                  </Route>
                </Route>
              </Route>

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    </I18nProvider>
  )
}
