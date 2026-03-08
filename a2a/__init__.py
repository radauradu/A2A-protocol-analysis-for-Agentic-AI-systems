"""
Agent-to-Agent (A2A) Communication Protocol

This module implements the A2A protocol for agent communication following JSON-RPC 2.0 standard.
Includes AgentCard discovery, A2A messaging, and execution.
"""

from .protocol import A2AMessage, A2AResponse, A2AError, AgentCard, AgentCardSkill
from .executor import A2AAgentExecutor
from .client import A2AClient
from .agent_cards import INSIGHT_AGENT_CARD, PLOT_AGENT_CARD, get_agent_card

__all__ = [
    "A2AMessage",
    "A2AResponse", 
    "A2AError",
    "AgentCard",
    "AgentCardSkill",
    "A2AAgentExecutor",
    "A2AClient",
    "INSIGHT_AGENT_CARD",
    "PLOT_AGENT_CARD",
    "get_agent_card",
]

