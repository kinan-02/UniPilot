import { useEffect, useState } from 'react'

export function useMinWidth(minWidth: number): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined') return true
    return window.matchMedia(`(min-width: ${minWidth}px)`).matches
  })

  useEffect(() => {
    const mediaQuery = window.matchMedia(`(min-width: ${minWidth}px)`)
    const update = () => setMatches(mediaQuery.matches)
    update()
    mediaQuery.addEventListener('change', update)
    return () => mediaQuery.removeEventListener('change', update)
  }, [minWidth])

  return matches
}
