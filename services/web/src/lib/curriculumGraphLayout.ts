import type { CurriculumGraph, CurriculumGraphEdge, CurriculumGraphNode } from '../types/api'

export type PrerequisiteRequirementType = 'hard' | 'catalog_text' | 'external' | 'corequisite'

export type EdgePath = {
  id: string
  d: string
  requirementType: PrerequisiteRequirementType
  kind: CurriculumGraphEdge['kind']
  highlight?: string
}

export type EdgeVisualStyle = {
  stroke: string
  strokeWidth: number
  strokeDasharray?: string
  markerId: string
  opacity: number
}

type Point = { x: number; y: number }
type Side = 'top' | 'bottom' | 'left' | 'right'

type Box = { left: number; top: number; width: number; height: number }

export const SEMESTER_ROW_GAP_PX = 72
export const NODE_HORIZONTAL_GAP_PX = 48
export const LAYOUT_PADDING_PX = 48
const PAN_OVERSCROLL_PX = 120

/** Extra pan room on each side; grows slightly when zoomed in. */
export function panOverscrollPx(
  scale: number,
  viewport: { width: number; height: number },
): number {
  const base = Math.max(PAN_OVERSCROLL_PX, viewport.width * 0.1, viewport.height * 0.08)
  return Math.round(base + Math.max(0, scale - 1) * base * 0.5)
}

/**
 * Layout-space box relative to container.
 * Uses offsetParent chain so positions stay stable while the viewport pans/zooms.
 */
export function elementBoxWithin(container: HTMLElement, element: HTMLElement): Box {
  let left = 0
  let top = 0
  let current: HTMLElement | null = element

  while (current && current !== container) {
    left += current.offsetLeft
    top += current.offsetTop
    const parent = current.offsetParent as HTMLElement | null
    if (!parent || parent === container) break
    if (!container.contains(parent)) break
    current = parent
  }

  return {
    left,
    top,
    width: element.offsetWidth,
    height: element.offsetHeight,
  }
}

export function measureLayoutSize(layout: HTMLElement): { width: number; height: number } {
  const nodes = layout.querySelectorAll('[data-curriculum-node]')
  let maxRight = 0
  let maxBottom = 0

  nodes.forEach((element) => {
    const box = elementBoxWithin(layout, element as HTMLElement)
    maxRight = Math.max(maxRight, box.left + box.width)
    maxBottom = Math.max(maxBottom, box.top + box.height)
  })

  if (maxRight === 0 && maxBottom === 0) {
    return {
      width: Math.max(layout.scrollWidth, 1),
      height: Math.max(layout.scrollHeight, 1),
    }
  }

  return {
    width: maxRight + LAYOUT_PADDING_PX,
    height: maxBottom + LAYOUT_PADDING_PX,
  }
}

function boxCenter(box: Box): Point {
  return { x: box.left + box.width / 2, y: box.top + box.height / 2 }
}

export function closestSides(fromBox: Box, toBox: Box): { from: Side; to: Side } {
  const fromCenter = boxCenter(fromBox)
  const toCenter = boxCenter(toBox)
  const dx = toCenter.x - fromCenter.x
  const dy = toCenter.y - fromCenter.y

  if (Math.abs(dx) > Math.abs(dy) * 0.85) {
    return dx >= 0 ? { from: 'right', to: 'left' } : { from: 'left', to: 'right' }
  }

  return dy >= 0 ? { from: 'bottom', to: 'top' } : { from: 'top', to: 'bottom' }
}

function anchorPointOnSide(box: Box, side: Side, slot: number, slotCount: number): Point {
  const inset = 0.12
  const ratio = slotCount <= 1 ? 0.5 : inset + (slot / (slotCount - 1)) * (1 - inset * 2)

  switch (side) {
    case 'top':
      return { x: box.left + box.width * ratio, y: box.top }
    case 'bottom':
      return { x: box.left + box.width * ratio, y: box.top + box.height }
    case 'left':
      return { x: box.left, y: box.top + box.height * ratio }
    case 'right':
      return { x: box.left + box.width, y: box.top + box.height * ratio }
  }
}

