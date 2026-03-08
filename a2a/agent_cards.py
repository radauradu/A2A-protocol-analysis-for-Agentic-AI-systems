

#capabilities and endpoints for each agent in the system.


import os
from typing import Optional
from .protocol import (
    AgentCard, 
    AgentCardSkill, 
    AgentCardCapabilities,
    AgentCardEndpoints,
    AgentCardAuthentication
)

# Base URL for endpoints 
BASE_URL = os.getenv("A2A_BASE_URL", "http://localhost:8000")
PLOT_SERVICE_URL = os.getenv("PLOT_SERVICE_URL", "http://localhost:8001")  # Env2 on separate port


# SQLAgent Card
SQL_AGENT_CARD = AgentCard(
    id="sql_agent_v1",
    name="Sales Data Query Agent",
    description="Generates and executes SQL queries against sales data using DuckDB. Converts natural language prompts into SQL, executes queries on local parquet files, and returns structured data with daily aggregates.",
    version="1.0.0",
    capabilities=AgentCardCapabilities(
        input_modes=["application/json"],
        output_modes=["application/json"],
        skills=[
            AgentCardSkill(
                name="query_sales_data",
                description="Generate SQL query from natural language and execute against sales database. Returns tabular data with rows, columns, SQL query used, and table metadata. Automatically extracts date ranges from prompts and enforces daily aggregation.",
                input_schema={
                    "prompt": "string"
                },
                output_schema={
                    "rows": "array<array>",
                    "columns": "array<string>",
                    "sql": "string",
                    "table_name": "string",
                    "notes": "string (optional)"
                }
            )
        ]
    ),
    endpoints=AgentCardEndpoints(
        a2a="local",  #  local execution only
        health="local",
        card="local"
    ),
    authentication=AgentCardAuthentication(type="none", required=False),
    metadata={
        "environment": "env1",
        "database": "duckdb",
        "llm_model": "llama3.2:3b",
        "data_source": "parquet"
    }
)


# InsightAgent Card
INSIGHT_AGENT_CARD = AgentCard(
    id="insight_agent_v1",
    name="Sales Insight Analyzer",
    description="Analyzes sales data and generates natural language insights about trends, patterns, and anomalies. Can identify revenue spikes, seasonal patterns, and provide chart configuration recommendations.",
    version="1.0.0",
    capabilities=AgentCardCapabilities(
        input_modes=["application/json"],
        output_modes=["application/json"],
        skills=[
            AgentCardSkill(
                name="analyze_sales_data",
                description="Analyzes tabular sales data (rows/columns) and generates insights. Returns natural language analysis and suggested chart configuration.",
                input_schema={
                    "rows": "array<array>",
                    "columns": "array<string>",
                    "prompt": "string"
                },
                output_schema={
                    "analysis": "string",
                    "chart_config": "object",
                    "data_preview": "array<object>",
                    "provenance": "object"
                }
            )
        ]
    ),
    endpoints=AgentCardEndpoints(
        a2a="local",  # Local execution in Env1
        health="local",
        card="local"
    ),
    authentication=AgentCardAuthentication(type="none", required=False),
    metadata={
        "environment": "env1",
        "llm_model": "llama3.2:3b",
        "max_data_preview": 20
    }
)


# PlotAgent Card
PLOT_AGENT_CARD = AgentCard(
    id="plot_agent_v1",
    name="Sales Visualization Agent",
    description="Creates visualizations from sales data. Supports line charts, bar charts, and custom configurations. Generates PNG images and saves data/config artifacts.",
    version="1.0.0",
    capabilities=AgentCardCapabilities(
        input_modes=["application/json"],
        output_modes=["application/json", "image/png"],
        skills=[
            AgentCardSkill(
                name="create_visualization",
                description="Creates a chart/visualization from tabular data. Accepts data (rows/columns), chart configuration (x_axis, y_axis, chart_type, title), and optional context about the data. Returns paths to generated image and data files.",
                input_schema={
                    "data": "object",  # {rows: array, columns: array}
                    "chart_config": "object",  # {x_axis: string, y_axis: string, chart_type: string, title: string}
                    "context": "string (optional)",  
                    "preferences": "object (optional)"  
                },
                output_schema={
                    "image_path": "string",
                    "csv_path": "string",
                    "chart_config_path": "string",
                    "status": "string"
                }
            )
        ]
    ),
    endpoints=AgentCardEndpoints(
        a2a=f"{PLOT_SERVICE_URL}/agent/plot/a2a",
        health=f"{PLOT_SERVICE_URL}/health",
        card=f"{PLOT_SERVICE_URL}/.well-known/agent-card.json?agent=plot"
    ),
    authentication=AgentCardAuthentication(type="none", required=False),
    metadata={
        "environment": "env2",
        "framework": "openai_agents",
        "agent_class": "Agent",
        "runner_class": "Runner",
        "llm_backend": "ollama",
        "llm_model": "llama3.2:3b",
        "supported_chart_types": ["line", "bar"],
        "output_format": "png",
        "output_dpi": 150,
        "tools": ["create_visualization"]
    }
)


# Registry of all agent cards — starts empty.
# SQL and Insight are registered in-process at Env1 startup (no HTTP).
# Plot is registered via HTTP POST from Env2 at Env2 startup.
AGENT_CARDS = {}


def get_agent_card(agent_id: str) -> Optional[AgentCard]:
    """
    Get an agent card by agent ID.
    
    Args:
        agent_id: Agent identifier (e.g., "insight", "plot")
        
    Returns:
        AgentCard if found, None otherwise
    """
    return AGENT_CARDS.get(agent_id)


def list_agent_cards():
    #List all available agent cards
    return list(AGENT_CARDS.values())

