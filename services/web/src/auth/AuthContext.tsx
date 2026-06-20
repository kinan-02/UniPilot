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
import { ApiError, setStoredToken, getStoredToken } from '../lib/api'
import type { User } from '../types/api'

type AuthContextValue = {
  user: User | null
  token: string | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(() => getStoredToken())
  const [isLoading, setIsLoading] = useState(Boolean(getStoredToken()))

  useEffect(() => {
    if (!token) {
      setIsLoading(false)
      return
    }

    let cancelled = false
    authApi
      .me()
      .then((data) => {
        if (!cancelled) setUser(data.user)
      })
      .catch(() => {
        if (!cancelled) {
          setStoredToken(null)
          setToken(null)
          setUser(null)
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [token])

  const applyAuth = useCallback((accessToken: string, nextUser: User) => {
    setStoredToken(accessToken)
    setToken(accessToken)
    setUser(nextUser)
  }, [])

  const login = useCallback(
    async (email: string, password: string) => {
      const data = await authApi.login(email, password)
      applyAuth(data.accessToken, data.user)
    },
    [applyAuth],
  )

  const register = useCallback(
    async (email: string, password: string) => {
      const data = await authApi.register(email, password)
      applyAuth(data.accessToken, data.user)
    },
    [applyAuth],
  )

  const logout = useCallback(() => {
    setStoredToken(null)
    setToken(null)
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, token, isLoading, login, register, logout }),
    [user, token, isLoading, login, register, logout],
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
