import { useCallback, useState } from 'react'

export function usePlannerHistory<T>(initial: T) {
  const [present, setPresent] = useState(initial)
  const [past, setPast] = useState<T[]>([])
  const [future, setFuture] = useState<T[]>([])

  const setWithHistory = useCallback((updater: T | ((prev: T) => T)) => {
    setPresent((prev) => {
      const next = typeof updater === 'function' ? (updater as (p: T) => T)(prev) : updater
      if (Object.is(next, prev)) return prev
      setPast((stack) => [...stack.slice(-19), prev])
      setFuture([])
      return next
    })
  }, [])

  const undo = useCallback(() => {
    setPast((stack) => {
      if (!stack.length) return stack
      const previous = stack[stack.length - 1]
      setPresent((current) => {
        setFuture((f) => [current, ...f])
        return previous
      })
      return stack.slice(0, -1)
    })
  }, [])

  const redo = useCallback(() => {
    setFuture((stack) => {
      if (!stack.length) return stack
      const next = stack[0]
      setPresent((current) => {
        setPast((p) => [...p, current])
        return next
      })
      return stack.slice(1)
    })
  }, [])

  const reset = useCallback((value: T) => {
    setPresent(value)
    setPast([])
    setFuture([])
  }, [])

  return {
    present,
    setPresent: setWithHistory,
    reset,
    undo,
    redo,
    canUndo: past.length > 0,
    canRedo: future.length > 0,
  }
}
