import type { AdvisorReply } from '../../types/api'

/** The citations behind one advisor reply, split by what they are.
 *
 * Lives beside `SourcesPanel` rather than inside it because a file that exports
 * both components and plain functions breaks Fast Refresh -- editing this helper
 * would remount the panel instead of hot-swapping it. Same reason the panel does
 * not re-export these.
 */
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
