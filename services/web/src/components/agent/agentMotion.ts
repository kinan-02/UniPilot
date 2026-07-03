/**
 * Agent UI motion helpers — respects prefers-reduced-motion (motion-ui skill).
 */
import { type Variants, useReducedMotion } from 'motion/react'

export function useAgentMotionEnabled(): boolean {
  return !useReducedMotion()
}

export const agentFadeUp: Variants = {
  hidden: { opacity: 0, y: 12 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] },
  },
}

export const agentFadeIn: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { duration: 0.28, ease: 'easeOut' },
  },
}

export const agentSlideInStart: Variants = {
  hidden: { opacity: 0, x: -16 },
  visible: {
    opacity: 1,
    x: 0,
    transition: { duration: 0.32, ease: [0.22, 1, 0.36, 1] },
  },
}

export const agentSlideInEnd: Variants = {
  hidden: { opacity: 0, x: 16 },
  visible: {
    opacity: 1,
    x: 0,
    transition: { duration: 0.32, ease: [0.22, 1, 0.36, 1] },
  },
}

export const agentStaggerContainer: Variants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.06, delayChildren: 0.04 },
  },
}

export const agentScaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.96 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.3, ease: [0.22, 1, 0.36, 1] },
  },
}

/** Spring for layout-friendly panel transitions */
export const agentPanelTransition = {
  type: 'spring' as const,
  stiffness: 380,
  damping: 32,
}

export function motionSafe<T extends Record<string, unknown>>(variants: T, reduced: boolean): T | undefined {
  return reduced ? undefined : variants
}