function isFinitePoint(point: Point): boolean {
  return Number.isFinite(point.x) && Number.isFinite(point.y)
}

export function buildCurve(
  from: Point,
  to: Point,
  fromSide: Side,
  toSide: Side,
): string | null {
  if (!isFinitePoint(from) || !isFinitePoint(to)) {
    return null
  }

  const dx = to.x - from.x
  const dy = to.y - from.y
  const distance = Math.hypot(dx, dy) || 1
  const control = Math.min(distance * 0.38, SEMESTER_ROW_GAP_PX * 0.75, NODE_HORIZONTAL_GAP_PX * 2.5)

  const c1 = { ...from }
  const c2 = { ...to }

  switch (fromSide) {
    case 'right':
      c1.x += control
      break
    case 'left':
      c1.x -= control
      break
    case 'bottom':
      c1.y += control
      break
    case 'top':
      c1.y -= control
      break
  }

  switch (toSide) {
    case 'right':
      c2.x += control
      break
    case 'left':
      c2.x -= control
      break
    case 'bottom':
      c2.y += control
      break
    case 'top':
      c2.y -= control
      break
  }

  return `M ${from.x} ${from.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${to.x} ${to.y}`
}

type EdgeDraft = {
  edge: CurriculumGraphEdge
  fromBox: Box
  toBox: Box
  fromSide: Side
  toSide: Side
}

function distributeSideSlots(drafts: EdgeDraft[]): Map<string, { slot: number; count: number }> {
  const groups = new Map<string, EdgeDraft[]>()

  for (const draft of drafts) {
    const fromKey = `${draft.edge.from}:out:${draft.fromSide}`
    const toKey = `${draft.edge.to}:in:${draft.toSide}`
    groups.set(fromKey, [...(groups.get(fromKey) ?? []), draft])
    groups.set(toKey, [...(groups.get(toKey) ?? []), draft])
  }

  const slotLookup = new Map<string, { slot: number; count: number }>()

  for (const [groupKey, groupDrafts] of groups) {
    const sorted = [...groupDrafts].sort((a, b) => {
      const aCenter = groupKey.includes(':out:')
        ? boxCenter(a.toBox).x + boxCenter(a.toBox).y
        : boxCenter(a.fromBox).x + boxCenter(a.fromBox).y
      const bCenter = groupKey.includes(':out:')
        ? boxCenter(b.toBox).x + boxCenter(b.toBox).y
        : boxCenter(b.fromBox).x + boxCenter(b.fromBox).y
      return aCenter - bCenter
    })

    sorted.forEach((draft, index) => {
      const isOutgoing = groupKey.includes(':out:')
      const nodeId = isOutgoing ? draft.edge.from : draft.edge.to
      const side = isOutgoing ? draft.fromSide : draft.toSide
      const key = `${nodeId}:${isOutgoing ? 'out' : 'in'}:${side}:${draft.edge.from}->${draft.edge.to}`
      slotLookup.set(key, { slot: index, count: sorted.length })
    })
  }

  return slotLookup
}

