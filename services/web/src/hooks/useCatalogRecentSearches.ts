import { useCallback, useState } from 'react'

const STORAGE_KEY = 'unipilot_catalog_recent'
const MAX_RECENT = 6

function readRecent(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed)
      ? parsed.filter((entry): entry is string => typeof entry === 'string' && entry.trim().length > 0)
      : []
  } catch {
    return []
  }
}

export function useCatalogRecentSearches() {
  const [recent, setRecent] = useState<string[]>(() => readRecent())

  const remember = useCallback((query: string) => {
    const trimmed = query.trim()
    if (trimmed.length < 2) return
    setRecent((current) => {
      const next = [trimmed, ...current.filter((entry) => entry !== trimmed)].slice(0, MAX_RECENT)
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      return next
    })
  }, [])

  const clear = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    setRecent([])
  }, [])

  return { recent, remember, clear }
}
