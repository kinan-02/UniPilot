import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import {
  buildChainRequirementView,
  hasStructuredChainLayout,
  resolvePoolChainLayout,
} from './chainRequirementSteps'
import type { ElectiveBucket } from '../types/api'

const t = (key: string) => key

type ContractPool = {
  programCode: string
  suffix: string
  minCourseRefs: number
}

type ContractFile = {
  institutionId: string
  faculties: Record<
    string,
    {
      deprecatedPoolSuffixes: string[]
      pools: ContractPool[]
    }
  >
}

const contractPath = join(
  dirname(fileURLToPath(import.meta.url)),
  '../../../data-engineering/data/contracts/elective_chain_pools.json',
)

function loadContract(): ContractFile {
  return JSON.parse(readFileSync(contractPath, 'utf-8')) as ContractFile
}

function ddsPools(): ContractPool[] {
  return loadContract().faculties.dds?.pools ?? []
}

function chainPool(suffix: string, count: number): ElectiveBucket {
  const courses = Array.from({ length: count }, (_, index) => ({
    courseNumber: String(960600 + index).padStart(8, '0'),
    title: `Course ${index}`,
    credits: 3,
  }))
  return {
    groupId: `program:${suffix}`,
    title: suffix,
    rule: { type: 'choose_chain' },
    courses,
    courseCount: courses.length,
    linkedCreditBucketId: 'elective-faculty',
  }
}

describe('electiveChainRegression', () => {
  it('every contract pool has a structured chain layout', () => {
    for (const entry of ddsPools()) {
      const pool = chainPool(entry.suffix, entry.minCourseRefs)
      expect(hasStructuredChainLayout(pool)).toBe(true)
      const layout = resolvePoolChainLayout(pool)
      expect(layout).not.toBeNull()
      if (layout?.type === 'steps') {
        expect(layout.steps.length).toBeGreaterThan(0)
      }
      if (layout?.type === 'pick_one_chain') {
        expect(layout.chains.length).toBeGreaterThan(0)
      }
    }
  })

  it('deprecated combined IE focus pool is not part of the contract', () => {
    const dds = loadContract().faculties.dds
    expect(dds?.deprecatedPoolSuffixes).toContain('ie-focus-chain')
    expect(ddsPools().some((pool) => pool.suffix === 'ie-focus-chain')).toBe(false)
  })

  it('IS performance chain layout resolves courses when pool uses vault numbers', () => {
    const pool: ElectiveBucket = {
      groupId: 'program:is-focus-chain-performance',
      title: 'Performance',
      rule: { type: 'choose_chain' },
      courses: [
        { courseNumber: '00960327', title: 'Nonlinear OR', credits: 3.5 },
        { courseNumber: '00960324', title: 'Service systems', credits: 3.5 },
        { courseNumber: '00960311', title: 'Elective', credits: 3.5 },
      ],
      courseCount: 3,
      linkedCreditBucketId: 'elective-faculty',
    }
    const view = buildChainRequirementView(pool, t, new Set())
    expect(view?.layout).toBe('steps')
    if (view?.layout !== 'steps') return
    expect(view.steps.filter((step) => step.courses.length > 0).length).toBeGreaterThan(0)
  })
})