export function edgeVisualStyle(
  edge: Pick<CurriculumGraphEdge, 'requirementType' | 'kind' | 'highlight'>,
): EdgeVisualStyle {
  if (edge.highlight === 'bottleneck') {
    return {
      stroke: '#c2410c',
      strokeWidth: 2.75,
      markerId: 'curriculum-arrow-bottleneck',
      opacity: 1,
    }
  }

  if (edge.kind === 'corequisite' || edge.requirementType === 'corequisite') {
    return {
      stroke: '#0369a1',
      strokeWidth: 2,
      strokeDasharray: '4 5',
      markerId: 'curriculum-arrow-corequisite',
      opacity: 0.95,
    }
  }

  if (edge.requirementType === 'hard') {
    return {
      stroke: '#1c1917',
      strokeWidth: 2.75,
      markerId: 'curriculum-arrow-hard',
      opacity: 1,
    }
  }

  if (edge.requirementType === 'external') {
    return {
      stroke: '#a8a29e',
      strokeWidth: 2,
      strokeDasharray: '7 5',
      markerId: 'curriculum-arrow-external',
      opacity: 0.85,
    }
  }

  return {
    stroke: '#57534e',
    strokeWidth: 2,
    markerId: 'curriculum-arrow-catalog',
    opacity: 0.95,
  }
}

export function computePrerequisiteEdgePaths(
  container: HTMLElement,
  edges: CurriculumGraph['edges'],
  nodeElements: Map<string, HTMLElement>,
): EdgePath[] {
  const drawableKinds = new Set(['prerequisite', 'corequisite', 'external_prerequisite'])
  const drafts: EdgeDraft[] = []

  for (const edge of edges) {
    if (!drawableKinds.has(edge.kind)) continue

    const fromEl = nodeElements.get(edge.from)
    const toEl = nodeElements.get(edge.to)
    if (!fromEl || !toEl) continue

    const fromBox = elementBoxWithin(container, fromEl)
    const toBox = elementBoxWithin(container, toEl)
    const sides = closestSides(fromBox, toBox)

    drafts.push({
      edge,
      fromBox,
      toBox,
      fromSide: sides.from,
      toSide: sides.to,
    })
  }

  const slotLookup = distributeSideSlots(drafts)
  const paths: EdgePath[] = []

  for (const draft of drafts) {
    const outKey = `${draft.edge.from}:out:${draft.fromSide}:${draft.edge.from}->${draft.edge.to}`
    const inKey = `${draft.edge.to}:in:${draft.toSide}:${draft.edge.from}->${draft.edge.to}`
    const outSlot = slotLookup.get(outKey) ?? { slot: 0, count: 1 }
    const inSlot = slotLookup.get(inKey) ?? { slot: 0, count: 1 }

    const from = anchorPointOnSide(draft.fromBox, draft.fromSide, outSlot.slot, outSlot.count)
    const to = anchorPointOnSide(draft.toBox, draft.toSide, inSlot.slot, inSlot.count)
    const curve = buildCurve(from, to, draft.fromSide, draft.toSide)
    if (!curve) continue

    paths.push({
      id: `${draft.edge.from}->${draft.edge.to}:${draft.edge.kind}`,
      d: curve,
      requirementType: draft.edge.requirementType ?? 'catalog_text',
      kind: draft.edge.kind,
      highlight: draft.edge.highlight,
    })
  }

  return paths
}

export function orderNodesWithinSemester(
  nodes: CurriculumGraphNode[],
  edges: CurriculumGraphEdge[],
  priorPositions: Map<string, number>,
): CurriculumGraphNode[] {
  if (nodes.length <= 1) return nodes

  const byId = new Map(nodes.map((node) => [node.nodeId, node]))
  const localIds = nodes.map((node) => node.nodeId)

  const positionOf = (nodeId: string, currentOrder: string[]): number => {
    const localIndex = currentOrder.indexOf(nodeId)
    if (localIndex >= 0) return localIndex
    return priorPositions.get(nodeId) ?? 0
  }

  let order = [...localIds]

  for (let pass = 0; pass < 10; pass += 1) {
    const scored = order.map((id, index) => {
      const related = edges.filter(
        (edge) =>
          (edge.to === id || edge.from === id) &&
          (order.includes(edge.from) ||
            order.includes(edge.to) ||
            priorPositions.has(edge.from) ||
            priorPositions.has(edge.to)),
      )

      if (related.length === 0) {
        return { id, score: index }
      }

      const score =
        related.reduce((sum, edge) => {
          if (edge.to === id) {
            return sum + positionOf(edge.from, order) + 0.5
          }
          if (edge.from === id) {
            return sum + positionOf(edge.to, order) - 0.5
          }
          return sum
        }, 0) / related.length

      return { id, score }
    })

    scored.sort((a, b) => a.score - b.score || order.indexOf(a.id) - order.indexOf(b.id))
    order = scored.map((entry) => entry.id)
  }

  return order
    .map((id) => byId.get(id))
    .filter((node): node is CurriculumGraphNode => Boolean(node))
}

