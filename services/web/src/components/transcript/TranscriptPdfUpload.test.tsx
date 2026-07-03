import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TranscriptPdfUpload } from './TranscriptPdfUpload'
import * as endpoints from '../../api/endpoints'
import { I18nProvider } from '../../i18n'

vi.mock('../../api/endpoints', () => ({
  transcriptImportApi: {
    parse: vi.fn(),
    commit: vi.fn(),
  },
  catalogApi: {
    course: vi.fn(),
  },
}))

const previewFixture = {
  courses: [
    {
      courseNumber: '00940345',
      semesterCode: '2024-1',
      grade: 88,
      creditsEarned: 5,
      attempt: 1,
      title: 'Discrete Mathematics',
      confidence: 0.95,
      warnings: [],
    },
    {
      courseNumber: '00940411',
      semesterCode: '2024-2',
      grade: 72,
      creditsEarned: 3.5,
      attempt: 1,
      title: 'Algorithms',
      confidence: 0.6,
      warnings: ['Ambiguous title'],
    },
  ],
  studentId: '211479449',
  studentName: 'Test Student',
  warnings: ['Header partially parsed'],
  parseMetadata: {
    pageCount: 2,
    extractor: 'pymupdf',
    pipelineVersion: '0.3.0-official-he-en',
    textCharCount: 12000,
    ocrUsed: false,
  },
}

function renderUpload(featured = false, locale: 'en' | 'he' = 'en') {
  localStorage.setItem('unipilot_locale', locale)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const t = (key: string, params?: Record<string, string | number>) => {
    const map: Record<string, string> = {
      'transcript.upload.title': 'Upload official transcript',
      'transcript.upload.hint': 'Upload hint',
      'transcript.upload.featuredHint': 'Featured hint',
      'transcript.upload.dropHint': 'Drag and drop',
      'transcript.upload.dropActive': 'Drop now',
      'transcript.upload.supportedFormats': 'PDF only',
      'transcript.upload.chooseFile': 'Choose PDF',
      'transcript.upload.parseButton': 'Extract courses',
      'transcript.upload.parsing': 'Extracting',
      'transcript.upload.previewCount': `${params?.count ?? 0} courses detected`,
      'transcript.upload.selectedCount': `${params?.count ?? 0} selected for import`,
      'transcript.upload.selectAll': 'Select all',
      'transcript.upload.deselectAll': 'Deselect all',
      'transcript.upload.clearPreview': 'Clear preview',
      'transcript.upload.filterPreview': 'Filter preview',
      'transcript.upload.studentInfo': 'Student',
      'transcript.upload.metadataPages': 'Document',
      'transcript.upload.lowConfidence': 'Review',
      'transcript.upload.noCourses': 'No courses',
      'transcript.upload.importButton': `Import ${params?.count ?? 0} selected`,
      'transcript.upload.importing': 'Importing',
      'transcript.upload.importSuccess': `Imported ${params?.created} courses`,
      'transcript.upload.parseFailed': 'Parse failed',
      'transcript.upload.importFailed': 'Import failed',
      'transcript.upload.invalidFile': 'Invalid file',
      'transcript.courses': 'Courses',
      'transcript.gradeLabel': `Grade {grade}`,
      'common.credits': 'credits',
      'common.noResults': 'No results found',
    }
    return map[key] ?? key
  }

  return {
    queryClient,
    ...render(
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <TranscriptPdfUpload locale={locale} t={t} featured={featured} />
        </QueryClientProvider>
      </I18nProvider>,
    ),
  }
}

