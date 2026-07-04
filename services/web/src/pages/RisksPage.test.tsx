import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { RisksPage } from './RisksPage'
import { I18nProvider } from '../i18n'

const mockList = vi.fn()
const mockPlansList = vi.fn()

vi.mock('../api/endpoints', () => ({
  risksApi: {
    list: (...args: unknown[]) => mockList(...args),
    analyze: vi.fn(),
  },
  plansApi: {
    list: (...args: unknown[]) => mockPlansList(...args),
  },
}))

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <MemoryRouter>
          <RisksPage />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

describe('RisksPage', () => {
  beforeEach(() => {
    localStorage.setItem('unipilot_locale', 'en')
    mockList.mockResolvedValue({ academicRiskAnalyses: [], pagination: { total: 0 } })
    mockPlansList.mockResolvedValue({ semesterPlans: [], pagination: { total: 0 } })
  })

  it('renders risks shell while plans are still loading', () => {
    mockPlansList.mockImplementation(() => new Promise(() => {}))
    renderPage()
    expect(screen.getByTestId('risks-page')).toBeInTheDocument()
    expect(screen.getByText('Academic risks')).toBeInTheDocument()
  })

  it('renders empty state when no analyses exist', async () => {
    renderPage()
    expect(await screen.findByText('No analyses yet')).toBeInTheDocument()
  })

  it('renders history when summary is a structured object', async () => {
    mockList.mockResolvedValue({
      academicRiskAnalyses: [
        {
          id: 'analysis-1',
          status: 'open',
          semesterCode: '2025-1',
          summary: {
            totalRisks: 2,
            highestSeverity: 'high',
            counts: { low: 0, medium: 1, high: 1 },
          },
        },
      ],
      pagination: { total: 1 },
    })
    renderPage()
    expect(await screen.findByText(/2 risks found/)).toBeInTheDocument()
  })

  it('handles plans payload without semesterPlans array', async () => {
    mockPlansList.mockResolvedValue({ pagination: { total: 0 } })
    renderPage()
    expect(await screen.findByText('No analyses yet')).toBeInTheDocument()
  })
})
