"""
Env2 Service - PlotAgent with OpenAI Agents Framework

This service uses OpenAI's Agents framework (openai-agents package) with local Ollama.

- Env1: LangGraph with state graphs and node routing
- Env2: OpenAI Agents with Agent/Runner and tool calling

"""

import sys
import os
import json
from datetime import datetime
from typing import Dict, Any
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from codecarbon import EmissionsTracker

# Configure OpenTelemetry for Phoenix tracing
# Use environment variable from docker-compose.yml 
if "PHOENIX_ENABLED" not in os.environ:
    os.environ["PHOENIX_ENABLED"] = "true"
os.environ["OTEL_SERVICE_NAME"] = os.getenv("OTEL_SERVICE_NAME", "torrado_env2_openai_agents")
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://phoenix:6006/v1/traces")

# env2 has its own manual OTel setup below
os.environ["SKIP_PHOENIX_REGISTRATION"] = "true"

# Use Phoenix's register() directly for consistent span format with env1
# This ensures spans are queryable using the same DSL
from phoenix.otel import register as phoenix_register
PHOENIX_PROJECT = os.getenv("PHOENIX_PROJECT_NAME", "evaluating-agent")
tracer_provider = phoenix_register(
    project_name=PHOENIX_PROJECT,
    endpoint=os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"],
)
tracer = trace.get_tracer(__name__)
print(f"[Env2] ✅ Phoenix registered: project={PHOENIX_PROJECT}, endpoint={os.environ['OTEL_EXPORTER_OTLP_ENDPOINT']}")

# Instrument requests and FastAPI
RequestsInstrumentor().instrument()

from fastapi import FastAPI
from a2a.protocol import A2AMessage, A2AResponse, A2AError
import asyncio

# Import OpenAI client
from openai import OpenAI

# Import PlotAgent FIRST, before any sys.path manipulation
# This ensures Python caches the local 'agents' module before I import openai-agents
from agents.plot_agent import PlotAgent
print("[Env2] ✅ Imported PlotAgent from local agents directory")

# Now import OpenAI Agents framework 
import sys
import os
import importlib

# Temporarily remove current directory from sys.path to avoid local 'agents' directory
original_sys_path = sys.path.copy()
sys.path = [p for p in sys.path if not p.startswith('/app') and p != '']

try:
    # Clear the 'agents' module from cache if it exists (it has PlotAgent)
    if 'agents' in sys.modules:
        local_agents = sys.modules.pop('agents')
    
    # Now import from the installed openai-agents package
    from agents import Agent, Runner
    print("[Env2] ✅ Imported Agent/Runner from openai-agents package (site-packages)")
    
    # Store references to Agent and Runner
    OpenAIAgent = Agent
    OpenAIRunner = Runner
finally:
    # Restore original sys.path and local agents module
    sys.path = original_sys_path
    if 'local_agents' in locals():
        sys.modules['agents'] = local_agents
        
# Use the stored references
Agent = OpenAIAgent
Runner = OpenAIRunner

# Initialize OpenAI client pointing to local Ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")

# Set global OpenAI configuration for agents
import openai
openai.api_key = "ollama"  # Dummy key for local Ollama
openai.api_base = OLLAMA_BASE_URL

# Also create explicit client instance
openai_client = OpenAI(
    base_url=OLLAMA_BASE_URL,
    api_key="ollama"  # Dummy key for local Ollama
)

app = FastAPI(
    title="Env2 - OpenAI Agents PlotAgent Service",
    description="Visualization service using OpenAI Agents framework with local Ollama for A2A protocol."
)

# Instrument FastAPI app
FastAPIInstrumentor.instrument_app(app)

import requests as _requests
import time as _time

REGISTRY_URL = os.getenv("A2A_BASE_URL", "http://localhost:8000")

