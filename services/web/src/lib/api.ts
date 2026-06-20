const TOKEN_KEY = 'unipilot_access_token'

export function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_URL ?? '/api'
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setStoredToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
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

  const authToken = token ?? getStoredToken()
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`
  }

  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
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
