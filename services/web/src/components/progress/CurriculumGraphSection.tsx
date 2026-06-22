import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Maximize2, Minimize2, ZoomIn, ZoomOut } from 'lucide-react'
import type { CurriculumGraph, CurriculumGraphNode } from '../../types/api'
import {
  clampOffset,
  clampZoom,
  computePrerequisiteEdgePaths,
  directionalNeighborhood,
  edgeVisualStyle,
  type EdgePath,
  initialMindMapOffset,
  measureLayoutSize,
  NODE_HORIZONTAL_GAP_PX,
  orderSemesterRows,
  SEMESTER_ROW_GAP_PX,
  sanitizeOffset,
  zoomAroundPoint,
} from '../../lib/curriculumGraphLayout'
import { Badge, Card } from '../ui/Card'
import { nodeStatusTone } from '../../lib/academicPath'

type CurriculumGraphSectionProps = {
  graph: CurriculumGraph
  t: (key: string) => string
}

function displayNodeStatus(
  node: CurriculumGraphNode,
  compact: boolean,
): CurriculumGraphNode['status'] {
  if (compact && node.status === 'verify_with_registrar') {
    return 'available'
  }
  return node.status
}

type NodeHighlightRole = 'none' | 'active' | 'incoming' | 'outgoing' | 'dimmed'

