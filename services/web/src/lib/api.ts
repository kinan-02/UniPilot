const TOKEN_KEY = 'unipilot_access_token'

/** @deprecated Tokens are stored in httpOnly cookies; kept for backward-compatible tests. */
export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

/** @deprecated Tokens are stored in httpOnly cookies; kept for backward-compatible tests. */
export function setStoredToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

export function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_URL ?? '/api'
}

export type ApiEnvelope<T> = {
  success: boolean
  data: T | null
  error: string | null
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

type RequestOptions = {
  method?: string
  body?: unknown
  token?: string | null
  signal?: AbortSignal
}

export async function apiRequest<T>(
  path: string,
  { method = 'GET', body, token, signal }: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
    credentials: 'include',
  })

  let payload: ApiEnvelope<T> | null = null
  try {
    payload = (await response.json()) as ApiEnvelope<T>
  } catch {
    payload = null
  }

  if (!response.ok || !payload?.success) {
    const message =
      payload?.error ??
      (response.status === 429
        ? 'Too many requests. Please wait a moment.'
        : `Request failed (${response.status})`)
    throw new ApiError(message, response.status)
  }

  return payload.data as T
}

export async function logoutRequest(): Promise<void> {
  await apiRequest<{ loggedOut: boolean }>('/auth/logout', { method: 'POST', token: null })
}

export async function refreshSessionRequest(): Promise<void> {
  await apiRequest<{ accessToken: string; user: unknown }>('/auth/refresh', {
    method: 'POST',
    token: null,
  })
}