@app.on_event("startup")
async def register_plot_agent():
    from a2a.agent_cards import PLOT_AGENT_CARD
    payload = json.dumps(PLOT_AGENT_CARD.dict()).encode("utf-8")
    bytes_sent = len(payload)
    for attempt in range(1, 6):
        try:
            resp = _requests.post(
                f"{REGISTRY_URL}/register/plot",
                data=payload,
                headers={"Content-Type": "application/json"},
                timeout=5
            )
            resp.raise_for_status()
            print(f"[Registry] plot registered via HTTP — bytes_sent={bytes_sent}, response={resp.json()}", flush=True)
            return
        except Exception as e:
            print(f"[Registry] attempt {attempt}/5 failed: {e}", flush=True)
            _time.sleep(2)
    print(f"[Registry] WARNING: plot registration failed after 5 attempts", flush=True)

print(f"[Env2 OpenAI Agents] Initializing PlotAgent with OpenAI Agents framework")
print(f"[Env2 OpenAI Agents] Using local Ollama at: {OLLAMA_BASE_URL}")

# Initialize LangChain LLM for chart config and code generation
from langchain_ollama import ChatOllama
_llm_for_viz = ChatOllama(
    model="llama3.2:3b",
    base_url="http://ollama:11434",  
    temperature=0.1
)

#
# Torrado's original prompts for create_visualization (2 LLM calls)

CHART_CONFIGURATION_PROMPT = """
Based on the provided data and goal, define a chart configuration using the format below:

Data:
{data}

Goal:
{visualization_goal}

Respond ONLY with the following format (no explanations, no markdown):

chart_type: <chart type>
x_axis: <x-axis column>
y_axis: <y-axis column>
title: <chart title>
"""

CREATE_CHART_PROMPT = """
Write python code to create a chart based on the following configuration.
Only return the code, no other text.
config: {config}
"""


def extract_chart_config_llm(data: Dict[str, Any], chart_config: Dict[str, Any], visualization_goal: str) -> Dict[str, Any]:
    """
    Torrado's extract_chart_config function, calls LLM to determine chart type, axes, title.
    """
    data_str = str(data.get("rows", []))[:2000]
    
    formatted_prompt = CHART_CONFIGURATION_PROMPT.format(
        data=data_str,
        visualization_goal=visualization_goal
    )
    
    print(f"[Env2] Calling LLM to determine chart configuration...")
    response = _llm_for_viz.invoke(formatted_prompt)
    
    try:
        raw = response.content.strip()
        print(f"[Env2] LLM chart config response:\n{raw}")
        
        config = {}
        for line in raw.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                config[key.strip().lower()] = value.strip()
        
        required_keys = {"chart_type", "x_axis", "y_axis", "title"}
        if not required_keys.issubset(config.keys()):
            print(f"[Env2] ⚠️ Missing keys, using provided config")
            config = chart_config.copy()
        else:
            config = {
                "chart_type": config.get("chart_type", chart_config.get("chart_type", "line")),
                "x_axis": config.get("x_axis", chart_config.get("x_axis", "x")),
                "y_axis": config.get("y_axis", chart_config.get("y_axis", "y")),
                "title": config.get("title", chart_config.get("title", "Chart")),
                "data": data.get("rows")
            }
        
        print(f"[Env2] ✅ Chart config: {config}")
        return config
        
    except Exception as e:
        print(f"[Env2] ⚠️ Error: {e}, using provided config")
        return chart_config


def create_chart_code_llm(chart_config: Dict[str, Any]) -> str:
    """
    Torrado's create_chart function, calls LLM to generate Python code.
    """
    try:
        formatted_prompt = CREATE_CHART_PROMPT.format(config=chart_config)
        
        print(f"[Env2] Calling LLM to generate chart code...")
        response = _llm_for_viz.invoke(formatted_prompt)
        code = response.content
        code = code.replace("```python", "").replace("```", "")
        print(f"[Env2] ✅ Generated code ({len(code)} chars)")
        return code
    except Exception as e:
        print(f"[Env2] Error: {e}")
        return f"# Error: {e}"


# Global variables to pass context to tool functions
_current_visualization_data = None
_current_chart_config = None
_current_run_id = type('obj', (object,), {'value': None})()  
_current_execution_id = type('obj', (object,), {'value': None})() 
_current_generated_code = None