function NodeCard({
  node,
  t,
  compact = false,
  highlightRole = 'none',
}: {
  node: CurriculumGraphNode
  t: (key: string) => string
  compact?: boolean
  highlightRole?: NodeHighlightRole
}) {
  const status = displayNodeStatus(node, compact)
  const statusKey = `progress.curriculum.status.${status}` as const
  const statusLabel = t(statusKey) !== statusKey ? t(statusKey) : status

  const highlightClass =
    highlightRole === 'active'
      ? 'z-20 border-stone-900 bg-white shadow-lg ring-2 ring-stone-900'
      : highlightRole === 'incoming'
        ? 'z-10 border-teal-600 bg-teal-50/90 shadow-md ring-2 ring-teal-500'
        : highlightRole === 'outgoing'
          ? 'z-10 border-violet-600 bg-violet-50/90 shadow-md ring-2 ring-violet-500'
          : highlightRole === 'dimmed'
            ? 'opacity-25 saturate-50'
            : 'border-[var(--color-border)] bg-white shadow-sm'

  return (
    <article
      className={`w-[11rem] shrink-0 rounded-xl border p-3 transition-[opacity,box-shadow,background-color] duration-150 ${highlightClass}`}
      aria-label={`${node.title ?? node.courseNumber} — ${statusLabel}`}
      data-testid={`curriculum-node-${node.courseNumber}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-xs font-mono text-[var(--color-text-muted)]">
            {node.courseNumber}
          </p>
          <p className="line-clamp-2 text-sm font-medium leading-snug">{node.title}</p>
        </div>
        <Badge tone={nodeStatusTone(status)}>{statusLabel}</Badge>
      </div>
      <p className="mt-2 text-xs text-[var(--color-text-muted)]">
        {t('progress.curriculum.credits')}: {node.credits.display}
        {!compact && node.credits.uncertain ? ` (${t('progress.curriculum.verifyCredits')})` : ''}
      </p>
      {!compact && node.alternatives.length > 0 ? (
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">
          {t('progress.curriculum.alternatives')}: {node.alternatives.join(', ')}
        </p>
      ) : null}
      {!compact && node.missingPrerequisites.length > 0 ? (
        <p className="mt-1 text-xs text-amber-800">
          {t('progress.curriculum.missingPrereqs')}: {node.missingPrerequisites.join(', ')}
        </p>
      ) : null}
    </article>
  )
}

function MindMapView({ graph, t }: { graph: CurriculumGraph; t: (key: string) => string }) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const layoutRef = useRef<HTMLDivElement>(null)
  const transformRef = useRef<HTMLDivElement>(null)
  const nodeRefs = useRef<Map<string, HTMLDivElement>>(new Map())
  const viewRef = useRef({ scale: 1, offset: { x: 0, y: 0 } })
  const [view, setView] = useState(viewRef.current)
  const [edgePaths, setEdgePaths] = useState<EdgePath[]>([])
  const contentSizeRef = useRef({ width: 800, height: 600 })
  const [contentSize, setContentSize] = useState(contentSizeRef.current)
  const dragRef = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null)
  const hasInitializedView = useRef(false)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)

  const hoverNeighborhood = useMemo(
    () => directionalNeighborhood(hoveredNodeId, graph.edges),
    [hoveredNodeId, graph.edges],
  )

  const getNodeHighlightRole = useCallback(
    (nodeId: string): NodeHighlightRole => {
      if (!hoveredNodeId) return 'none'
      if (nodeId === hoveredNodeId) return 'active'
      if (hoverNeighborhood.incomingNodeIds.has(nodeId)) return 'incoming'
      if (hoverNeighborhood.outgoingNodeIds.has(nodeId)) return 'outgoing'
      return 'dimmed'
    },
    [hoveredNodeId, hoverNeighborhood.incomingNodeIds, hoverNeighborhood.outgoingNodeIds],
  )

  const getEdgeEmphasis = useCallback(
    (path: EdgePath) => {
      if (!hoveredNodeId) return 'default' as const
      if (hoverNeighborhood.incomingEdgeIds.has(path.id)) return 'incoming' as const
      if (hoverNeighborhood.outgoingEdgeIds.has(path.id)) return 'outgoing' as const
      return 'dimmed' as const
    },
    [hoveredNodeId, hoverNeighborhood.incomingEdgeIds, hoverNeighborhood.outgoingEdgeIds],
  )

  const sortedEdgePaths = useMemo(() => {
    if (!hoveredNodeId) return edgePaths
    const dimmed = edgePaths.filter(
      (path) =>
        !hoverNeighborhood.incomingEdgeIds.has(path.id) &&
        !hoverNeighborhood.outgoingEdgeIds.has(path.id),
    )
    const incoming = edgePaths.filter((path) => hoverNeighborhood.incomingEdgeIds.has(path.id))
    const outgoing = edgePaths.filter((path) => hoverNeighborhood.outgoingEdgeIds.has(path.id))
    return [...dimmed, ...incoming, ...outgoing]
  }, [
    edgePaths,
    hoveredNodeId,
    hoverNeighborhood.incomingEdgeIds,
    hoverNeighborhood.outgoingEdgeIds,
  ])

  const semesterRows = useMemo(() => {
    const grouped = new Map<number, CurriculumGraphNode[]>()
    graph.semesterLanes.forEach((lane) => {
      const nodes = lane.nodeIds
        .map((id) => graph.nodes.find((node) => node.nodeId === id))
        .filter((node): node is CurriculumGraphNode => Boolean(node))
      grouped.set(lane.semester, nodes)
    })
    const rows = [...grouped.entries()].sort(([a], [b]) => a - b)
    return orderSemesterRows(rows, graph.edges)
  }, [graph.nodes, graph.semesterLanes, graph.edges])

  const applyView = useCallback(
    (
      next: { scale: number; offset: { x: number; y: number } },
      options?: { clamp?: boolean },
    ) => {
      const viewport = viewportRef.current
      const safeScale = clampZoom(next.scale)
      const rawOffset = sanitizeOffset(next.offset)
      const safeOffset =
        viewport && options?.clamp === true
          ? clampOffset(
              rawOffset,
              safeScale,
              { width: viewport.clientWidth, height: viewport.clientHeight },
              contentSizeRef.current,
            )
          : rawOffset
      const prev = viewRef.current
      if (
        prev.scale === safeScale &&
        prev.offset.x === safeOffset.x &&
        prev.offset.y === safeOffset.y
      ) {
        return
      }
      const resolved = { scale: safeScale, offset: safeOffset }
      viewRef.current = resolved
      setView(resolved)
    },
    [],
  )

  const registerNode = useCallback((nodeId: string) => {
    return (element: HTMLDivElement | null) => {
      if (element) nodeRefs.current.set(nodeId, element)
      else nodeRefs.current.delete(nodeId)
    }
  }, [])

  const refreshLayout = useCallback(() => {
    const layout = layoutRef.current
    const viewport = viewportRef.current
    if (!layout) return
    const nextPaths = computePrerequisiteEdgePaths(layout, graph.edges, nodeRefs.current)
    const measured = measureLayoutSize(layout)
    if (
      measured.width !== contentSizeRef.current.width ||
      measured.height !== contentSizeRef.current.height
    ) {
      contentSizeRef.current = measured
      setContentSize(measured)
    }
    setEdgePaths((prev) => {
      if (
        prev.length === nextPaths.length &&
        prev.every((path, index) => path.id === nextPaths[index]?.id && path.d === nextPaths[index]?.d)
      ) {
        return prev
      }
      return nextPaths
    })

    if (viewport && !hasInitializedView.current) {
      const nodeCount = layout.querySelectorAll('[data-curriculum-node]').length
      if (nodeCount === 0) return

      hasInitializedView.current = true
      applyView({
        scale: 1,
        offset: initialMindMapOffset(
          { width: viewport.clientWidth, height: viewport.clientHeight },
          measured,
        ),
      })
    }
  }, [graph.edges, applyView])

  useLayoutEffect(() => {
    hasInitializedView.current = false
  }, [graph.trackSlug, graph.programCode])

  useLayoutEffect(() => {
    let cancelled = false
    let frame = 0
    const run = () => {
      if (cancelled) return
      refreshLayout()
    }
    run()
    frame = requestAnimationFrame(run)
    return () => {
      cancelled = true
      cancelAnimationFrame(frame)
    }
  }, [refreshLayout, semesterRows.length, graph.trackSlug, graph.programCode])

  useEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) return

    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      const rect = viewport.getBoundingClientRect()
      const pointer = { x: event.clientX - rect.left, y: event.clientY - rect.top }
      const delta = -event.deltaY * 0.0012
      const current = viewRef.current
      const next = zoomAroundPoint(current.scale, current.offset, pointer, delta)
      applyView(next)
    }

    viewport.addEventListener('wheel', onWheel, { passive: false })
    return () => viewport.removeEventListener('wheel', onWheel)
  }, [applyView])

  const onPointerDown = useCallback((event: React.PointerEvent) => {
    if ((event.target as HTMLElement).closest('button')) return
    const current = viewRef.current
    dragRef.current = {
      x: event.clientX,
      y: event.clientY,
      ox: current.offset.x,
      oy: current.offset.y,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
  }, [])

  const onPointerMove = useCallback(
    (event: React.PointerEvent) => {
      if (!dragRef.current) return
      const nextOffset = {
        x: dragRef.current.ox + (event.clientX - dragRef.current.x),
        y: dragRef.current.oy + (event.clientY - dragRef.current.y),
      }
      const current = viewRef.current
      applyView({ scale: current.scale, offset: nextOffset })
    },
    [applyView],
  )

  const onPointerUp = useCallback(() => {
    dragRef.current = null
  }, [])

  const clearHover = useCallback((event?: React.MouseEvent) => {
    if (dragRef.current) return
    const nextTarget = event?.relatedTarget
    if (nextTarget instanceof HTMLElement && nextTarget.closest('[data-curriculum-node]')) {
      return
    }
    setHoveredNodeId(null)
  }, [])

  const adjustZoom = (delta: number) => {
    const viewport = viewportRef.current
    if (!viewport) return
    const rect = viewport.getBoundingClientRect()
    const pointer = { x: rect.width / 2, y: rect.height / 2 }
    const current = viewRef.current
    applyView(zoomAroundPoint(current.scale, current.offset, pointer, delta))
  }

  const resetView = () => {
    const viewport = viewportRef.current
    const layout = layoutRef.current
    if (!viewport || !layout) return
    const measured = measureLayoutSize(layout)
    applyView({
      scale: 1,
      offset: initialMindMapOffset(
        { width: viewport.clientWidth, height: viewport.clientHeight },
        measured,
      ),
    })
    requestAnimationFrame(refreshLayout)
  }

  const edgeLegend = [
    { type: 'hard', label: t('progress.curriculum.edgeLegend.hard') },
    { type: 'catalog_text', label: t('progress.curriculum.edgeLegend.catalogText') },
    { type: 'corequisite', label: t('progress.curriculum.edgeLegend.corequisite') },
    { type: 'external', label: t('progress.curriculum.edgeLegend.external') },
    { type: 'incoming', label: t('progress.curriculum.edgeLegend.incomingHover') },
    { type: 'outgoing', label: t('progress.curriculum.edgeLegend.outgoingHover') },
  ]

  return (
    <div className="space-y-3" data-testid="curriculum-mindmap">
      <p className="text-sm text-amber-900" role="note">
        {t('progress.curriculum.mindMapDisclaimer')}
      </p>

      <div className="flex flex-wrap items-center gap-3 text-xs text-[var(--color-text-muted)]">
        {edgeLegend.map((item) => {
          const style =
            item.type === 'incoming'
              ? edgeVisualStyle(
                  { requirementType: 'catalog_text', kind: 'prerequisite' },
                  'incoming',
                )
              : item.type === 'outgoing'
                ? edgeVisualStyle(
                    { requirementType: 'catalog_text', kind: 'prerequisite' },
                    'outgoing',
                  )
                : edgeVisualStyle({
                    requirementType: item.type as EdgePath['requirementType'],
                    kind: item.type === 'corequisite' ? 'corequisite' : 'prerequisite',
                  })
          return (
            <span key={item.type} className="inline-flex items-center gap-2">
              <svg width="28" height="10" aria-hidden>
                <line
                  x1="0"
                  y1="5"
                  x2="24"
                  y2="5"
                  stroke={style.stroke}
                  strokeWidth={style.strokeWidth}
                  strokeDasharray={style.strokeDasharray}
                />
              </svg>
              {item.label}
            </span>
          )
        })}
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          className="rounded-lg border px-2 py-1 text-xs"
          onClick={() => adjustZoom(0.12)}
          aria-label={t('progress.curriculum.zoomIn')}
        >
          <ZoomIn className="h-4 w-4" />
        </button>
        <button
          type="button"
          className="rounded-lg border px-2 py-1 text-xs"
          onClick={() => adjustZoom(-0.12)}
          aria-label={t('progress.curriculum.zoomOut')}
        >
          <ZoomOut className="h-4 w-4" />
        </button>
        <button
          type="button"
          className="rounded-lg border px-2 py-1 text-xs"
          onClick={resetView}
        >
          {t('progress.curriculum.resetView')}
        </button>
        <span className="text-xs text-[var(--color-text-muted)]">
          {Math.round(view.scale * 100)}%
        </span>
      </div>

      <div
        ref={viewportRef}
        className="h-[min(72vh,52rem)] min-h-[28rem] cursor-grab overflow-hidden rounded-xl border border-[var(--color-border)] bg-[radial-gradient(circle,_#d6d3d1_1px,_transparent_1px)] bg-[length:20px_20px] bg-stone-50 active:cursor-grabbing"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => {
          onPointerUp()
          clearHover()
        }}
        onMouseLeave={clearHover}
        role="img"
        aria-label={t('progress.curriculum.mindMapAria')}
      >
        <div
          ref={transformRef}
          className="origin-top-left will-change-transform"
          style={{
            transform: `translate(${view.offset.x}px, ${view.offset.y}px) scale(${view.scale})`,
          }}
        >
          <div ref={layoutRef} className="relative inline-block min-w-max p-8">
            <svg
              className="pointer-events-none absolute left-0 top-0 z-0 overflow-visible"
              width={contentSize.width}
              height={contentSize.height}
              aria-hidden
            >
              <defs>
                <marker id="curriculum-arrow-hard" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
                  <path d="M0,0 L10,5 L0,10 Z" fill="#1c1917" />
                </marker>
                <marker id="curriculum-arrow-catalog" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
                  <path d="M0,0 L10,5 L0,10 Z" fill="#57534e" />
                </marker>
                <marker id="curriculum-arrow-external" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
                  <path d="M0,0 L10,5 L0,10 Z" fill="#a8a29e" />
                </marker>
                <marker id="curriculum-arrow-corequisite" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
                  <path d="M0,0 L10,5 L0,10 Z" fill="#0369a1" />
                </marker>
                <marker id="curriculum-arrow-bottleneck" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
                  <path d="M0,0 L10,5 L0,10 Z" fill="#c2410c" />
                </marker>
                <marker id="curriculum-arrow-incoming" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
                  <path d="M0,0 L10,5 L0,10 Z" fill="#0d9488" />
                </marker>
                <marker id="curriculum-arrow-outgoing" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
                  <path d="M0,0 L10,5 L0,10 Z" fill="#7c3aed" />
                </marker>
              </defs>
              {sortedEdgePaths.map((path) => {
                const style = edgeVisualStyle(path, getEdgeEmphasis(path))
                return (
                  <path
                    key={path.id}
                    d={path.d}
                    fill="none"
                    stroke={style.stroke}
                    strokeWidth={style.strokeWidth}
                    strokeDasharray={style.strokeDasharray}
                    markerEnd={`url(#${style.markerId})`}
                    opacity={style.opacity}
                  />
                )
              })}
            </svg>

            <div
              className="relative z-10 flex flex-col"
              data-curriculum-semesters
              style={{ gap: `${SEMESTER_ROW_GAP_PX}px` }}
            >
              {semesterRows.map(([semester, nodes]) => (
                <div key={semester} className="flex flex-col gap-3 pb-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                    {t('progress.curriculum.semester')} {semester}
                  </p>
                  <div
                    className="flex flex-nowrap items-start"
                    style={{ gap: `${NODE_HORIZONTAL_GAP_PX}px` }}
                  >
                    {nodes.map((node) => (
                      <div
                        key={node.nodeId}
                        ref={registerNode(node.nodeId)}
                        data-curriculum-node={node.nodeId}
                        className="relative transition-opacity duration-150"
                        onMouseEnter={() => setHoveredNodeId(node.nodeId)}
                        onMouseLeave={(event) => clearHover(event)}
                      >
                        <NodeCard
                          node={node}
                          t={t}
                          compact
                          highlightRole={getNodeHighlightRole(node.nodeId)}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export function CurriculumGraphSection({ graph, t }: CurriculumGraphSectionProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <Card className="space-y-4" data-testid="curriculum-graph-section">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{t('progress.curriculum.title')}</h2>
          <p className="text-sm text-[var(--color-text-muted)]">
            {t('progress.curriculum.subtitle')}
          </p>
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-sm font-medium"
          onClick={() => setExpanded((value) => !value)}
          aria-pressed={expanded}
          aria-expanded={expanded}
        >
          {expanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          {expanded
            ? t('progress.curriculum.collapseView')
            : t('progress.curriculum.expandMindMap')}
        </button>
      </div>

      {expanded ? <MindMapView graph={graph} t={t} /> : null}
    </Card>
  )
}
