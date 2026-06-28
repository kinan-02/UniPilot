import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { I18nProvider } from '../../i18n'
import { ElectivePoolCourseList } from './ElectivePoolCourseList'
import { electivePool, manyPoolCourses, progressT, requirementBucket } from '../../testFixtures/progress'
import { VIRTUAL_LIST_THRESHOLD } from '../../lib/electivePools'

function renderCourseList(courseCount: number) {
  const pool = electivePool({
    courses: manyPoolCourses(courseCount),
    courseCount,
  })

  return render(
    <I18nProvider>
      <MemoryRouter>
        <ElectivePoolCourseList
          pool={pool}
          allPools={[pool]}
          bucket={requirementBucket()}
          transcriptNumbers={new Set()}
          requiredCurriculumNumbers={new Set()}
          t={progressT}
        />
      </MemoryRouter>
    </I18nProvider>,
  )
}

describe('ElectivePoolCourseList', () => {
  it('uses a standard list for pools below the virtual threshold', () => {
    renderCourseList(VIRTUAL_LIST_THRESHOLD - 1)

    expect(screen.getByTestId(`elective-pool-detail-${electivePool().groupId}`)).toBeInTheDocument()
    expect(screen.queryByTestId('virtual-pool-course-list')).not.toBeInTheDocument()
    expect(screen.getAllByRole('listitem').length).toBe(VIRTUAL_LIST_THRESHOLD - 1)
  })

  it('virtualizes large pools at or above the threshold', () => {
    renderCourseList(VIRTUAL_LIST_THRESHOLD)

    expect(screen.getByTestId('virtual-pool-course-list')).toBeInTheDocument()
    const renderedCourses = screen.getAllByRole('listitem')
    expect(renderedCourses.length).toBeGreaterThan(0)
    expect(renderedCourses.length).toBeLessThan(VIRTUAL_LIST_THRESHOLD)
  })

  it('virtualizes 50-course pools without mounting every row', () => {
    renderCourseList(50)

    expect(screen.getByTestId('virtual-pool-course-list')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem').length).toBeLessThan(50)
  })
})