describe('TranscriptPdfUpload', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.mocked(endpoints.catalogApi.course).mockImplementation(async (courseNumber: string) => ({
      course: {
        courseNumber,
        title:
          courseNumber === '00940345' ? 'Discrete Mathematics' : 'Intro to Data Science',
        titleHebrew:
          courseNumber === '00940345' ? 'מתמטיקה דיסקרטית' : 'מבוא למדעי הנתונים',
      },
    }))
  })

  it('renders drop zone and featured hint when highlighted', () => {
    renderUpload(true)
    expect(screen.getByTestId('transcript-upload-dropzone')).toBeInTheDocument()
    expect(screen.getByText('Featured hint')).toBeInTheDocument()
  })

  it('parses PDF and shows grouped preview with student metadata', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.transcriptImportApi.parse).mockResolvedValue({
      parsePreview: previewFixture,
    })

    renderUpload()
    const file = new File(['pdf'], 'transcript.pdf', { type: 'application/pdf' })
    await user.upload(screen.getByTestId('transcript-upload-input'), file)
    await user.click(screen.getByTestId('transcript-upload-parse'))

    expect(await screen.findByTestId('transcript-upload-preview')).toBeInTheDocument()
    expect(screen.getByText('Test Student')).toBeInTheDocument()
    expect(screen.getByText('211479449')).toBeInTheDocument()
    expect(screen.getByTestId('transcript-preview-row-00940345')).toBeInTheDocument()
    expect(screen.getByTestId('transcript-preview-row-00940411')).toBeInTheDocument()
    expect(screen.getByText('Review')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('Intro to Data Science')).toBeInTheDocument()
    })
    expect(screen.queryByText('Algorithms')).not.toBeInTheDocument()
  })

  it('shows Hebrew catalog titles when UI locale is Hebrew', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.transcriptImportApi.parse).mockResolvedValue({
      parsePreview: previewFixture,
    })

    renderUpload(false, 'he')
    const file = new File(['pdf'], 'transcript.pdf', { type: 'application/pdf' })
    await user.upload(screen.getByTestId('transcript-upload-input'), file)
    await user.click(screen.getByTestId('transcript-upload-parse'))

    await screen.findByTestId('transcript-upload-preview')
    await waitFor(() => {
      expect(screen.getByText('מתמטיקה דיסקרטית')).toBeInTheDocument()
      expect(screen.getByText('מבוא למדעי הנתונים')).toBeInTheDocument()
    })
    expect(screen.queryByText('Discrete Mathematics')).not.toBeInTheDocument()
    expect(screen.queryByText('Intro to Data Science')).not.toBeInTheDocument()
  })

  it('commits selected courses and invalidates transcript/progress queries', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.transcriptImportApi.parse).mockResolvedValue({
      parsePreview: previewFixture,
    })
    vi.mocked(endpoints.transcriptImportApi.commit).mockResolvedValue({
      importResult: {
        created: [],
        skippedDuplicates: [],
        unresolved: [],
        createdCount: 2,
        skippedCount: 0,
        unresolvedCount: 0,
      },
    })

    const { queryClient } = renderUpload()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    const file = new File(['pdf'], 'transcript.pdf', { type: 'application/pdf' })
    await user.upload(screen.getByTestId('transcript-upload-input'), file)
    await user.click(screen.getByTestId('transcript-upload-parse'))
    await screen.findByTestId('transcript-upload-preview')

    await user.click(screen.getByTestId('transcript-upload-commit'))

    await waitFor(() => {
      expect(endpoints.transcriptImportApi.commit).toHaveBeenCalledWith(previewFixture.courses, {
        replaceExisting: true,
      })
    })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['transcript'] })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['progress'] })
    expect(await screen.findByTestId('transcript-upload-success')).toHaveTextContent('Imported 2 courses')
  })

  it('filters preview rows', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.transcriptImportApi.parse).mockResolvedValue({
      parsePreview: previewFixture,
    })

    renderUpload()
    const file = new File(['pdf'], 'transcript.pdf', { type: 'application/pdf' })
    await user.upload(screen.getByTestId('transcript-upload-input'), file)
    await user.click(screen.getByTestId('transcript-upload-parse'))
    await screen.findByTestId('transcript-upload-preview')

    await user.type(screen.getByTestId('transcript-upload-filter'), 'data science')
    expect(screen.queryByTestId('transcript-preview-row-00940345')).not.toBeInTheDocument()
    expect(screen.getByTestId('transcript-preview-row-00940411')).toBeInTheDocument()
  })
})
