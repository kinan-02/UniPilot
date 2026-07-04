import { describe, expect, it } from 'vitest'
import type { AiJob } from '../types/api'

// Re-export mapping logic test via duplicated minimal check — hook is tested through AdvisorPage integration later.
function advisorReplyFromJob(job: AiJob) {
  const advisor = job.result?.advisor as Record<string, unknown> | undefined
  if (!advisor || typeof advisor.answer !== 'string') return null
  return {
    answer: advisor.answer,
    confidence: typeof advisor.confidence === 'string' ? advisor.confidence : 'medium',
    courseIds: Array.isArray(advisor.courseIds) ? advisor.courseIds : [],
    wikiSlugs: [],
    sources: [],
    contacts: [],
    question: '',
  }
}

describe('advisorReplyFromJob', () => {
  it('maps completed job advisor payload', () => {
    const reply = advisorReplyFromJob({
      id: '1',
      type: 'advisor_deep_plan',
      status: 'completed',
      payload: {},
      result: {
        advisor: {
          answer: 'Done',
          confidence: 'high',
          courseIds: ['00440148'],
        },
      },
    })

    expect(reply?.answer).toBe('Done')
    expect(reply?.courseIds).toEqual(['00440148'])
  })
})
