import { ProgressPageNav } from '../progress/ProgressPageNav'

type AgentSessionNavProps = {
  sections: ReadonlyArray<{ id: string; label: string }>
  t: (key: string) => string
}

export function AgentSessionNav({ sections, t }: AgentSessionNavProps) {
  return <ProgressPageNav sections={sections} t={t} />
}
