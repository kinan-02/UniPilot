import { useEffect, useState, type RefObject } from 'react'

type VirtualRange = {
  start: number
  end: number
}

export function useVirtualList<T>({
  items,
  itemHeight,
  overscan = 6,
  scrollElementRef,
}: {
  items: T[]
  itemHeight: number
  overscan?: number
  scrollElementRef: RefObject<HTMLElement | null>
}): {
  virtualItems: Array<{ item: T; index: number }>
  totalHeight: number
  offsetY: number
} {
  const [range, setRange] = useState<VirtualRange>({ start: 0, end: 24 })

  useEffect(() => {
    const element = scrollElementRef.current
    if (!element) return

    const updateRange = () => {
      const viewportHeight = element.clientHeight
      const scrollTop = element.scrollTop
      const start = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan)
      const visibleCount = Math.ceil(viewportHeight / itemHeight) + overscan * 2
      const end = Math.min(items.length, start + visibleCount)
      setRange((previous) =>
        previous.start === start && previous.end === end ? previous : { start, end },
      )
    }

    updateRange()
    element.addEventListener('scroll', updateRange, { passive: true })
    window.addEventListener('resize', updateRange)

    return () => {
      element.removeEventListener('scroll', updateRange)
      window.removeEventListener('resize', updateRange)
    }
  }, [itemHeight, items.length, overscan, scrollElementRef])

  return {
    virtualItems: items.slice(range.start, range.end).map((item, offset) => ({
      item,
      index: range.start + offset,
    })),
    totalHeight: items.length * itemHeight,
    offsetY: range.start * itemHeight,
  }
}
