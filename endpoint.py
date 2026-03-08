import os
import json

# Set service name for Phoenix tracing (Env1 service)
os.environ.setdefault("OTEL_SERVICE_NAME", "torrado_env1_orchestrator")

from fastapi import FastAPI, HTTPException, Query, Request
from utils_copy import run_graph_with_tracing
from pydantic import BaseModel
from uuid import uuid4
from typing import Dict, Any, Optional

from env1_env2_a2a_wrapper import run_env1_then_env2_a2a
from env3_openai_agents_wrapper import run_env3_openai_agents_with_tracking

# Import A2A components
from a2a import get_agent_card, A2AMessage
from a2a.agent_cards import AGENT_CARDS
from a2a.protocol import AgentCard

app = FastAPI(title="Torrado Multi-Agent System with A2A Protocol")


@app.on_event("startup")
async def register_local_agents():
    from a2a.agent_cards import SQL_AGENT_CARD, INSIGHT_AGENT_CARD
    AGENT_CARDS["sql"] = SQL_AGENT_CARD
    AGENT_CARDS["insight"] = INSIGHT_AGENT_CARD
    sql_bytes = len(json.dumps(SQL_AGENT_CARD.dict()).encode("utf-8"))
    insight_bytes = len(json.dumps(INSIGHT_AGENT_CARD.dict()).encode("utf-8"))
    print(f"[Registry] sql registered in-process ({sql_bytes} bytes, no HTTP)", flush=True)
    print(f"[Registry] insight registered in-process ({insight_bytes} bytes, no HTTP)", flush=True)

class PromptRequest(BaseModel):
    prompt: str

@app.post("/run-agent")
async def run_agent(request: PromptRequest):
    try:
        # Extract the prompt from the request body
        input = {"prompt":request.prompt, "id": str(uuid4())}
        
        # Run the graph with tracing using the provided prompt
        result = run_graph_with_tracing(input)
        
        # Return the result as a JSON response
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}


class Env1Body(BaseModel):
    prompt: str


@app.post("/env1-then-env2-a2a")
async def env1_then_env2_a2a(
    body: Env1Body,
    nodes: int = Query(3, description="Number of parallel nodes (3, 5, or 10)"),
    users: int = Query(1, description="Number of concurrent users (for logging)")
):
    """
    Run orchestrated Env1 workflow with A2A communication to Env2.
    
    This endpoint uses an LLM-powered orchestrator that:
    - Dynamically discovers all AgentCards (SQL, Insight, Plot)
    - Decides which agents to invoke based on the user prompt and workflow state
    - Routes execution: SQL (local) - Insight (local) - Plot (A2A to Env2)
    
    A2A Communication Flow:
    1. Orchestrator discovers AgentCard for PlotAgent via /.well-known/agent-card.json
    2. Orchestrator sends A2A message to PlotAgent requesting visualization
    3. PlotAgent (in Env2) receives A2A message, creates chart, responds
    4. Response includes A2A conversation metadata
    
    """
    try:
        # Validate nodes
        if nodes not in [1, 3, 5, 10]:
            nodes = 3
            print(f"[WARNING] Invalid nodes value, using default: 3")
        
        run_id = str(uuid4())
        input_state = {"id": run_id, "nodes": nodes, "users": users}
        result = run_env1_then_env2_a2a(body.prompt, input_state)
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}


