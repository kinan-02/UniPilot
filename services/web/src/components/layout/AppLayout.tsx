import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  BookOpen,
  CalendarDays,
  GraduationCap,
  LayoutDashboard,
  LogOut,
  MessageCircle,
  Plug,
  ScrollText,
  ShieldAlert,
  UserCircle,
  Users,
} from 'lucide-react'
import { useAuth } from '../../auth/AuthContext'
import { useTranslation } from '../../i18n'
import { cn } from '../../lib/utils'
import { Button } from '../ui/Button'
import { LanguageSwitcher } from '../ui/LanguageSwitcher'

export function AppLayout() {
  const { user, logout } = useAuth()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const isPlannerWorkspace = /^\/plans\/(?:new|[^/]+\/edit)$/.test(location.pathname)

  const navItems = [
    { to: '/', label: t('nav.dashboard'), icon: LayoutDashboard, end: true },
    { to: '/catalog', label: t('nav.catalog'), icon: BookOpen },
    { to: '/transcript', label: t('nav.transcript'), icon: ScrollText },
    { to: '/progress', label: t('nav.progress'), icon: GraduationCap },
    { to: '/plans', label: t('nav.plans'), icon: CalendarDays },
    { to: '/risks', label: t('nav.risks'), icon: ShieldAlert },
    { to: '/advisor', label: t('nav.advisor'), icon: MessageCircle },
    { to: '/agent', label: t('nav.agents'), icon: Users },
    { to: '/profile', label: t('nav.profile'), icon: UserCircle },
    { to: '/settings/integrations', label: t('nav.integrations'), icon: Plug },
  ]

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="agent-mesh-bg min-h-screen lg:flex text-[var(--color-text)]">
      <aside className="agent-glass m-4 rounded-[var(--radius-2xl)] border border-[var(--color-border)] shadow-card lg:fixed lg:inset-y-4 lg:flex lg:w-64 lg:flex-col z-20">
        <div className="flex items-center gap-3 px-6 py-5">
          <div className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-xl)] bg-gradient-to-br from-[var(--color-primary)] to-[var(--color-accent)] shadow-glow text-sm font-bold text-white transition-transform hover:scale-105">
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
                  'flex shrink-0 items-center gap-2.5 rounded-[var(--radius-xl)] px-3 py-2.5 text-sm font-medium transition-all duration-300',
                  isActive
                    ? 'bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-primary-light)] text-white shadow-glow translate-x-1'
                    : 'text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-text)] hover:shadow-soft',
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="hidden border-t border-[var(--color-border)] p-4 lg:block">
          <LanguageSwitcher className="mb-3" />
          <p className="truncate text-xs text-[var(--color-text-muted)]">{user?.email}</p>
          <Button variant="ghost" size="sm" className="mt-2 w-full justify-start hover:bg-[var(--color-danger)] hover:text-white transition-colors" onClick={handleLogout}>
            <LogOut className="h-4 w-4" />
            {t('nav.signOut')}
          </Button>
        </div>
      </aside>

      <main className="flex-1 lg:ps-[18rem] pt-4 lg:pt-0">
        <div className="agent-glass m-4 rounded-[var(--radius-xl)] px-4 py-3 lg:hidden">
          <LanguageSwitcher />
        </div>
        <div
          className={cn(
            'animate-fade-in mx-auto px-4 py-6 sm:px-6 lg:px-8',
            isPlannerWorkspace ? 'max-w-none' : 'max-w-6xl py-8',
          )}
        >
          <Outlet />
        </div>
      </main>
    </div>
  )
}
