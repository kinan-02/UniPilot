import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { OnboardingStepIndicator } from './OnboardingStepIndicator'

describe('OnboardingStepIndicator', () => {
  it('marks the active step for screen readers', () => {
    render(<OnboardingStepIndicator steps={['Level', 'Faculty', 'Program', 'Term']} currentStep={1} />)
    expect(screen.getByLabelText('Profile setup progress')).toBeInTheDocument()
    expect(screen.getByText('Faculty')).toBeInTheDocument()
  })
})