@app.post("/env3-openai-agents")
async def env3_openai_agents(
    body: Env1Body,
    nodes: int = Query(3, description="Number of parallel nodes (1, 3, 5, or 10)"),
    users: int = Query(1, description="Number of concurrent users (for logging)")
):
    """
    Run Env3 with OpenAI Agents SDK - replicates Torrado's original LangGraph workflow.
    
    This endpoint uses OpenAI Agents SDK to implement the same workflow as Env1:
    - Orchestrator decides next tool using Torrado's original decide_tool prompt (hardcoded tool descriptions)
    - All agents (SQL, Insight, Plot) run in the same environment (no A2A)
    
    Tool Names (matching Torrado's original):
    - lookup_sales_data: Retrieve raw sales data (must be run first)
    - analyzing_data: Analyze sales data to extract trends and insights
    - create_visualization: Create chart/graph based on data and analysis
    - end: Conclude the process
    
    Configuration:
    - nodes: Number of parallel nodes for SQL and Insight agents (1, 3, 5, or 10)
    - users: Number of concurrent users (for result organization in evaluation CSVs)
    """
    try:
        # Validate nodes
        if nodes not in [1, 3, 5, 10]:
            nodes = 3
            print(f"[WARNING] Invalid nodes value, using default: 3")
        
        result = run_env3_openai_agents_with_tracking(body.prompt, nodes=nodes, users=users)
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# A2A Protocol Endpoints
# =============================================================================

@app.post("/register/{agent_slug}")
async def register_agent(agent_slug: str, request: Request):
    raw_body = await request.body()
    data = json.loads(raw_body)
    card = AgentCard.parse_obj(data)
    AGENT_CARDS[agent_slug] = card
    print(f"[Registry] {agent_slug} registered via HTTP ({len(raw_body)} bytes received)", flush=True)
    return {"status": "registered", "agent": agent_slug, "bytes_received": len(raw_body)}


@app.get("/.well-known/agent-card.json")
async def get_agent_card_endpoint(agent: str = Query(..., description="Agent ID (e.g., 'insight', 'plot')")):
    """
    AgentCard discovery endpoint.
    
    Returns the AgentCard for the specified agent, describing its capabilities,
    skills, and communication endpoints.
    
    Exemple: GET /.well-known/agent-card.json?agent=plot
    """
    agent_card = get_agent_card(agent)
    if agent_card is None:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent}' not found. Available agents: {list(AGENT_CARDS.keys())}"
        )
    return agent_card.dict()


@app.get("/agents/list")
async def list_agents():
    return {
        "agents": [
            {
                "id": agent_id,
                "name": card.name,
                "description": card.description,
                "version": card.version,
                "endpoints": card.endpoints.dict(),
                "skills": [skill.name for skill in card.capabilities.skills]
            }
            for agent_id, card in AGENT_CARDS.items()
        ]
    }


@app.post("/agent/insight/a2a")
async def insight_agent_a2a(message: A2AMessage):

   # A2A endpoint for InsightAgent.

    # InsightAgent doesn't typically receive A2A messages 
    #  included forcompleteness
    from a2a import A2AResponse, A2AError
    
    error = A2AError(
        code=-32601,
        message="InsightAgent does not accept incoming A2A requests. It only sends messages to other agents.",
        data={"agent_role": "sender_only"}
    )
    return A2AResponse(id=message.id, error=error).dict()


@app.post("/agent/plot/a2a")
async def plot_agent_a2a(message: A2AMessage):
    
# Allows InsightAgent (or other agents) to request visualizations via A2A protocol
    import asyncio
    from agents.plot_agent import PlotAgent
    from a2a import A2AAgentExecutor, PLOT_AGENT_CARD
    
    # Create PlotAgent executor if not cached
    if not hasattr(plot_agent_a2a, "_executor"):
        plot_agent = PlotAgent()
        plot_agent_a2a._executor = A2AAgentExecutor(plot_agent, PLOT_AGENT_CARD)
    
    # Execute message in thread pool 
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, plot_agent_a2a._executor.execute, message)
    return response.dict()


@app.get("/agent/insight/health")
async def insight_health():
    """Health check for InsightAgent"""
    return {"status": "healthy", "agent": "insight", "capabilities": ["analyze_sales_data"]}


@app.get("/agent/plot/health")
async def plot_health():
    """Health check for PlotAgent"""
    return {"status": "healthy", "agent": "plot", "capabilities": ["create_visualization"]}