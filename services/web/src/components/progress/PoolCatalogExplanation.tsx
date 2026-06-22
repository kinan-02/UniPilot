import { cn } from '../../lib/utils'

type PoolCatalogExplanationProps = {
  lines: string[]
  heading: string
  compact?: boolean
}

export function PoolCatalogExplanation({ lines, heading, compact = false }: PoolCatalogExplanationProps) {
  if (!lines.length) return null

  return (
    <div
      className={cn(
        'rounded-lg border border-violet-100 bg-violet-50/60 text-violet-950',
        compact ? 'px-3 py-2 text-xs leading-relaxed' : 'px-3.5 py-3 text-sm leading-relaxed',
      )}
      data-testid="pool-catalog-explanation"
    >
      <p className={cn('font-medium', compact ? 'mb-1' : 'mb-1.5')}>{heading}</p>
      <div className={cn('space-y-1 text-violet-900/90', compact && 'line-clamp-3')}>
        {lines.map((line) => (
          <p key={line}>{line}</p>
        ))}
      </div>
    </div>
  )
}