export function orderSemesterRows(
  semesterRows: Array<[number, CurriculumGraphNode[]]>,
  edges: CurriculumGraphEdge[],
): Array<[number, CurriculumGraphNode[]]> {
  const priorPositions = new Map<string, number>()

  return semesterRows.map(([semester, nodes]) => {
    const ordered = orderNodesWithinSemester(nodes, edges, priorPositions)
    ordered.forEach((node, index) => priorPositions.set(node.nodeId, index))
    return [semester, ordered] as [number, CurriculumGraphNode[]]
  })
}

export function clampZoom(scale: number, min = 0.5, max = 2.5): number {
  if (!Number.isFinite(scale)) return 1
  return Math.min(max, Math.max(min, scale))
}

export function sanitizeOffset(offset: { x: number; y: number }): { x: number; y: number } {
  return {
    x: Number.isFinite(offset.x) ? offset.x : 0,
    y: Number.isFinite(offset.y) ? offset.y : 0,
  }
}

export function clampOffset(
  offset: { x: number; y: number },
  scale: number,
  viewport: { width: number; height: number },
  content: { width: number; height: number },
): { x: number; y: number } {
  const safe = sanitizeOffset(offset)
  const scaledWidth = content.width * scale
  const scaledHeight = content.height * scale
  const overscroll = panOverscrollPx(scale, viewport)

  if (scaledWidth <= viewport.width) {
    const centeredX = (viewport.width - scaledWidth) / 2
    return {
      x: Math.min(centeredX + overscroll, Math.max(centeredX - overscroll, safe.x)),
      y:
        scaledHeight <= viewport.height
          ? Math.min(
              (viewport.height - scaledHeight) / 2 + overscroll,
              Math.max((viewport.height - scaledHeight) / 2 - overscroll, safe.y),
            )
          : safe.y,
    }
  }

  const slackX = (scaledWidth - viewport.width) * 0.35 + overscroll
  const slackY =
    scaledHeight > viewport.height ? (scaledHeight - viewport.height) * 0.35 + overscroll : overscroll

  return {
    x: Math.min(slackX, Math.max(viewport.width - scaledWidth - slackX, safe.x)),
    y: Math.min(slackY, Math.max(viewport.height - scaledHeight - slackY, safe.y)),
  }
}

export function zoomAroundPoint(
  scale: number,
  offset: { x: number; y: number },
  pointer: { x: number; y: number },
  delta: number,
  bounds?: {
    viewport: { width: number; height: number }
    content: { width: number; height: number }
  },
): { scale: number; offset: { x: number; y: number } } {
  const safeScale = clampZoom(scale)
  const nextScale = clampZoom(safeScale * (1 + delta))
  const ratio = nextScale / safeScale
  const nextOffset = {
    x: pointer.x - ratio * (pointer.x - offset.x),
    y: pointer.y - ratio * (pointer.y - offset.y),
  }

  if (!bounds) {
    return { scale: nextScale, offset: sanitizeOffset(nextOffset) }
  }

  return {
    scale: nextScale,
    offset: sanitizeOffset(nextOffset),
  }
}

export function initialMindMapOffset(
  viewport: { width: number; height: number },
  content: { width: number; height: number },
): { x: number; y: number } {
  const margin = 40
  return {
    x: content.width > viewport.width ? margin : (viewport.width - content.width) / 2,
    y: margin,
  }
}
