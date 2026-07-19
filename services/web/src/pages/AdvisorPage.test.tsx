import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AdvisorPage } from './AdvisorPage'
import { advisorApi } from '../api/endpoints'
import { I18nProvider } from '../i18n'

vi.mock('../api/endpoints', () => ({
  advisorApi: {
    ask: vi.fn(),
    askStream: vi.fn(),
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
          <AdvisorPage />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

/** A Response whose body yields exactly these byte chunks, in order. The split
 * points are the whole point: the reader must not assume they align with SSE
 * event boundaries. */
function streamingResponse(...chunks: string[]): Response {
  const encoder = new TextEncoder()
  let index = 0

  return {
    ok: true,
    body: {
      getReader: () => ({
        read: async () =>
          index < chunks.length
            ? { value: encoder.encode(chunks[index++]), done: false }
            : { value: undefined, done: true },
      }),
    },
  } as unknown as Response
}

const ADVISOR_REPLY = {
  question: 'How many credits do I have left?',
  answer: 'You have 12.5 credits remaining.',
  confidence: 'high',
  courseIds: ['00940314'],
  wikiSlugs: [],
  sources: ['search: ise credits'],
  contacts: [],
  eligibility: null,
  semesterResolution: null,
  retrievalStatus: 'succeeded',
}

const CHUNK_EVENT = `data: ${JSON.stringify({ type: 'chunk', text: ADVISOR_REPLY.answer })}\n\n`
const FINAL_EVENT = `data: ${JSON.stringify({ type: 'final', data: { advisor: ADVISOR_REPLY } })}\n\n`

async function ask() {
  const user = userEvent.setup()
  renderPage()
  await user.type(screen.getByTestId('advisor-input'), 'How many credits do I have left?')
  await user.click(screen.getByTestId('advisor-submit'))
}

describe('AdvisorPage', () => {
  beforeEach(() => {
    vi.mocked(advisorApi.askStream).mockReset()
  })

  it('renders advisor shell and suggested prompts', () => {
    vi.mocked(advisorApi.askStream).mockResolvedValue(streamingResponse())
    renderPage()
    expect(screen.getByTestId('advisor-page')).toBeInTheDocument()
    expect(screen.getByTestId('advisor-input')).toBeInTheDocument()
    expect(screen.getByTestId('advisor-submit')).toBeInTheDocument()
  })

  it('renders answer and metadata when each event arrives in its own read', async () => {
    vi.mocked(advisorApi.askStream).mockResolvedValue(
      streamingResponse(CHUNK_EVENT, FINAL_EVENT),
    )

    await ask()

    expect(await screen.findByText(ADVISOR_REPLY.answer)).toBeInTheDocument()
    expect(await screen.findByText('Referenced Courses')).toBeInTheDocument()
    expect(await screen.findByText('00940314')).toBeInTheDocument()
  })

  it('keeps the final event when a read boundary splits it in half', async () => {
    // The regression this pins: `final` carries the whole advisor payload and is
    // the largest event, so it is the one a buffer boundary lands inside. Parsing
    // per-read dropped both halves silently -- the answer text still rendered
    // (it came from `chunk`), so the only visible symptom was the confidence
    // badge and source list quietly going missing.
    const split = CHUNK_EVENT.length + Math.floor(FINAL_EVENT.length / 2)
    const whole = CHUNK_EVENT + FINAL_EVENT

    vi.mocked(advisorApi.askStream).mockResolvedValue(
      streamingResponse(whole.slice(0, split), whole.slice(split)),
    )

    await ask()

    expect(await screen.findByText(ADVISOR_REPLY.answer)).toBeInTheDocument()
    expect(await screen.findByText('Referenced Courses')).toBeInTheDocument()
    expect(await screen.findByText('00940314')).toBeInTheDocument()
  })

  it('reassembles an event delivered one byte at a time', async () => {
    const whole = CHUNK_EVENT + FINAL_EVENT

    vi.mocked(advisorApi.askStream).mockResolvedValue(
      streamingResponse(...whole.split('')),
    )

    await ask()

    expect(await screen.findByText(ADVISOR_REPLY.answer)).toBeInTheDocument()
    expect(await screen.findByText('Referenced Courses')).toBeInTheDocument()
  })
})
