import { describe, expect, it } from 'vitest'
import { generatePlanIcs } from './icsExport'

describe('icsExport', () => {
  it('generates a valid calendar with schedule and exams', () => {
    const content = generatePlanIcs({
      planName: 'Fall plan',
      schedule: {
        weekView: [
          {
            day: 'Monday',
            slots: [
              {
                day: 'Monday',
                timeRange: '09:00-11:00',
                courseNumber: '01040001',
                courseTitle: 'Intro',
              },
            ],
          },
        ],
      },
      examSummary: {
        exams: [
          {
            courseNumber: '01040001',
            courseName: 'Intro',
            moed: 'A',
            date: '2026-02-15',
            startTime: '09:00',
          },
        ],
      },
      customEvents: [
        { id: '1', title: 'Gym', day: 'Sunday', startTime: '07:00', endTime: '08:00' },
      ],
    })

    expect(content).toContain('BEGIN:VCALENDAR')
    expect(content).toContain('01040001')
    expect(content).toContain('Exam 01040001')
    expect(content).toContain('Gym')
    expect(content).toContain('END:VCALENDAR')
  })

  it('does not duplicate custom blocks already baked into weekView', () => {
    const content = generatePlanIcs({
      planName: 'Fall plan',
      schedule: {
        weekView: [
          {
            day: 'Sunday',
            slots: [
              {
                day: 'Sunday',
                timeRange: '07:00-08:00',
                courseNumber: 'CUSTOM',
                courseTitle: 'Gym',
                slotType: 'custom',
              },
            ],
          },
        ],
      },
      customEvents: [{ id: '1', title: 'Gym', day: 'Sunday', startTime: '07:00', endTime: '08:00' }],
    })

    expect(content.match(/Gym/g)?.length).toBe(1)
  })
})
