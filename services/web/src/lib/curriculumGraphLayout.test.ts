import { describe, expect, it } from 'vitest'
import {
  buildCurve,
  clampOffset,
  clampZoom,
  closestSides,
  connectedNeighborhood,
  directionalNeighborhood,
  edgeVisualStyle,
  orderNodesWithinSemester,
  panOverscrollPx,
  zoomAroundPoint,
} from './curriculumGraphLayout'
import type { CurriculumGraphEdge, CurriculumGraphNode } from '../types/api'

describe('curriculumGraphLayout', () => {
  it('clamps zoom scale and handles invalid values', () => {
    expect(clampZoom(0.1)).toBe(0.5)
    expect(clampZoom(3)).toBe(2.5)
    expect(clampZoom(Number.NaN)).toBe(1)
  })

  it('allows wide graphs to pan far left and right when zoomed', () => {
    const viewport = { width: 400, height: 300 }
    const content = { width: 2800, height: 600 }
    const scale = 2.5
    const offset = clampOffset({ x: -5000, y: 0 }, scale, viewport, content)
    const overscroll = panOverscrollPx(scale, viewport)
    const slackX = (content.width * scale - viewport.width) * 0.35 + overscroll
    const minX = viewport.width - content.width * scale - slackX
    expect(offset.x).toBeGreaterThanOrEqual(minX)
    expect(offset.x).toBeLessThanOrEqual(slackX)
  })

  it('adds extra pan room when zoomed in', () => {
    const viewport = { width: 800, height: 600 }
    expect(panOverscrollPx(2.5, viewport)).toBeGreaterThan(panOverscrollPx(1, viewport))
  })

  it('chooses horizontal sides for same-row neighbors', () => {
    const sides = closestSides(
      { left: 0, top: 0, width: 100, height: 80 },
      { left: 180, top: 10, width: 100, height: 80 },
    )
    expect(sides).toEqual({ from: 'right', to: 'left' })
  })

  it('chooses vertical sides for stacked semesters', () => {
    const sides = closestSides(
      { left: 0, top: 0, width: 100, height: 80 },
      { left: 20, top: 160, width: 100, height: 80 },
    )
    expect(sides).toEqual({ from: 'bottom', to: 'top' })
  })

  it('orders nodes to align prerequisites before dependents', () => {
    const nodes: CurriculumGraphNode[] = [
      {
        nodeId: 'B',
        courseNumber: 'B',
        semester: 1,
        credits: { display: '3', value: 3, uncertain: false },
        alternatives: [],
        dataQuality: {
          manualReviewRequired: false,
          confidence: 'high',
          hasAlternatives: false,
          creditsUncertain: false,
          verifyWithRegistrar: false,
        },
        prerequisiteNumbers: ['A'],
        status: 'available',
        missingPrerequisites: [],
        isBottleneck: false,
      },
      {
        nodeId: 'A',
        courseNumber: 'A',
        semester: 1,
        credits: { display: '3', value: 3, uncertain: false },
        alternatives: [],
        dataQuality: {
          manualReviewRequired: false,
          confidence: 'high',
          hasAlternatives: false,
          creditsUncertain: false,
          verifyWithRegistrar: false,
        },
        prerequisiteNumbers: [],
        status: 'available',
        missingPrerequisites: [],
        isBottleneck: false,
      },
    ]
    const edges: CurriculumGraphEdge[] = [
      { from: 'A', to: 'B', kind: 'prerequisite', requirementType: 'catalog_text' },
    ]

    const ordered = orderNodesWithinSemester(nodes, edges, new Map())
    expect(ordered.map((node) => node.nodeId)).toEqual(['A', 'B'])
  })

  it('zooms around pointer without drifting origin wildly', () => {
    const result = zoomAroundPoint(1, { x: 0, y: 0 }, { x: 100, y: 100 }, 0.2)
    expect(result.scale).toBeGreaterThan(1)
    expect(result.offset.x).toBeLessThan(0)
    expect(result.offset.y).toBeLessThan(0)
  })

  it('builds finite svg curves with side-aware control points', () => {
    const curve = buildCurve({ x: 10, y: 20 }, { x: 140, y: 25 }, 'right', 'left')
    expect(curve).toContain('M 10 20')
    expect(curve).not.toContain('NaN')
  })

  it('styles edge types differently', () => {
    expect(edgeVisualStyle({ requirementType: 'hard', kind: 'prerequisite' }).markerId).toBe(
      'curriculum-arrow-hard',
    )
    expect(
      edgeVisualStyle({ requirementType: 'corequisite', kind: 'corequisite' }).strokeDasharray,
    ).toBeTruthy()
  })

  it('collects direct graph neighbors for hover highlighting', () => {
    const edges: CurriculumGraphEdge[] = [
      { from: 'A', to: 'B', kind: 'prerequisite', requirementType: 'hard' },
      { from: 'B', to: 'C', kind: 'prerequisite', requirementType: 'catalog_text' },
      { from: 'X', to: 'Y', kind: 'prerequisite', requirementType: 'external' },
    ]

    const neighborhood = connectedNeighborhood('B', edges)
    expect([...neighborhood.nodeIds].sort()).toEqual(['A', 'B', 'C'])
    expect([...neighborhood.edgeIds].sort()).toEqual([
      'A->B:prerequisite',
      'B->C:prerequisite',
    ])
  })

  it('splits hover neighborhood into incoming and outgoing directions', () => {
    const edges: CurriculumGraphEdge[] = [
      { from: 'A', to: 'B', kind: 'prerequisite', requirementType: 'hard' },
      { from: 'B', to: 'C', kind: 'prerequisite', requirementType: 'catalog_text' },
      { from: 'B', to: 'D', kind: 'corequisite', requirementType: 'corequisite' },
    ]

    const neighborhood = directionalNeighborhood('B', edges)
    expect([...neighborhood.incomingNodeIds]).toEqual(['A'])
    expect([...neighborhood.outgoingNodeIds].sort()).toEqual(['C', 'D'])
    expect([...neighborhood.incomingEdgeIds]).toEqual(['A->B:prerequisite'])
    expect([...neighborhood.outgoingEdgeIds].sort()).toEqual([
      'B->C:prerequisite',
      'B->D:corequisite',
    ])
  })

  it('emphasizes incoming and outgoing edges with distinct colors', () => {
    const incoming = edgeVisualStyle(
      { requirementType: 'catalog_text', kind: 'prerequisite' },
      'incoming',
    )
    const outgoing = edgeVisualStyle(
      { requirementType: 'catalog_text', kind: 'prerequisite' },
      'outgoing',
    )

    expect(incoming.stroke).toBe('#0d9488')
    expect(outgoing.stroke).toBe('#7c3aed')
    expect(incoming.markerId).toBe('curriculum-arrow-incoming')
    expect(outgoing.markerId).toBe('curriculum-arrow-outgoing')
  })

  it('keeps requirement-type dash styles when direction is highlighted', () => {
    const incomingCoreq = edgeVisualStyle(
      { requirementType: 'corequisite', kind: 'corequisite' },
      'incoming',
    )
    const outgoingExternal = edgeVisualStyle(
      { requirementType: 'external', kind: 'external_prerequisite' },
      'outgoing',
    )

    expect(incomingCoreq.strokeDasharray).toBeTruthy()
    expect(outgoingExternal.strokeDasharray).toBeTruthy()
  })
})
