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
  courses: [{ id: '00940314', name: 'Statistical Inference' }],
  wikiSlugs: [],
  sources: ['search: ise credits'],
  contacts: [],
  eligibility: null,
  semesterResolution: null,
  retrievalStatus: 'succeeded',
}

/** More references than the footer will inline — the 46-chip case, in miniature. */
const MANY_SOURCES_REPLY = {
  ...ADVISOR_REPLY,
  answer: 'You completed several courses.',
  courseIds: ['00940314', '00960211', '00960262', '00960236'],
  courses: [
    { id: '00940314', name: 'Statistical Inference' },
    { id: '00960211', name: 'E-Commerce Models' },
    { id: '00960262', name: 'Information Retrieval' },
    { id: '00960236', name: 'Generative Learning' },
  ],
}

const manyFinalEvent = `data: ${JSON.stringify({ type: 'final', data: { advisor: MANY_SOURCES_REPLY } })}\n\n`
const manyChunkEvent = `data: ${JSON.stringify({ type: 'chunk', text: MANY_SOURCES_REPLY.answer })}\n\n`

const CHUNK_EVENT = `data: ${JSON.stringify({ type: 'chunk', text: ADVISOR_REPLY.answer })}\n\n`
const FINAL_EVENT = `data: ${JSON.stringify({ type: 'final', data: { advisor: ADVISOR_REPLY } })}\n\n`
const progressEvent = (text: string) => `data: ${JSON.stringify({ type: 'progress', text })}\n\n`

/** Delivers `before`, then blocks until the returned `release` is called, then
 * delivers `after` — so a test can assert on what the UI shows mid-stream. */
function gatedStream(before: string[], after: string[]) {
  const encoder = new TextEncoder()
  const queue = [...before]
  let release: () => void = () => {}
  const gate = new Promise<void>((resolve) => { release = resolve })
  let opened = false

  const response = {
    ok: true,
    body: {
      getReader: () => ({
        read: async () => {
          if (!queue.length && !opened) {
            await gate
            opened = true
            queue.push(...after)
          }
          return queue.length
            ? { value: encoder.encode(queue.shift()), done: false }
            : { value: undefined, done: true }
        },
      }),
    },
  } as unknown as Response

  return { response, release: () => release() }
}

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
    // Two references: inlined, and named rather than numbered.
    expect(await screen.findByText('Statistical Inference')).toBeInTheDocument()
    expect(screen.getByText('ise credits')).toBeInTheDocument()
  })

  it('collapses to one control once there are more references than fit inline', async () => {
    // The 46-chip case: inlining every reference is a wall, not a citation.
    vi.mocked(advisorApi.askStream).mockResolvedValue(
      streamingResponse(manyChunkEvent, manyFinalEvent),
    )

    await ask()

    const toggle = await screen.findByTestId('advisor-sources-toggle')
    expect(toggle).toHaveTextContent('Based on 5 sources')
    expect(screen.queryByText('E-Commerce Models')).not.toBeInTheDocument()
    expect(screen.queryByTestId('sources-panel')).not.toBeInTheDocument()
  })

  it('opens the sources panel from the footer control', async () => {
    const user = userEvent.setup()
    vi.mocked(advisorApi.askStream).mockResolvedValue(
      streamingResponse(manyChunkEvent, manyFinalEvent),
    )

    await ask()
    await user.click(await screen.findByTestId('advisor-sources-toggle'))

    expect(await screen.findByTestId('sources-panel')).toBeInTheDocument()
    expect(screen.getByText('E-Commerce Models')).toBeInTheDocument()
    expect(screen.getByText('Information Retrieval')).toBeInTheDocument()
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
    expect(await screen.findByText('Statistical Inference')).toBeInTheDocument()
  })

  it('shows the latest progress phrase while the answer is still pending', async () => {
    // The answer arrives in one piece at the end, so during a 190s planning
    // question this is the only thing on screen that changes.
    const { response, release } = gatedStream(
      [progressEvent('Reading your academic record'), progressEvent('Checking your eligibility')],
      [CHUNK_EVENT, FINAL_EVENT],
    )
    vi.mocked(advisorApi.askStream).mockResolvedValue(response)

    await ask()

    // Mid-stream: latest phrase wins, and no answer has landed yet.
    expect(await screen.findByText('Checking your eligibility')).toBeInTheDocument()
    expect(screen.queryByText('Reading your academic record')).not.toBeInTheDocument()
    expect(screen.queryByText(ADVISOR_REPLY.answer)).not.toBeInTheDocument()

    release()

    expect(await screen.findByText(ADVISOR_REPLY.answer)).toBeInTheDocument()
    expect(screen.queryByTestId('advisor-progress')).not.toBeInTheDocument()
  })

  it('falls back to the default phrase before any progress event arrives', async () => {
    const { response, release } = gatedStream([], [CHUNK_EVENT, FINAL_EVENT])
    vi.mocked(advisorApi.askStream).mockResolvedValue(response)

    await ask()

    expect(await screen.findByTestId('advisor-progress')).toHaveTextContent('Analyzing your question…')

    release()
    expect(await screen.findByText(ADVISOR_REPLY.answer)).toBeInTheDocument()
  })

  it('marks message text dir="auto" so English is not mangled by the RTL shell', async () => {
    // <html dir="rtl"> for the Hebrew UI. Without dir="auto" an English answer
    // inherits RTL and bidi throws its final period to the visual left.
    vi.mocked(advisorApi.askStream).mockResolvedValue(
      streamingResponse(CHUNK_EVENT, FINAL_EVENT),
    )

    await ask()

    const answer = await screen.findByText(ADVISOR_REPLY.answer)
    expect(answer.closest('[dir="auto"]')).not.toBeNull()
    expect(screen.getByText('How many credits do I have left?').closest('[dir="auto"]')).not.toBeNull()
  })

  it('reassembles an event delivered one byte at a time', async () => {
    const whole = CHUNK_EVENT + FINAL_EVENT

    vi.mocked(advisorApi.askStream).mockResolvedValue(
      streamingResponse(...whole.split('')),
    )

    await ask()

    expect(await screen.findByText(ADVISOR_REPLY.answer)).toBeInTheDocument()
    expect(await screen.findByText('Statistical Inference')).toBeInTheDocument()
  })
})
