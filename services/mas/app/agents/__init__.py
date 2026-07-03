"""MAS agent plugins."""

from app.agents.arbiter import ArbiterAgent
from app.agents.catalog_scout import CatalogScoutAgent
from app.agents.planner import PlannerAgent
from app.agents.registry import AgentRegistry, get_default_registry
from app.agents.risk_sentinel import RiskSentinelAgent
from app.agents.student_advocate import StudentAdvocateAgent

__all__ = [
    "AgentRegistry",
    "ArbiterAgent",
    "CatalogScoutAgent",
    "PlannerAgent",
    "RiskSentinelAgent",
    "StudentAdvocateAgent",
    "get_default_registry",
]
