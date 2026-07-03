import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { IntegrationsPage } from './IntegrationsPage'
import { I18nProvider } from '../i18n'

const { statusMock, disconnectMock } = vi.hoisted(() => ({
  statusMock: vi.fn(),
  disconnectMock: vi.fn(),
}))

vi.mock('../api/outlook', () => ({
  outlookApi: {
    status: statusMock,
    disconnect: disconnectMock,
  },
  outlookConnectUrl: () => '/api/integrations/outlook/connect',
}))

function renderPage(initialEntry = '/settings/integrations') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <IntegrationsPage />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

describe('IntegrationsPage', () => {
  beforeEach(() => {
    statusMock.mockReset()
    disconnectMock.mockReset()
    vi.stubGlobal('location', { assign: vi.fn() })
  })

  it('renders connect when Outlook is available but not connected', async () => {
    statusMock.mockResolvedValue({ connected: false, available: true, scopes: [] })
    renderPage()

    expect(await screen.findByTestId('integrations-page')).toBeInTheDocument()
    expect(screen.getByTestId('outlook-connect')).toBeInTheDocument()
  })

  it('renders connected state with disconnect action', async () => {
    statusMock.mockResolvedValue({
      connected: true,
      available: true,
      email: 'student@example.com',
      scopes: ['Mail.Read'],
    })
    renderPage()

    expect(await screen.findByTestId('outlook-connected')).toBeInTheDocument()
    expect(screen.getByText('student@example.com')).toBeInTheDocument()
  })

  it('shows not configured message when integration is unavailable', async () => {
    statusMock.mockResolvedValue({ connected: false, available: false })
    renderPage()

    expect(await screen.findByTestId('outlook-unavailable')).toBeInTheDocument()
  })

  it('shows success banner after OAuth callback', async () => {
    statusMock.mockResolvedValue({ connected: true, available: true, email: 'a@b.com' })
    renderPage('/settings/integrations?outlook=connected')

    expect(await screen.findByTestId('integrations-banner')).toBeInTheDocument()
  })

  it('disconnects Outlook account', async () => {
    statusMock.mockResolvedValue({
      connected: true,
      available: true,
      email: 'student@example.com',
    })
    disconnectMock.mockResolvedValue({ disconnected: true })

    renderPage()
    const user = userEvent.setup()
    await screen.findByTestId('outlook-disconnect')
    await user.click(screen.getByTestId('outlook-disconnect'))

    await waitFor(() => {
      expect(disconnectMock).toHaveBeenCalled()
    })
  })
})
