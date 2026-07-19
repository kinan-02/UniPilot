import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { BookOpen, FileText, Users, X } from 'lucide-react'
import type { AdvisorReply } from '../../types/api'

export type SourceGroups = {
  courses: { id: string; name: string }[]
  sources: string[]
  contacts: string[]
}

/** Prefers the named `courses` the AI service now sends, falling back to bare
 * `courseIds` so a reply from an older response shape still renders. */
export function sourceGroups(reply: AdvisorReply): SourceGroups {
  const courses =
    reply.courses?.length
      ? reply.courses
      : (reply.courseIds ?? []).map((id) => ({ id, name: id }))
  return {
    courses,
    sources: reply.sources ?? [],
    contacts: reply.contacts ?? [],
  }
}

export function countSources(groups: SourceGroups): number {
  return groups.courses.length + groups.sources.length + groups.contacts.length
}

/** A search source is recorded as `search: <query>`; show the query, labelled. */
function readableSource(source: string): { label: string; text: string } {
  return source.startsWith('search: ')
    ? { label: 'Search', text: source.slice('search: '.length) }
    : { label: 'Page', text: source }
}

function CourseLink({ course }: { course: { id: string; name: string } }) {
  const named = course.name && course.name !== course.id
  return (
    <Link
      to={`/catalog?course=${course.id}`}
      dir="auto"
      className="group flex items-baseline justify-between gap-3 rounded-lg px-3 py-2 hover:bg-[var(--color-primary)]/5 transition-colors"
    >
      <span dir="auto" className="text-sm text-[var(--color-text)] group-hover:text-[var(--color-primary)] transition-colors">
        {named ? course.name : `Course ${course.id}`}
      </span>
      <span className="shrink-0 font-mono text-xs text-[var(--color-text-muted)]">{course.id}</span>
    </Link>
  )
}

/**
 * Slide-over listing everything an answer drew on.
 *
 * Exists because the footer inlined every referenced course: one live answer
 * produced 46 chips, which is a wall, not a citation. Few sources stay inline in
 * the footer; the rest live here.
 */
export function SourcesPanel({
  groups,
  isOpen,
  onClose,
}: {
  groups: SourceGroups
  isOpen: boolean
  onClose: () => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!isOpen) return
    closeRef.current?.focus()

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      // Focus trap: a dialog the keyboard can walk out of is a dialog only mouse
      // users can actually close.
      const focusable = panelRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )
      if (!focusable?.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const { courses, sources, contacts } = groups

  // Portalled to <body> deliberately. The message bubble animates in via a
  // transform (`advisor-msg-in`), and a transformed ancestor becomes the
  // containing block for `position: fixed` -- so rendered in place the panel was
  // trapped inside the bubble, clipped to its width and height.
  return createPortal(
    <div className="fixed inset-0 z-50 flex" role="presentation">
      <button
        type="button"
        aria-label="Close sources"
        onClick={onClose}
        className="flex-1 bg-black/20 backdrop-blur-[2px] animate-fade-in"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="sources-panel-title"
        data-testid="sources-panel"
        className="w-full max-w-sm overflow-y-auto bg-[var(--color-surface,#fff)] shadow-2xl advisor-panel-in"
      >
        <div className="sticky top-0 flex items-center justify-between gap-3 border-b border-[rgba(79,70,229,0.1)] bg-inherit px-5 py-4">
          <h2 id="sources-panel-title" className="text-sm font-semibold text-[var(--color-text)]">
            Sources &amp; citations
          </h2>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Close sources"
            className="rounded-lg p-1.5 text-[var(--color-text-muted)] hover:bg-[var(--color-primary)]/5 hover:text-[var(--color-text)] transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-6 px-3 py-4">
          {courses.length > 0 && (
            <section aria-labelledby="sources-courses">
              <h3
                id="sources-courses"
                className="flex items-center gap-1.5 px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]"
              >
                <BookOpen className="h-3.5 w-3.5" />
                Courses ({courses.length})
              </h3>
              <div className="space-y-0.5">
                {courses.map((course) => (
                  <CourseLink key={course.id} course={course} />
                ))}
              </div>
            </section>
          )}

          {sources.length > 0 && (
            <section aria-labelledby="sources-references">
              <h3
                id="sources-references"
                className="flex items-center gap-1.5 px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]"
              >
                <FileText className="h-3.5 w-3.5" />
                References ({sources.length})
              </h3>
              <ul className="space-y-0.5">
                {sources.map((source) => {
                  const { label, text } = readableSource(source)
                  return (
                    <li key={source} className="flex items-baseline gap-2 px-3 py-2">
                      <span className="shrink-0 rounded bg-[var(--color-primary)]/8 px-1.5 py-0.5 text-[10px] font-medium uppercase text-[var(--color-primary)]">
                        {label}
                      </span>
                      <span dir="auto" className="text-sm text-[var(--color-text)] break-words">
                        {text}
                      </span>
                    </li>
                  )
                })}
              </ul>
            </section>
          )}

          {contacts.length > 0 && (
            <section aria-labelledby="sources-contacts">
              <h3
                id="sources-contacts"
                className="flex items-center gap-1.5 px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]"
              >
                <Users className="h-3.5 w-3.5" />
                Contacts ({contacts.length})
              </h3>
              <ul className="space-y-0.5">
                {contacts.map((contact) => (
                  <li key={contact} dir="auto" className="px-3 py-2 text-sm text-[var(--color-text)]">
                    {contact}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>,
    document.body,
  )
}
