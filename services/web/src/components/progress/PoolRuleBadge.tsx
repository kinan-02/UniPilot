import { Badge } from '../ui/Card'
import { interpolateTemplate, localizedChainName, ruleBadgeTone, ruleOperatorTranslationKey } from '../../lib/electivePools'
import type { ElectiveBucket } from '../../types/api'

type PoolRuleBadgeProps = {
  pool: ElectiveBucket
  t: (key: string) => string
}

export function PoolRuleBadge({ pool, t }: PoolRuleBadgeProps) {
  const operatorKey = ruleOperatorTranslationKey(pool.rule.operator)
  const label = t(operatorKey) !== operatorKey ? t(operatorKey) : pool.rule.operator ?? '—'

  return (
    <div className="flex flex-wrap gap-1.5">
      <Badge tone={ruleBadgeTone(pool.rule.operator)}>{label}</Badge>
      {pool.rule.chooseCount != null ? (
        <Badge tone="neutral">
          {interpolateTemplate(t('progress.electiveExplorer.chooseCount'), {
            count: pool.rule.chooseCount,
          })}
        </Badge>
      ) : null}
      {pool.rule.chain ? (
        <Badge tone="neutral">
          {interpolateTemplate(t('progress.electiveExplorer.chain'), {
            name: localizedChainName(pool.rule.chain, t),
          })}
        </Badge>
      ) : null}
    </div>
  )
}