# Define the tool function that the Agent will use
def create_visualization(data: Dict[str, Any], chart_config: Dict[str, Any], context: str = "") -> str:
    """
    Create visualization using Torrado's exact method (code-only):
    1. LLM call to extract_chart_config (determine chart type, axes, title)
    2. LLM call to create_chart_code (generate Python code)
    No PlotAgent.run() execution
    """
    print(f"[OpenAI Agent Tool] create_visualization called ")
    print(f"[OpenAI Agent Tool] Data: {len(data.get('rows', []))} rows")
    print(f"[OpenAI Agent Tool] Original chart type: {chart_config.get('chart_type')}")
    
    # Get run_id and execution_id from global variables set by A2A handler
    global _current_run_id, _current_execution_id, _current_generated_code
    run_id = _current_run_id.value if _current_run_id.value else f"agent_run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    execution_id = _current_execution_id.value
    
    print(f"[OpenAI Agent Tool] Using run_id: {run_id}, execution_id: {execution_id}")
    
   
    # TORRADO'S METHOD: 2 LLM calls only, no PlotAgent execution
   
    
    # LLM CALL #1: Extract chart configuration (chart type, axes, title)
    llm_chart_config = extract_chart_config_llm(
        data=data,
        chart_config=chart_config,
        visualization_goal=context or f"Create a {chart_config.get('chart_type', 'line')} chart"
    )
    
    # LLM CALL #2: Generate Python code for the chart
    viz_code = create_chart_code_llm(llm_chart_config)
    _current_generated_code = viz_code  # Store for A2A response
    
    result = {
        "generated_code": viz_code,
        "image_path": None,
        "csv_path": None,
        "chart_config_path": None,
    }
    
    # Create gen_visualization span so visualization_eval can find it in Phoenix
    if tracer is not None:
        try:
            with tracer.start_as_current_span("gen_visualization") as span:
                span.set_attribute("openinference.span.kind", "tool")
                if run_id:
                    span.set_attribute("agentrun_id", run_id)
                if execution_id:
                    span.set_attribute("viz.execution_id", execution_id)
                span.set_attribute("viz.chart_type", llm_chart_config.get('chart_type', 'line'))
                span.set_attribute("viz.row_count", len(data.get('rows', [])))
                span.set_status(StatusCode.OK)
                print(f"[OpenAI Agent Tool] ✅ Created gen_visualization span for evaluation")
        except Exception as e:
            print(f"[OpenAI Agent Tool] ⚠️ Span creation failed: {e}")
    
    print(f"[OpenAI Agent Tool] ✅ Visualization code generated (code-only, no file creation)")
    
    # Return as JSON string (Agents framework expects string returns)
    return json.dumps(result)


# Create the PlotAgent using OpenAI Agents framework
# The Agent class uses environment or global OpenAI client configuration
try:
    plot_agent = Agent(
        name="PlotAgent",
        instructions=(
            "You are a sales data visualization agent. Your job is to create charts and visualizations "
            "from sales data. When you receive data and chart configuration, use the create_visualization "
            "tool to generate the visualization. Always call the tool with the provided data and configuration."
        ),
        model="llama3.2:3b",
        functions=[create_visualization]
    )
    print(f"✅ [Env2 OpenAI Agents] PlotAgent initialized with create_visualization tool")
except TypeError as e:
    print(f"[Env2] Agent initialization failed: {e}")

    plot_agent = Agent(
        name="PlotAgent",
        instructions=(
            "You are a sales data visualization agent. Your job is to create charts and visualizations "
            "from sales data. When you receive data and chart configuration, use the create_visualization "
            "tool to generate the visualization. Always call the tool with the provided data and configuration."
        ),
        model="llama3.2:3b"
    )
    # Try setting functions attribute after initialization
    if hasattr(plot_agent, 'functions'):
        plot_agent.functions = [create_visualization]
    print(f"✅ [Env2 OpenAI Agents] PlotAgent initialized (fallback method)")

print(f"✅ [Env2 OpenAI Agents] PlotAgent initialized with create_visualization tool")


