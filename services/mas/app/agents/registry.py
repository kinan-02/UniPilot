"""Default MAS agent registry."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.arbiter import ArbiterAgent
from app.agents.base import AgentPlugin
from app.agents.catalog_scout import CatalogScoutAgent
from app.agents.explainer import ExplainerAgent
from app.agents.goal_analyst import GoalAnalystAgent
from app.agents.planner import PlannerAgent
from app.agents.progress_scout import ProgressScoutAgent
from app.agents.red_team import RedTeamAgent
from app.agents.risk_sentinel import RiskSentinelAgent
from app.agents.student_advocate import StudentAdvocateAgent


@dataclass
class AgentRegistry:
    """Bundled default agents for the planning vertical (MAS-1.5)."""

    goal_analyst: GoalAnalystAgent = field(default_factory=GoalAnalystAgent)
    planner: PlannerAgent = field(default_factory=PlannerAgent)
    catalog_scout: CatalogScoutAgent = field(default_factory=CatalogScoutAgent)
    risk_sentinel: RiskSentinelAgent = field(default_factory=RiskSentinelAgent)
    progress_scout: ProgressScoutAgent = field(default_factory=ProgressScoutAgent)
    student_advocate: StudentAdvocateAgent = field(default_factory=StudentAdvocateAgent)
    arbiter: ArbiterAgent = field(default_factory=ArbiterAgent)
    explainer: ExplainerAgent = field(default_factory=ExplainerAgent)
    red_team: RedTeamAgent = field(default_factory=RedTeamAgent)

    def hard_critics(self) -> list[AgentPlugin]:
        return [self.catalog_scout, self.risk_sentinel]

    def soft_advocates(self) -> list[AgentPlugin]:
        return [self.progress_scout, self.student_advocate]

    def critics(self) -> list[AgentPlugin]:
        return [*self.hard_critics(), *self.soft_advocates()]

    def all_agents(self) -> list[AgentPlugin]:
        return [
            self.goal_analyst,
            self.planner,
            self.catalog_scout,
            self.risk_sentinel,
            self.progress_scout,
            self.student_advocate,
            self.arbiter,
            self.explainer,
            self.red_team,
        ]


_default_registry: AgentRegistry | None = None


def get_default_registry() -> AgentRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = AgentRegistry()
    return _default_registry
