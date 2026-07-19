import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { SourcesPanel, countSources, sourceGroups } from './SourcesPanel'
import type { AdvisorReply } from '../../types/api'

function reply(overrides: Partial<AdvisorReply> = {}): AdvisorReply {
  return {
    question: 'q',
    answer: 'a',
    confidence: 'high',
    courseIds: [],
    wikiSlugs: [],
    sources: [],
    contacts: [],
    ...overrides,
  }
}

describe('sourceGroups', () => {
  it('prefers named courses over bare ids', () => {
    const groups = sourceGroups(
      reply({
        courseIds: ['00960211'],
        courses: [{ id: '00960211', name: 'E-Commerce Models' }],
      }),
    )
    expect(groups.courses).toEqual([{ id: '00960211', name: 'E-Commerce Models' }])
  })

  it('falls back to ids when the reply predates named courses', () => {
    // An older response shape, or a reply already in a rendered conversation
    // when the service was upgraded.
    const groups = sourceGroups(reply({ courseIds: ['00960211'] }))
    expect(groups.courses).toEqual([{ id: '00960211', name: '00960211' }])
  })

  it('counts every kind of source together', () => {
    const groups = sourceGroups(
      reply({
        courseIds: ['1', '2'],
        sources: ['search: credits'],
        contacts: ['registrar@example.edu'],
      }),
    )
    expect(countSources(groups)).toBe(4)
  })
})

describe('SourcesPanel', () => {
  const groups = sourceGroups(
    reply({
      courses: [
        { id: '00960211', name: 'E-Commerce Models' },
        { id: '03240305', name: 'היסטוריה של המדע' },
        { id: '00000001', name: '00000001' },
      ],
      sources: ['search: graduation credits', 'track-information-systems-engineering'],
      contacts: ['registrar@example.edu'],
    }),
  )

  function renderPanel(isOpen = true, onClose = vi.fn()) {
    render(
      <MemoryRouter>
        <SourcesPanel groups={groups} isOpen={isOpen} onClose={onClose} />
      </MemoryRouter>,
    )
    return { onClose }
  }

  it('renders nothing while closed', () => {
    renderPanel(false)
    expect(screen.queryByTestId('sources-panel')).not.toBeInTheDocument()
  })

  it('lists every group with its count', () => {
    renderPanel()
    expect(screen.getByText('Courses (3)')).toBeInTheDocument()
    expect(screen.getByText('References (2)')).toBeInTheDocument()
    expect(screen.getByText('Contacts (1)')).toBeInTheDocument()
  })

  it('shows course names, and keeps the code alongside', () => {
    renderPanel()
    expect(screen.getByText('E-Commerce Models')).toBeInTheDocument()
    expect(screen.getByText('היסטוריה של המדע')).toBeInTheDocument()
    expect(screen.getByText('00960211')).toBeInTheDocument()
  })

  it('labels an unnamed course rather than showing a bare number twice', () => {
    renderPanel()
    expect(screen.getByText('Course 00000001')).toBeInTheDocument()
  })

  it('links each course to the catalog', () => {
    renderPanel()
    expect(screen.getByRole('link', { name: /E-Commerce Models/ })).toHaveAttribute(
      'href',
      '/catalog?course=00960211',
    )
  })

  it('labels a search source and strips its prefix', () => {
    renderPanel()
    expect(screen.getByText('graduation credits')).toBeInTheDocument()
    expect(screen.queryByText(/^search: /)).not.toBeInTheDocument()
  })

  it('closes on Escape', async () => {
    const user = userEvent.setup()
    const { onClose } = renderPanel()
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })

  it('closes when the backdrop is clicked', async () => {
    const user = userEvent.setup()
    const { onClose } = renderPanel()
    await user.click(screen.getByLabelText('Close sources', { selector: 'button.flex-1' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('is a labelled modal dialog', () => {
    renderPanel()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAccessibleName('Sources & citations')
  })

  it('moves focus into the panel when it opens', () => {
    renderPanel()
    // A dialog that never takes focus strands a keyboard user behind it.
    expect(document.activeElement).toHaveAttribute('aria-label', 'Close sources')
  })
})
