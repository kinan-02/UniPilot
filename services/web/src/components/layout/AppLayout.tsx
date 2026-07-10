import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  BookOpen,
  CalendarDays,
  FlaskConical,
  GraduationCap,
  LayoutDashboard,
  LogOut,
  MessageCircle,
  ScrollText,
  ShieldAlert,
  UserCircle,
} from 'lucide-react'
import { useAuth } from '../../auth/AuthContext'
import { useActiveRecommendationCount } from '../../components/watchdog/WatchdogNudgesCard'
import { useTranslation } from '../../i18n'
import { cn } from '../../lib/utils'
import { Button } from '../ui/Button'
import { LanguageSwitcher } from '../ui/LanguageSwitcher'

export function AppLayout() {
  const { user, logout } = useAuth()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const recommendationCount = useActiveRecommendationCount()
  const isPlannerWorkspace = /^\/plans\/(?:new|[^/]+\/edit)$/.test(location.pathname)

  const navItems = [
    { to: '/', label: t('nav.dashboard'), icon: LayoutDashboard, end: true },
    { to: '/catalog', label: t('nav.catalog'), icon: BookOpen },
    { to: '/transcript', label: t('nav.transcript'), icon: ScrollText },
    { to: '/progress', label: t('nav.progress'), icon: GraduationCap },
    { to: '/plans', label: t('nav.plans'), icon: CalendarDays },
    { to: '/risks', label: t('nav.risks'), icon: ShieldAlert },
    { to: '/simulations', label: t('nav.whatIf'), icon: FlaskConical },
    { to: '/advisor', label: t('nav.advisor'), icon: MessageCircle },
    { to: '/profile', label: t('nav.profile'), icon: UserCircle },
  ]

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen lg:flex">
      <aside className="border-b border-[var(--color-border)] bg-[var(--color-surface)] lg:fixed lg:inset-y-0 lg:flex lg:w-64 lg:flex-col lg:border-b-0 lg:border-e">
        <div className="flex items-center gap-3 px-6 py-5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-primary)] text-sm font-bold text-white">
            UP
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold tracking-tight">{t('app.name')}</p>
            <p className="truncate text-xs text-[var(--color-text-muted)]">{t('app.tagline')}</p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="lg:hidden"
            onClick={handleLogout}
            aria-label={t('nav.signOut')}
          >
            <LogOut className="h-4 w-4" />
          </Button>
        </div>

        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 lg:flex-1 lg:flex-col lg:overflow-visible lg:px-3 lg:pb-6">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'flex shrink-0 items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-[var(--color-primary)] text-white shadow-sm'
                    : 'text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-text)]',
                )
              }
            >
              <Icon className="h-4 w-4" />
              <span className="flex min-w-0 flex-1 items-center gap-2">
                <span className="truncate">{label}</span>
                {to === '/' && recommendationCount > 0 ? (
                  <span
                    className="inline-flex min-w-5 items-center justify-center rounded-full bg-amber-500 px-1.5 py-0.5 text-[10px] font-semibold text-white"
                    data-testid="nav-recommendations-badge"
                    aria-label={t('watchdog.navBadge', { count: recommendationCount })}
                  >
                    {recommendationCount}
                  </span>
                ) : null}
              </span>
            </NavLink>
          ))}
        </nav>

        <div className="hidden border-t border-[var(--color-border)] p-4 lg:block">
          <LanguageSwitcher className="mb-3" />
          <p className="truncate text-xs text-[var(--color-text-muted)]">{user?.email}</p>
          <Button variant="ghost" size="sm" className="mt-2 w-full justify-start" onClick={handleLogout}>
            <LogOut className="h-4 w-4" />
            {t('nav.signOut')}
          </Button>
        </div>
      </aside>

      <main className="flex-1 lg:ps-64">
        <div className="border-b border-[var(--color-border)] px-4 py-3 lg:hidden">
          <LanguageSwitcher />
        </div>
        <div
          className={cn(
            'mx-auto px-3 py-6 sm:px-4 lg:px-6',
            isPlannerWorkspace ? 'max-w-none' : 'max-w-6xl py-8 sm:px-6 lg:px-8',
          )}
        >
          <Outlet />
        </div>
      </main>
    </div>
  )
}
