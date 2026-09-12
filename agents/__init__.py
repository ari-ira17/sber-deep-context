"""Deep Agents & Orchestration Module for Meridian Knowledge Base."""

from .router_agent import RouterAgent, RouterOutput, MERIDIAN_CATALOG
from .answer_agent import AnswerAgent, AnswerOutput, DocumentContext
from .pipeline import create_deep_agent, DeepAgent, DeepAgentsPipeline, AgentState
from .orchestrator import (
    MeridianOrchestrator,
    OrchestratorResponse,
    StandaloneSearchEngine,
    GraphNode,
    GraphEdge,
    PRODUCT_COLOR_PALETTE,
)

__all__ = [
    "RouterAgent",
    "RouterOutput",
    "MERIDIAN_CATALOG",
    "AnswerAgent",
    "AnswerOutput",
    "DocumentContext",
    "create_deep_agent",
    "DeepAgent",
    "DeepAgentsPipeline",
    "AgentState",
    "MeridianOrchestrator",
    "OrchestratorResponse",
    "StandaloneSearchEngine",
    "GraphNode",
    "GraphEdge",
    "PRODUCT_COLOR_PALETTE",
]
