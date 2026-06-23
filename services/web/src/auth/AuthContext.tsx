import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { authApi } from '../api/endpoints'
import { ApiError, logoutRequest } from '../lib/api'
import type { User } from '../types/api'

type AuthContextValue = {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (email: string, password: string, rememberMe?: boolean) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    authApi
      .me()
      .then((data) => {
        if (!cancelled) setUser(data.user)
      })
      .catch(() => {
        if (!cancelled) setUser(null)
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const applyAuth = useCallback((nextUser: User) => {
    setUser(nextUser)
  }, [])

  const refreshUser = useCallback(async () => {
    const data = await authApi.me()
    applyAuth(data.user)
  }, [applyAuth])

  const login = useCallback(
    async (email: string, password: string, rememberMe = false) => {
      const data = await authApi.login(email, password, rememberMe)
      applyAuth(data.user)
    },
    [applyAuth],
  )

  const register = useCallback(
    async (email: string, password: string) => {
      const data = await authApi.register(email, password)
      applyAuth(data.user)
    },
    [applyAuth],
  )

  const logout = useCallback(async () => {
    try {
      await logoutRequest()
    } finally {
      setUser(null)
    }
  }, [])

  const value = useMemo(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      isLoading,
      login,
      register,
      logout,
      refreshUser,
    }),
    [user, isLoading, login, register, logout, refreshUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

export function isAuthError(error: unknown): error is ApiError {
  return error instanceof ApiError
}
