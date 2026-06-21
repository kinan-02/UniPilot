import type { SelectedGroups, SelectedLessonEvent } from './api'

export type DraftCourse = {
  courseId: string
  courseNumber: string
  courseTitle: string
  credits: number
  isActive: boolean
  selectedGroups?: SelectedGroups
  selectedLessonEvents?: SelectedLessonEvent[]
  groupSummary?: string
  color?: string
  notes?: string
}

export type PlannerSnapshot = {
  courses: DraftCourse[]
  maybeCourses: DraftCourse[]
  customEvents: import('./api').CustomEvent[]
}

export type PlannerFilters = {
  searchQuery: string
  faculty: string
  minCredits: string
  maxCredits: string
  slotType: string
  hideSelected: boolean
  hideMissingPrereqs: boolean
  hideMissingCoreqs: boolean
  hideNoCreditConflicts: boolean
  includeOnly: string
  exclude: string
  moedAFrom: string
  moedATo: string
  moedBFrom: string
  moedBTo: string
  hideWithExam: boolean
  hideWithoutExam: boolean
}

export const emptyPlannerFilters = (): PlannerFilters => ({
  searchQuery: '',
  faculty: '',
  minCredits: '',
  maxCredits: '',
  slotType: '',
  hideSelected: true,
  hideMissingPrereqs: false,
  hideMissingCoreqs: false,
  hideNoCreditConflicts: false,
  includeOnly: '',
  exclude: '',
  moedAFrom: '',
  moedATo: '',
  moedBFrom: '',
  moedBTo: '',
  hideWithExam: false,
  hideWithoutExam: false,
})

export type PlanChangeItem = {
  id: string
  courseNumber?: string
  type: string
  message: string
}
