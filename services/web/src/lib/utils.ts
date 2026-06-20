import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCredits(value: number | undefined | null): string {
  if (value == null) return '—'
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

export function formatPercent(value: number | undefined | null): string {
  if (value == null) return '—'
  return `${value.toFixed(1)}%`
}
