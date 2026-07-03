import { apiRequest, getApiBaseUrl } from '../lib/api'

export type OutlookConnectionStatus = {
  connected: boolean
  available: boolean
  email?: string | null
  scopes?: string[]
  updatedAt?: string | null
}

export const outlookApi = {
  status: () => apiRequest<OutlookConnectionStatus>('/integrations/outlook/status'),
  disconnect: () =>
    apiRequest<{ disconnected: boolean }>('/integrations/outlook/disconnect', {
      method: 'DELETE',
    }),
}

export function outlookConnectUrl(): string {
  return `${getApiBaseUrl()}/integrations/outlook/connect`
}
