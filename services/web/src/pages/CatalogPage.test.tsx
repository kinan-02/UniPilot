import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CatalogPage } from './CatalogPage'
import * as endpoints from '../api/endpoints'
import { I18nProvider } from '../i18n'

vi.mock('../hooks/useMinWidth', () => ({
  useMinWidth: () => true,
}))

vi.mock('../api/endpoints', () => ({
  catalogApi: {
    courses: vi.fn(),
    course: vi.fn(),
    faculties: vi.fn(),
  },
}))

function renderCatalog(initialEntry = '/catalog') {
  localStorage.setItem('unipilot_locale', 'en')
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[initialEntry]}>
          <CatalogPage />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nProvider>,
  )
}

const sampleCourse = {
  courseNumber: '00940345',
  title: 'Discrete Mathematics',
  titleHebrew: 'מתמטיקה בדידה',
  faculty: 'Faculty of Data Science',
  credits: 5,
}

describe('CatalogPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.mocked(endpoints.catalogApi.faculties).mockResolvedValue({
      items: ['Faculty of Data Science'],
      total: 1,
    })
    vi.mocked(endpoints.catalogApi.courses).mockResolvedValue({
      items: [sampleCourse],
      total: 1,
      limit: 30,
      offset: 0,
    })
    vi.mocked(endpoints.catalogApi.course).mockResolvedValue({
      course: {
        ...sampleCourse,
        syllabus: 'Introductory discrete math topics.',
        offerings: [],
      },
    })
  })

  it('renders search results and opens rich detail panel', async () => {
    const user = userEvent.setup()
    renderCatalog()

    expect(await screen.findByTestId('catalog-course-list')).toBeInTheDocument()
    await user.click(screen.getByTestId('catalog-course-row-00940345'))

    expect(await screen.findByTestId('catalog-detail-panel')).toBeInTheDocument()
    expect(screen.getByText('Introductory discrete math topics.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /add to plan/i })).toHaveAttribute('href', '/plans/new')
    expect(screen.getByRole('link', { name: /view progress/i })).toHaveAttribute('href', '/progress')
  })

  it('hydrates search query from URL', async () => {
    renderCatalog('/catalog?q=00940345')

    expect(await screen.findByTestId('catalog-search-input')).toHaveValue('00940345')
    await waitFor(() => {
      expect(endpoints.catalogApi.courses).toHaveBeenCalled()
    })
  })

  it('appends additional pages when loading more', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.catalogApi.courses).mockImplementation(async (params) => {
      const offset = Number(params.offset ?? 0)
      if (offset > 0) {
        return {
          items: [{ ...sampleCourse, courseNumber: '00940411', title: 'Data Structures' }],
          total: 2,
          limit: 30,
          offset,
        }
      }
      return {
        items: [sampleCourse],
        total: 2,
        limit: 30,
        offset: 0,
      }
    })

    renderCatalog()
    expect(await screen.findByTestId('catalog-course-list')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /load more/i }))
    expect(await screen.findByTestId('catalog-course-row-00940411')).toBeInTheDocument()
    expect(screen.getByTestId('catalog-course-row-00940345')).toBeInTheDocument()
  })
})