@app.post("/agent/plot/a2a")
async def plot_agent_a2a(message: A2AMessage):
    
    print(f"\n[Env2 OpenAI Agents] Received A2A message: {message.method}")
    print(f"[Env2 OpenAI Agents] Message ID: {message.id}")
    
    # Generate unique execution ID for this visualization
    from uuid import uuid4
    viz_execution_id = str(uuid4())[:8]
    
    with tracer.start_as_current_span("a2a_openai_agents_handler") as span:
        span.set_attribute("a2a.message_id", message.id)
        span.set_attribute("a2a.method", message.method)
        span.set_attribute("a2a.framework", "openai_agents")
        span.set_attribute("viz.execution_id", viz_execution_id)
        
        try:
            if message.method != "create_visualization":
                error = A2AError(
                    code=-32601,
                    message=f"Method not found: {message.method}"
                )
                return A2AResponse(
                    jsonrpc="2.0",
                    id=message.id,
                    error=error
                ).dict()
            
            # Extract parameters
            data = message.params.get("data", {})
            chart_config = message.params.get("chart_config", {})
            context = message.params.get("context", "")
            run_id = message.params.get("run_id", "unknown")
            
            print(f"[Env2 OpenAI Agents] Data: {len(data.get('rows', []))} rows, {len(data.get('columns', []))} columns")
            print(f"[Env2 OpenAI Agents] Chart type: {chart_config.get('chart_type', 'unknown')}")
            
            # Start CPU/GPU monitoring
            from usage_monitor import UsageMonitor
            import time as time_module
            from datetime import datetime
            usage_monitor = UsageMonitor()
            usage_monitor.start()
            execution_start_time = time_module.time()  # Track execution time
            execution_timestamp = datetime.utcnow().isoformat()  # Capture actual execution timestamp
            
            # Track energy for agent execution
            tracker = EmissionsTracker(
                project_name="openai_agent_run",
                experiment_id=viz_execution_id,  # Use viz_execution_id for emissions file naming
                measure_power_secs=1
            )
            tracker.start()
            
            # Use OpenAI Agents framework Runner to execute the agent
            with tracer.start_as_current_span("openai_agents_runner") as runner_span:
                runner_span.set_attribute("agent.name", "PlotAgent")
                runner_span.set_attribute("agent.model", "llama3.2:3b")
                runner_span.set_attribute("agent.backend", "ollama")
                
                # Build prompt for the agent
                agent_prompt = (
                    f"Create a visualization with the following specifications:\n"
                    f"- Chart type: {chart_config.get('chart_type', 'line')}\n"
                    f"- X-axis: {chart_config.get('x_axis', 'unknown')}\n"
                    f"- Y-axis: {chart_config.get('y_axis', 'unknown')}\n"
                    f"- Title: {chart_config.get('title', 'Chart')}\n"
                    f"- Data: {len(data.get('rows', []))} rows with columns: {', '.join(data.get('columns', []))}\n\n"
                    f"Context: {context[:200] if context else 'No context provided'}\n\n"
                    f"Use the create_visualization tool to generate the chart."
                )
                
                print(f"[Env2 OpenAI Agents] Running agent with Runner.run_sync()...")
                
                # Store data in a way the agent can access it
                # I'll pass it as part of the context that the tool can access
                global _current_visualization_data, _current_chart_config, _current_run_id, _current_execution_id
                _current_visualization_data = data
                _current_chart_config = chart_config
                _current_run_id.value = run_id  # From message.params
                _current_execution_id.value = viz_execution_id  # Generated earlier
                
                # Run the agent
                try:
                    result = Runner.run_sync(plot_agent, agent_prompt)
                    
                    runner_span.set_attribute("agent.response_received", True)
                    
                    # The agent's final_output contains the result
                    final_output = result.final_output if hasattr(result, 'final_output') else str(result)
                    
                    print(f"[Env2 OpenAI Agents] Agent execution completed")
                    print(f"[Env2 OpenAI Agents] Final output type: {type(final_output)}")
                    
                    # Parse the result 
                    if isinstance(final_output, str):
                        try:
                            visualization_result = json.loads(final_output)
                        except json.JSONDecodeError:
                            # If not JSON, the agent might have just described what it did
                            # Fall back to direct tool execution
                            print(f"[Env2 OpenAI Agents] Agent response not JSON, calling tool directly")
                            visualization_result = json.loads(create_visualization(data, chart_config, context))
                    else:
                        visualization_result = final_output
                    
                    runner_span.set_output({"visualization_created": True})
                    
                except Exception as e:
                    print(f"[Env2 OpenAI Agents] Agent execution failed: {e}")
                    print(f"[Env2 OpenAI Agents] Falling back to direct tool execution")
                    
                    # Fallback: directly call the tool
                    visualization_result = json.loads(create_visualization(data, chart_config, context))
            
            emissions = tracker.stop()
            execution_time = time_module.time() - execution_start_time  # Calculate execution time
            
            # Read energy breakdown from CodeCarbon's emissions CSV file
            # This matches Torrado/env3 approach: read from the CSV that CodeCarbon writes
            # instead of using internal tracker attributes (which can have unit mismatches)
            cpu_energy = None
            gpu_energy = None
            ram_energy = None
            emissions_rate = None
            total_energy = None
            emissions_duration = None
            emissions_timestamp = None
            try:
                import glob as glob_module
                # CodeCarbon writes emissions CSV
                emissions_pattern = f"emissions_{viz_execution_id}*.csv"
                # Also check default emissions.csv
                possible_files = glob_module.glob(f"**/emissions*.csv", recursive=True)
                # Filter for execution ID
                matching = [f for f in possible_files if viz_execution_id in f]
                if not matching:
                    # look for the default emissions.csv
                    matching = [f for f in possible_files if 'emissions.csv' in f]
                if matching:
                    import pandas as pd
                    emissions_csv = sorted(matching, key=lambda x: os.path.getmtime(x), reverse=True)[0]
                    row = pd.read_csv(emissions_csv).iloc[-1]  # Last row
                    cpu_energy = row.get("cpu_energy")
                    gpu_energy = row.get("gpu_energy")
                    ram_energy = row.get("ram_energy")
                    emissions_rate = row.get("emissions_rate")
                    total_energy = row.get("energy_consumed")
                    emissions_duration = row.get("duration")
                    emissions_timestamp = row.get("timestamp")
                    print(f"[Env2] Read energy from emissions CSV: {emissions_csv}")
                else:
                    print(f"[Env2] ⚠️ No emissions CSV found, using tracker attributes as fallback")
                    cpu_energy = tracker._total_cpu_energy.kWh if hasattr(tracker, '_total_cpu_energy') and tracker._total_cpu_energy else None
                    gpu_energy = tracker._total_gpu_energy.kWh if hasattr(tracker, '_total_gpu_energy') and tracker._total_gpu_energy else None
                    ram_energy = tracker._total_ram_energy.kWh if hasattr(tracker, '_total_ram_energy') and tracker._total_ram_energy else None
                    emissions_rate = getattr(tracker, 'final_emissions', None) or getattr(tracker, '_emissions', None)
                    total_energy = emissions
            except Exception as e:
                print(f"[Env2] ⚠️ Error reading emissions CSV: {e}, using tracker attributes")
                cpu_energy = tracker._total_cpu_energy.kWh if hasattr(tracker, '_total_cpu_energy') and tracker._total_cpu_energy else None
                gpu_energy = tracker._total_gpu_energy.kWh if hasattr(tracker, '_total_gpu_energy') and tracker._total_gpu_energy else None
                ram_energy = tracker._total_ram_energy.kWh if hasattr(tracker, '_total_ram_energy') and tracker._total_ram_energy else None
                emissions_rate = getattr(tracker, 'final_emissions', None) or getattr(tracker, '_emissions', None)
                total_energy = emissions
            
            # Use total_energy from CSV if available 
            if total_energy is not None:
                emissions = total_energy
            
            print(f"[Env2] DEBUG: cpu_energy={cpu_energy}, gpu_energy={gpu_energy}, ram_energy={ram_energy}, emissions_rate={emissions_rate}, total_energy={emissions}")
            
            # Stop CPU/GPU monitoring and get stats
            usage_monitor.stop()
            cpu_util = usage_monitor.cpu_mean
            gpu_util = usage_monitor.gpu_mean
            
            # Add energy tracking and execution metadata to result
            if isinstance(visualization_result, dict):
                print(f"[Env2] DEBUG: visualization_result keys before adding metadata: {list(visualization_result.keys())}")
                visualization_result["energy_create_visualization"] = emissions
                visualization_result["viz_execution_id"] = viz_execution_id
                visualization_result["cpu_utilization_create_visualization"] = cpu_util
                visualization_result["gpu_utilization_create_visualization"] = gpu_util
                visualization_result["execution_time_create_visualization"] = execution_time
                visualization_result["timestamp_create_visualization"] = execution_timestamp  # Actual execution timestamp
                # Add detailed energy breakdown
                visualization_result["cpu_energy_create_visualization"] = cpu_energy
                visualization_result["gpu_energy_create_visualization"] = gpu_energy
                visualization_result["ram_energy_create_visualization"] = ram_energy
                visualization_result["emissions_rate_create_visualization"] = emissions_rate
                print(f"[Env2] DEBUG: visualization_result keys after adding metadata: {list(visualization_result.keys())}")
                print(f"[Env2] DEBUG: timestamp_create_visualization = {visualization_result.get('timestamp_create_visualization')}")
            else:
                print(f"[Env2] ⚠️  visualization_result is not a dict! Type: {type(visualization_result)}")
            
            span.set_attribute("a2a.visualization_created", True)
            span.set_attribute("a2a.energy_kwh", emissions)
            span.set_attribute("a2a.viz_execution_id", viz_execution_id)
            span.set_attribute("a2a.cpu_util", cpu_util)
            span.set_attribute("a2a.gpu_util", gpu_util)
            
            print(f"[Env2 OpenAI Agents] Visualization execution ID: {viz_execution_id}")
            print(f"[Env2 OpenAI Agents] Energy: {emissions:.6f} kWh, CPU: {cpu_util}%, GPU: {gpu_util}%")
            
            # Return success response
            a2a_response = A2AResponse(
                jsonrpc="2.0",
                id=message.id,
                result=visualization_result
            )
            
            print(f"[Env2 OpenAI Agents] ✅ A2A response sent with visualization")
            response_dict = a2a_response.dict()
            if isinstance(response_dict.get('result'), dict):
                print(f"[Env2] DEBUG: result keys: {list(response_dict.get('result').keys())}")
                print(f"[Env2] DEBUG: timestamp_create_visualization in result: {response_dict.get('result').get('timestamp_create_visualization')}")
            return response_dict
                    
        except Exception as e:
            print(f"[Env2 OpenAI Agents] ❌ Error processing A2A message: {e}")
            import traceback
            traceback.print_exc()
            
            # Cleanup on error
            try:
                if 'usage_monitor' in locals():
                    usage_monitor.stop()
                if 'tracker' in locals():
                    tracker.stop()
            except:
                pass
            
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            
            error = A2AError(
                code=-32603,
                message=f"Internal error: {str(e)}"
            )
            return A2AResponse(
                jsonrpc="2.0",
                id=message.id,
                error=error
            ).dict()


@app.get("/.well-known/agent-card.json")
async def get_plot_card(agent: str = "plot"):
    #Return PlotAgent's AgentCard
    from a2a.agent_cards import PLOT_AGENT_CARD
    return PLOT_AGENT_CARD.dict()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "env2_openai_agents_plotagent",
        "framework": "openai_agents",
        "agent_class": "Agent",
        "runner_class": "Runner",
        "llm_backend": "ollama",
        "model": "llama3.2:3b"
    }


if __name__ == "__main__":
    import uvicorn
    print(f"Starting Env2 PlotAgent service (OpenAI Agents framework) on port 8001")
    print(f" Using local Ollama at: {OLLAMA_BASE_URL}")
    print(f" Traces will be sent to Phoenix at: {os.environ['OTEL_EXPORTER_OTLP_ENDPOINT']}")
    uvicorn.run(app, host="0.0.0.0", port=8001)
