"""
Environment 1 with Orchestrator and A2A Communication

This graph uses an LLM-powered orchestrator that dynamically discovers AgentCards
and decides which agents to invoke (SQL/Insight locally, PlotAgent via A2A to Env2).
"""

import os
import json
from uuid import uuid4
from typing import TypedDict, Dict, Any, NotRequired, List
from datetime import datetime
from functools import partial

from langgraph.graph import StateGraph, END
from codecarbon import EmissionsTracker
from langchain_core.messages import HumanMessage, SystemMessage

from agents.sql_agent import SQLAgent
from agents.insight_agent import InsightAgent

try:
    from usage_monitor import UsageMonitor
except ImportError:
    UsageMonitor = None

try:
    from utils_copy import tracer, llm
    from opentelemetry.trace import StatusCode
except Exception:
    tracer = None
    llm = None
    StatusCode = None

# Import LLM if not available from utils_copy (use same approach as env3)
if llm is None:
    from langchain_ollama import ChatOllama
    _base = os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_API_BASE") or "http://ollama:11434"
    _model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    llm = ChatOllama(model=_model, base_url=_base, temperature=0.1, streaming=True)


class Env1OrchestratedState(TypedDict):
    prompt: str
    id: str
    sql: NotRequired[str]
    rows: NotRequired[List[List]]
    columns: NotRequired[List[str]]
    analysis: NotRequired[str]
    chart_config: NotRequired[Dict]
    table_name: NotRequired[str]
    energy_lookup_sales_data: NotRequired[float]
    energy_analyzing_data: NotRequired[float]
    energy_orchestrator: NotRequired[List[float]]
    energy_a2a_message_sending: NotRequired[float]
    used_tools: NotRequired[List[str]]
    answer: NotRequired[List[str]]
    next_action: NotRequired[str]
    a2a_visualization: NotRequired[Dict]
    # Execution IDs for matching emissions files
    sql_execution_id: NotRequired[str]
    insight_execution_id: NotRequired[str]
    orchestrator_execution_ids: NotRequired[List[str]]
    # CPU/GPU utilization metrics
    cpu_utilization_sql: NotRequired[float]
    gpu_utilization_sql: NotRequired[float]
    cpu_utilization_insight: NotRequired[float]
    gpu_utilization_insight: NotRequired[float]
    cpu_utilization_orchestrator: NotRequired[List[float]]
    gpu_utilization_orchestrator: NotRequired[List[float]]


def _runs_dir() -> str:
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    root = os.path.join('.', 'runs', ts)
    os.makedirs(root, exist_ok=True)
    return root


# Agents will be created dynamically based on request parameters
# Default initialization for backward compatibility
sql_agent = None
insight_agent = None

def _create_agents(num_nodes: int = 3):
    """Create SQL and Insight agents with specified number of parallel nodes."""
    global sql_agent, insight_agent
    if num_nodes not in [1, 3, 5, 10]:
        print(f"[WARNING] Invalid num_nodes={num_nodes}, using default: 3")
        num_nodes = 3
    print(f"[Config] Creating agents with {num_nodes} parallel nodes")
    sql_agent = SQLAgent(num_parallel_nodes=num_nodes)
    insight_agent = InsightAgent(enable_a2a=False, use_parallel_analysis=True, num_parallel_nodes=num_nodes)
    return sql_agent, insight_agent

# Initialize with default for backward compatibility
_create_agents(3)


def orchestrator_decide(state: Dict[str, Any], llm_instance) -> Dict[str, Any]:
    """
    Orchestrator decide_tool: Single LLM call per invocation.
    """
    import difflib
    from pathlib import Path
    
    # Track orchestrator energy and utilization
    if "energy_orchestrator" not in state:
        state["energy_orchestrator"] = []
    if "orchestrator_execution_ids" not in state:
        state["orchestrator_execution_ids"] = []
    if "cpu_utilization_orchestrator" not in state:
        state["cpu_utilization_orchestrator"] = []
    if "gpu_utilization_orchestrator" not in state:
        state["gpu_utilization_orchestrator"] = []
    
    nodes = state.get("nodes", 3)
    
    # Generate unique execution ID for this decision
    decision_exec_id = str(uuid4())[:8]
    

    usage_monitor = UsageMonitor(interval=0.5) if UsageMonitor else None
 
    
    # Create output directory
    output_dir = f"3Hour_Radu/{nodes}node"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    tracker = EmissionsTracker(
        project_name="decide_tool",
        experiment_id=state.get("id", "unknown"),
        measure_power_secs=1,
        log_level="critical",
        output_file=f"emissions_{state.get('id', 'unknown')}_{decision_exec_id}.csv",
        output_dir=output_dir
    )
    tracker.start()
    
    used_tools = state.get("used_tools", [])
    has_data = bool(state.get("data") or state.get("rows"))
    has_analysis = bool(state.get("analysis") or state.get("analyze_data"))
    
    print(f"\n{'='*80}")
    print(f"[Orchestrator] DECISION CONTEXT (single LLM call, matching Torrado)")
    print(f"{'='*80}")
    print(f"  - Full prompt: {state['prompt']}")
    print(f"  - used_tools: {used_tools}")
    print(f"  - has_data: {has_data}")
    print(f"  - has_analysis: {has_analysis}")
    print(f"{'='*80}\n")
    
    # Discover agent cards for A2A-aware tool descriptions
    from a2a.agent_cards import AGENT_CARDS
    
    # Build tools description from AgentCards (A2A-specific: tool names come from agent cards)
    tools_list = []
    
    sql_card = AGENT_CARDS.get("sql")
    if sql_card:
        sql_skill = sql_card.capabilities.skills[0] if sql_card.capabilities.skills else None
        sql_desc = f"{sql_card.description}"
        if sql_skill:
            sql_desc += f" {sql_skill.description}"
        tools_list.append(f"    - {sql_card.id}: {sql_desc} (Must be run first)")
    else:
        tools_list.append("    - sql_agent_v1: Retrieve raw sales data. (Must be run first)")
    
    insight_card = AGENT_CARDS.get("insight")
    if insight_card:
        insight_skill = insight_card.capabilities.skills[0] if insight_card.capabilities.skills else None
        insight_desc = f"{insight_card.description}"
        if insight_skill:
            insight_desc += f" {insight_skill.description}"
        tools_list.append(f"    - {insight_card.id}: {insight_desc} (Run only after sql_agent_v1)")
    else:
        tools_list.append("    - insight_agent_v1: Analyze the sales data to extract trends and insights. (Run only after sql_agent_v1)")
    
    plot_card = AGENT_CARDS.get("plot")
    if plot_card:
        plot_skill = plot_card.capabilities.skills[0] if plot_card.capabilities.skills else None
        plot_desc = f"{plot_card.description}"
        if plot_skill:
            plot_desc += f" {plot_skill.description}"
        tools_list.append(f"    - {plot_card.id}: {plot_desc} (Run only after insight_agent_v1)")
    else:
        tools_list.append("    - plot_agent_v1: Create a chart or graph based on the data and its analysis. (Run only after insight_agent_v1)")
    
    tools_list.append("    - end: Conclude the process if the user's request is fully satisfied.")
    tools_description = "You have access to the following tools:\n" + "\n".join(tools_list)

    # Torrado's exact prompt format 
    decision_prompt = f"""
    Current user request: {state['prompt']}
    Current state details:
    - Answer so far: {state.get('answer', [])}
    - Tools already used: {state.get('used_tools', [])}
    - Data available: {"yes" if state.get("data") or state.get("rows") else "no"}

    You are a decision-making agent whose job is to determine the next step, choosing from these tools: {tools_description}. In a fixed workflow to fully answer a user's request. The workflow for a typical sales query that requires a full answer is strictly ordered as follows:

    1. sql_agent_v1: Retrieve the raw sales data from a Parquet file using an SQL query. This step must be performed first.
    2. insight_agent_v1: Analyze the retrieved sales data to extract patterns, trends, insights, or summaries. This step must be performed after the data has been retrieved.
    3. plot_agent_v1: Create a chart, graph, or visual representation based on the sales data and its analysis. This step must be performed after the analysis is done.
    4. end: Conclude the process when the user's request is completely satisfied and no further action is needed.
    
    Based on the current state and the user prompt, decide which tool to use next. Choose just between the tools. In this case, please just minimize the answer to the name of the tool you choose. 
    Besides this, do not use any tool that is already in :{used_tools}.

    To provide you a better understanding for this, the functions should have a number of hierarchy and order. So, sql_agent_v1 [1], insight_agent_v1 [2], plot_agent_v1 [3], end [4]. More specifically, this hierarchy needs to be respected [1] should never appear after [2], [3] or [4], neither should [1] appear after [1] was used at least once before, a flow [1], [2] ... [1], or [1], [2], [2] should never happen for example. [2] should never appear after [3] or [4]. [3] should never appear after [4]. And the only one that can be used at any time is "end" or [4], also know that's better to end than to have a repeated tool. 

    A more visual representation of the workflow is as follows:
    Examples of a flow: sql_agent_v1 -> insight_agent_v1 -> plot_agent_v1 -> end
    Examples of a flow: sql_agent_v1 -> insight_agent_v1 -> end
    Examples of a flow: sql_agent_v1 -> plot_agent_v1 -> end
    Examples of a flow: sql_agent_v1 -> end


    WHAT NOT TO DO? 
    What is NOT an example of a flow: insight_agent_v1 -> plot_agent_v1 -> end
    What is NOT an example of a flow: plot_agent_v1 -> end
    What is NOT an example of a flow: end -> end
    What is NOT an example of a flow: end -> plot_agent_v1 or sql_agent_v1 or insight_agent_v1
    What is NOT an example of a flow: sql_agent_v1 -> sql_agent_v1 or insight_agent_v1 or plot_agent_v1
    What is NOT an example of a flow: sql_agent_v1 -> insight_agent_v1 -> sql_agent_v1 ....
    ---
    Guidelines:
    - If there is no data available, you must choose "sql_agent_v1".
    - If data is available but no analysis has been performed yet, and the user's request includes terms like "trend", "insight", "analysis", or "summary", then choose "insight_agent_v1".
    - If both data and analysis are available and the request explicitly asks for a visualization (e.g., "create a chart", "plot the data", "visualize"), then choose "plot_agent_v1".
    - Only choose "end" if the complete workflow has been executed in order.
    - DO NOT select any tool out of this fixed order.

    Answer:
    """
    
    # Single LLM call 
    if tracer is not None:
        with tracer.start_as_current_span(
            "tool_choice",
            openinference_span_kind="tool"
        ) as span:
            span.set_attributes({
                "prompt": state["prompt"],
                "agentrun_id": state.get("id"),
                "valid_tools": json.dumps(["sql_agent_v1", "insight_agent_v1", "plot_agent_v1", "end"]),
                "used_tools": json.dumps(state.get("used_tools", [])),
            })
            span.set_input(state["prompt"])
            response = llm_instance.invoke(decision_prompt)
            tool_choice = response.content.strip().lower()
            span.set_output(tool_choice)
            if StatusCode:
                span.set_status(StatusCode.OK)
    else:
        response = llm_instance.invoke(decision_prompt)
        tool_choice = response.content.strip().lower()
    
    print(f"[Orchestrator] LLM response: {tool_choice}")
    
    # Fuzzy matching 
    valid_tools = ["sql_agent_v1", "insight_agent_v1", "plot_agent_v1", "end"]
    matched_tool = difflib.get_close_matches(tool_choice, valid_tools, n=1, cutoff=0.6)
    matched_tool = matched_tool[0] if matched_tool else "end"
    
    # duplicate prevention (line 739-741)
    if matched_tool in used_tools:
        print(f"[Orchestrator] ⚠️ Tool {matched_tool} already used. Forcing 'end' to prevent duplicate.")
        matched_tool = "end"
    
    # Stop tracker and monitor 
    emissions = tracker.stop()
    if usage_monitor:
        usage_monitor.stop()  
        cpu_util = usage_monitor.cpu_mean
        gpu_util = usage_monitor.gpu_mean
    else:
        cpu_util = None
        gpu_util = None
    
    # Append to state lists
    state["orchestrator_execution_ids"].append(decision_exec_id)
    state["energy_orchestrator"].append(emissions)
    state["cpu_utilization_orchestrator"].append(cpu_util)
    state["gpu_utilization_orchestrator"].append(gpu_util)
    
    # Queue single evaluation immediately 
    try:
        from prueba import decide_tool_eval
        from evaluation_logger import queue_evaluation as _queue_eval
        _queue_eval(
            tool_name="decide_tool",
            eval_func=decide_tool_eval,
            run_id=state.get("id"),
            energy=emissions,
            tool_execution_ids=decision_exec_id,
            cpu_utilization=cpu_util,
            gpu_utilization=gpu_util,
            nodes=nodes,
            users=state.get("users")
        )
    except Exception as e:
        print(f"[Orchestrator] ⚠️ Could not queue decide_tool evaluation: {e}")
    
    # Map agent_id to node name
    if matched_tool == "sql_agent_v1":
        next_action = "sql_agent"
    elif matched_tool == "insight_agent_v1":
        next_action = "insight_agent"
    elif matched_tool == "plot_agent_v1":
        next_action = "plot_agent_a2a"
    else:
        next_action = "end"
    
    # Update used_tools in state
    current_used_tools = state.get("used_tools", [])
    if matched_tool not in current_used_tools:
        state["used_tools"] = current_used_tools + [matched_tool]
    
    print(f"[Orchestrator] Decision: {matched_tool} → {next_action}")
    print(f"[Orchestrator] used_tools: {state['used_tools']}")
    
    return {
        **state,
        "next_action": next_action,
        "energy_orchestrator": state["energy_orchestrator"]
    }


def node_sql_local(state: Dict[str, Any]) -> Dict[str, Any]:
    """Execute SQL agent locally in Env1"""
    print(f"[Orchestrator→SQL] Executing SQLAgent locally... Prompt: {state['prompt'][:80]}...")
    
    # Generate execution ID for SQL agent
    sql_execution_id = str(uuid4())[:8]
    
    print("LLM response: lookup_sales_data")
    print(['lookup_sales_data'])
    
    # SQLAgent now handles its own CodeCarbon tracking
    res = sql_agent.run(
        state["prompt"],
        run_id=state.get("id"),
        execution_id=sql_execution_id
    )
    
    print(f"[SQL→Orchestrator] ✅ SQLAgent completed. Generated SQL with {len(res.get('rows', []))} rows")
    
    # Update used_tools list
    used_tools = state.get("used_tools", [])
    used_tools.append("sql_agent_v1")
    
    # Build data string from merged rows/columns (correct behavior,  this is where Torrado had a bug)
    rows = res.get("rows", [])
    columns = res.get("columns", [])
    if rows and columns:
        import pandas as pd
        df_for_prompt = pd.DataFrame(rows, columns=columns)
        data_string = df_for_prompt.to_string()
    else:
        data_string = ""
    
    # Handle parallel node metrics if available
    result = {
        **state,
        "sql": res.get("sql"),
        "rows": rows,
        "columns": columns,
        "data": data_string,  # Full merged result (correct behavior)
        "table_name": res.get("table_name"),
        "notes": res.get("notes"),
        "energy_lookup_sales_data": res.get("energy_consumed"),
        "sql_execution_id": sql_execution_id,
        "cpu_utilization_sql": res.get("cpu_utilization"),
        "gpu_utilization_sql": res.get("gpu_utilization"),
        "used_tools": used_tools
    }
    
    # Add parallel node metrics if SQL agent used parallel generation
    if res.get("num_parallel_nodes", 1) > 1:
        result["sql_execution_ids"] = res.get("sql_execution_ids", [])
        result["energy_lookup_sales_data"] = res.get("energy_lookup_sales_data", [])
        result["cpu_utilization_lookup_sales_data"] = res.get("cpu_utilization_lookup_sales_data", [])
        result["gpu_utilization_lookup_sales_data"] = res.get("gpu_utilization_lookup_sales_data", [])
        result["num_parallel_nodes"] = res.get("num_parallel_nodes")
    
    return result


def node_insight_local(state: Dict[str, Any]) -> Dict[str, Any]:
    """Execute Insight agent locally in Env1 (without A2A)"""
    print(f"[Orchestrator→Insight] Executing InsightAgent locally... Analyzing {len(state['rows'])} rows")
    
    # Generate execution ID for Insight agent
    insight_execution_id = str(uuid4())[:8]
    
    print("LLM response: analyzing_data")
    print(['analyzing_data'])
    
    # InsightAgent now handles its own CodeCarbon tracking
    res = insight_agent.run(
        state["rows"], 
        state["columns"], 
        state["prompt"],
        request_visualization=False,  # No A2A from Insight node
        run_id=state.get("id"),
        execution_id=insight_execution_id,
        data_string=state.get("data", "")  # Pass full df.to_string() 
    )
    
   
    prov = res.get("provenance", {})
    prov["sql_used"] = state.get("sql")
    res["provenance"] = prov
    
    print(f"[Insight→Orchestrator] ✅ InsightAgent completed with analysis and chart config")
    
    # Update used_tools list
    used_tools = state.get("used_tools", [])
    used_tools.append("insight_agent_v1")
    

    analysis_ids = res.get("analysis_execution_ids", [insight_execution_id])
    energy_list = res.get("energy_analyzing_data", [res.get("energy_consumed")])
    cpu_list = res.get("cpu_utilization_analyzing_data", [res.get("cpu_utilization")])
    gpu_list = res.get("gpu_utilization_analyzing_data", [res.get("gpu_utilization")])
    
    result = {
        **state,
        "analysis": res.get("analysis"),
        "chart_config": res.get("chart_config"),
        "data_preview": res.get("data_preview"),
        "provenance": res.get("provenance"),
        "energy_analyzing_data": energy_list,
        "insight_execution_id": insight_execution_id,
        "analysis_execution_ids": analysis_ids,
        "cpu_utilization_analyzing_data": cpu_list,
        "gpu_utilization_analyzing_data": gpu_list,
        "num_parallel_nodes": res.get("num_parallel_nodes", 1),
        "used_tools": used_tools
    }
    
    return result


def node_plot_via_a2a(state: Dict[str, Any]) -> Dict[str, Any]:
    """Execute PlotAgent via A2A with CodeCarbon tracking for A2A overhead"""
    print(f"[Orchestrator→PlotAgent] Calling PlotAgent via A2A...")
    
    # Track A2A message sending overhead
    tracker = EmissionsTracker(
        project_name="a2a_message_sending",
        experiment_id=state.get("id", "unknown"),
        measure_power_secs=1
    )
    tracker.start()
    
    if tracer is not None:
        with tracer.start_as_current_span(
            "orchestrator_a2a_to_plot",
            openinference_span_kind="tool"
        ) as span:
            span.set_attribute("a2a.from_agent", "orchestrator_v1")
            span.set_attribute("a2a.to_agent", "plot")
            span.set_attribute("a2a.method", "create_visualization")
            span.set_attribute("a2a.data_rows", len(state.get("rows", [])))
            
            # Use A2AClient to send message
            from a2a.client import A2AClient
            
            a2a_client = A2AClient()
            
            span.set_input({
                "data_rows": len(state.get("rows", [])),
                "columns": state.get("columns", []),
                "chart_config": state.get("chart_config", {}),
                "context_preview": state.get("analysis", "")[:200]
            })
            
            viz_response = a2a_client.send_message(
                to_agent="plot",
                method="create_visualization",
                params={
                    "data": {"rows": state.get("rows", []), "columns": state.get("columns", [])},
                    "chart_config": state.get("chart_config", {}),
                    "context": state.get("analysis", "")[:300],
                    "run_id": state.get("id", "unknown"),  # Pass run_id for tracking
                    "execute": False  # No plot execution
                },
                from_agent="orchestrator_v1"
            )
            span.set_output({
                "visualization_created": viz_response.get("image_path") is not None,
                "image_path": viz_response.get("image_path"),
                "a2a_execution_mode": viz_response.get("a2a_execution_mode")
            })
            span.set_status(StatusCode.OK)
    else:
        from a2a.client import A2AClient
        a2a_client = A2AClient()
        viz_response = a2a_client.send_message(
            to_agent="plot",
            method="create_visualization",
            params={
                "data": {"rows": state.get("rows", []), "columns": state.get("columns", [])},
                "chart_config": state.get("chart_config", {}),
                "context": state.get("analysis", "")[:300],
                "run_id": state.get("id", "unknown"),  # Pass run_id for tracking
                "execute": False  # No plot execution 
            },
            from_agent="orchestrator_v1"
        )
    
    # Stop tracking A2A overhead
    a2a_emissions = tracker.stop()
    
    print(f"[PlotAgent→Orchestrator] ✅ Received visualization from PlotAgent")
    print(f"[PlotAgent→Orchestrator] Image: {viz_response.get('image_path')}")
   
    used_tools = state.get("used_tools", [])
    used_tools.append("plot_agent_v1")
    
    return {
        **state,
        "a2a_visualization": viz_response,
        "used_tools": used_tools,
        "energy_a2a_message_sending": a2a_emissions
    }


def route_from_orchestrator(state: Dict[str, Any]) -> str:
    """Route based on orchestrator decision"""
    return state.get("next_action", "end")


# Build orchestrated graph with LLM-powered orchestrator
orchestrator_with_llm = partial(orchestrator_decide, llm_instance=llm)

graph_orchestrated = StateGraph(dict)
graph_orchestrated.add_node("orchestrator", orchestrator_with_llm)
graph_orchestrated.add_node("sql_agent", node_sql_local)
graph_orchestrated.add_node("insight_agent", node_insight_local)
graph_orchestrated.add_node("plot_agent_a2a", node_plot_via_a2a)

# Entry point is orchestrator
graph_orchestrated.set_entry_point("orchestrator")

# Conditional routing from orchestrator
graph_orchestrated.add_conditional_edges(
    "orchestrator",
    route_from_orchestrator,
    {
        "sql_agent": "sql_agent",
        "insight_agent": "insight_agent",
        "plot_agent_a2a": "plot_agent_a2a",
        "end": END
    }
)

# All agents loop back to orchestrator
graph_orchestrated.add_edge("sql_agent", "orchestrator")
graph_orchestrated.add_edge("insight_agent", "orchestrator")
graph_orchestrated.add_edge("plot_agent_a2a", "orchestrator")

compiled_orchestrated = graph_orchestrated.compile()


def run_env1_orchestrated(prompt: str, nodes: int = 3, users: int = 1) -> Dict[str, Any]:
    """
    Env1 with LLM-powered orchestrator + dynamic AgentCard discovery.
    
    The orchestrator discovers available agents, decides which to invoke,
    and routes between SQL (local), Insight (local), and Plot (A2A to Env2).
    
    Args:
        prompt: User prompt
        nodes: Number of parallel nodes (3, 5, or 10) - configures SQL and Insight agents
        users: Number of concurrent users (for result organization)
        
    Returns:
        Dict with SQL results, analysis, optional A2A visualization, and orchestrator energy
    """
    # Validate and create agents with specified node configuration
    if nodes not in [1, 3, 5, 10]:
        print(f"[WARNING] Invalid nodes={nodes}, using default: 3")
        nodes = 3
    _create_agents(nodes)
    
    run_id = str(uuid4())
    input_state = {
        "prompt": prompt,
        "id": run_id,
        "used_tools": [],
        "answer": [],
        "energy_orchestrator": [],
        "nodes": nodes,  # Store in state for evaluation logger
        "users": users   # Store in state for evaluation logger
    }
    
    print(f"[Orchestrator] Starting orchestrated workflow for: {prompt[:80]}...")
    print(f"[Orchestrator] Configuration: {nodes} nodes, {users} users")
    
    if tracer is not None:
        with tracer.start_as_current_span(
            "env1_orchestrated_run", 
            openinference_span_kind="agent"
        ) as span:
            span.set_input(input_state)
            span.set_attribute("agentrun_id", run_id)  # For evaluation queries
            span.set_attribute("orchestrator.enabled", True)
            span.set_attribute("orchestrator.run_id", run_id)
            span.set_attribute("num_parallel_nodes", nodes)  # Track node configuration
            span.set_attribute("num_users", users)  # Track user count
            out = compiled_orchestrated.invoke(input_state, config={"recursion_limit": 50})
            span.set_output(out)
            span.set_attribute("orchestrator.decisions_made", len(out.get("energy_orchestrator", [])))
            span.set_attribute("orchestrator.a2a_used", out.get("a2a_visualization") is not None)
            span.set_status(StatusCode.OK)
    else:
        out = compiled_orchestrated.invoke(input_state, config={"recursion_limit": 50})

    # Persist orchestrated output with metadata
    out_dir = _runs_dir()
    out_path = os.path.join(out_dir, 'env1_orchestrated_output.json')
    payload = {
    "prompt": prompt,
    "sql": out.get("sql"),
    "rows": out.get("rows", []),
    "columns": out.get("columns", []),
    "analysis": out.get("analysis"),
    "chart_config": out.get("chart_config", {}),
    "table_name": out.get("table_name", "sales"),
    "id": out.get("id", run_id),
    "energy_lookup_sales_data": out.get("energy_lookup_sales_data"),
    "energy_analyzing_data": out.get("energy_analyzing_data"),
    "energy_orchestrator": out.get("energy_orchestrator", []),
    "energy_a2a_message_sending": out.get("energy_a2a_message_sending"),
    "used_tools": out.get("used_tools", []),
    "answer": out.get("answer", []),
    "a2a_visualization": out.get("a2a_visualization", {}),
    "a2a_enabled": bool(out.get("a2a_visualization")),  
}
    
    with open(out_path, 'w') as f:
        json.dump(payload, f, default=str)
    
    payload["env1_orchestrated_output_path"] = out_path
    
    print(f"[Orchestrator] Workflow complete. Tools used: {out.get('used_tools', [])}")
    
    # Queue evaluations for background processing 

    try:
        from prueba import decide_tool_eval, sql_eval, analysis_eval, visualization_eval
        from evaluation_logger import queue_evaluation
        
        print(f"[Orchestrator] Queueing evaluations for run {run_id}...")
        
      
        
        # Queue SQL evaluation (handle both single and parallel nodes)
        if "sql_execution_id" in out or "sql_execution_ids" in out:
            # Use parallel IDs if available, otherwise single ID
            sql_ids = out.get("sql_execution_ids") or [out.get("sql_execution_id")]
            sql_energy = out.get("energy_lookup_sales_data")
            # Handle both list and scalar energy
            if not isinstance(sql_energy, list):
                sql_energy = [sql_energy] if sql_energy else []
            
            sql_cpu = out.get("cpu_utilization_lookup_sales_data") or out.get("cpu_utilization_sql")
            sql_gpu = out.get("gpu_utilization_lookup_sales_data") or out.get("gpu_utilization_sql")
            
            queue_evaluation(
                tool_name="lookup_sales_data",  # Match Torrado's naming
                eval_func=sql_eval,
                run_id=run_id,
                energy=sql_energy,
                tool_execution_ids=sql_ids,
                cpu_utilization=sql_cpu,
                gpu_utilization=sql_gpu,
                file_path=None,  # Will be determined by evaluation_logger based on nodes/users
                nodes=nodes,
                users=users
            )
            print(f"[Orchestrator]  Queued SQL evaluation ({len(sql_ids)} execution(s))")
        
        # Queue Insight evaluation (handle both single and parallel nodes)
        if "insight_execution_id" in out or "analysis_execution_ids" in out:
            # Use parallel IDs if available, otherwise single ID
            insight_ids = out.get("analysis_execution_ids") or [out.get("insight_execution_id")]
            insight_energy = out.get("energy_analyzing_data")
            # Handle both list and scalar energy
            if not isinstance(insight_energy, list):
                insight_energy = [insight_energy] if insight_energy else []
            
            insight_cpu = out.get("cpu_utilization_analyzing_data") or out.get("cpu_utilization_insight")
            insight_gpu = out.get("gpu_utilization_analyzing_data") or out.get("gpu_utilization_insight")
            
            queue_evaluation(
                tool_name="analyzing_data",  # Match Torrado's naming
                eval_func=analysis_eval,
                run_id=run_id,
                energy=insight_energy,
                tool_execution_ids=insight_ids,
                cpu_utilization=insight_cpu,
                gpu_utilization=insight_gpu,
                file_path=None,  # Will be determined by evaluation_logger based on nodes/users
                nodes=nodes,
                users=users
            )
            print(f"[Orchestrator]  Queued Insight evaluation ({len(insight_ids)} execution(s))")
        
        # Queue Visualization evaluation (if A2A visualization was executed)
        if "a2a_visualization" in out:
            viz_data = out.get("a2a_visualization", {})
            print(f"[Orchestrator] DEBUG: viz_data keys: {list(viz_data.keys()) if isinstance(viz_data, dict) else 'NOT A DICT'}")
            viz_execution_id = viz_data.get("viz_execution_id")
            viz_energy = viz_data.get("energy_create_visualization")
            viz_cpu = viz_data.get("cpu_utilization_create_visualization")
            viz_gpu = viz_data.get("gpu_utilization_create_visualization")
            viz_exec_time = viz_data.get("execution_time_create_visualization")
            # Extract detailed energy breakdown from A2A response
            viz_cpu_energy = viz_data.get("cpu_energy_create_visualization")
            viz_gpu_energy = viz_data.get("gpu_energy_create_visualization")
            viz_ram_energy = viz_data.get("ram_energy_create_visualization")
            viz_emissions_rate = viz_data.get("emissions_rate_create_visualization")
            # Extract timestamp, check multiple possible keys
            viz_timestamp = viz_data.get("timestamp_create_visualization") or viz_data.get("execution_timestamp_create_visualization")
            print(f"[Orchestrator] DEBUG: Checking for timestamp in viz_data...")
            print(f"[Orchestrator] DEBUG: viz_data keys: {list(viz_data.keys()) if isinstance(viz_data, dict) else 'NOT A DICT'}")
            print(f"[Orchestrator] DEBUG: timestamp_create_visualization = {viz_data.get('timestamp_create_visualization')}")
            print(f"[Orchestrator] DEBUG: execution_timestamp_create_visualization = {viz_data.get('execution_timestamp_create_visualization')}")
            print(f"[Orchestrator] DEBUG: Extracted viz_timestamp = {viz_timestamp}")
            
            # Fallback: if no timestamp from env2, use current time minus execution time
            if not viz_timestamp or str(viz_timestamp).strip() == '':
                print(f"[Orchestrator] ⚠️  No timestamp found in viz_data, using fallback")
                from datetime import datetime, timedelta
                if viz_exec_time:
                    # Estimate timestamp as current time minus execution time
                    viz_timestamp = (datetime.utcnow() - timedelta(seconds=viz_exec_time)).isoformat()
                else:
                    viz_timestamp = datetime.utcnow().isoformat()
                print(f"[Orchestrator] DEBUG: Fallback timestamp = {viz_timestamp}")
            else:
                print(f"[Orchestrator] ✅ Using timestamp from env2: {viz_timestamp}")
            
            print(f"[Orchestrator] DEBUG: viz_execution_id={viz_execution_id}, viz_energy={viz_energy}, viz_exec_time={viz_exec_time}")
            print(f"[Orchestrator] DEBUG: cpu_energy={viz_cpu_energy}, gpu_energy={viz_gpu_energy}, ram_energy={viz_ram_energy}, timestamp={viz_timestamp}")
            
            if viz_execution_id and viz_energy is not None:
                queue_evaluation(
                    tool_name="create_visualization",  # Match Torrado's naming
                    eval_func=visualization_eval,
                    run_id=run_id,
                    energy=viz_energy,
                    tool_execution_ids=viz_execution_id,
                    cpu_utilization=viz_cpu,
                    gpu_utilization=viz_gpu,
                    execution_time=viz_exec_time,
                    cpu_energy=viz_cpu_energy,
                    gpu_energy=viz_gpu_energy,
                    ram_energy=viz_ram_energy,
                    emissions_rate=viz_emissions_rate,
                    timestamp=viz_timestamp,  # Actual execution timestamp from env2 
                    file_path=None,  # Will be determined by evaluation_logger based on nodes/users
                    nodes=nodes,
                    users=users
                )
                print(f"[Orchestrator] ✓ Queued Visualization evaluation (execution: {viz_execution_id}, timestamp: {viz_timestamp})")
            else:
                print(f"[Orchestrator] ⚠️ Skipping Visualization evaluation (missing execution_id={viz_execution_id} or energy={viz_energy})")
            
            # Queue A2A Communication evaluation (separate from tool execution)
            # a2a_network_time_seconds is the full HTTP round-trip (send + env2 processing + receive)
            # I only want the pure network overhead, so I will subtract env2's processing time
            a2a_request_size = viz_data.get("a2a_request_size_bytes", 0)
            a2a_response_size = viz_data.get("a2a_response_size_bytes", 0)
            a2a_total_size = viz_data.get("a2a_total_size_bytes", 0)
            a2a_total_round_trip = viz_data.get("a2a_network_time_seconds", 0)
            a2a_conversation_id = viz_data.get("a2a_conversation_id", viz_data.get("a2a_message_id", "unknown"))
            
            # Calculate pure network overhead = total round-trip - env2 processing time
            a2a_network_overhead = a2a_total_round_trip - (viz_exec_time or 0)
            if a2a_network_overhead < 0:
                a2a_network_overhead = a2a_total_round_trip  # Fallback: use total if subtraction fails
            print(f"[Orchestrator] A2A timing: total_round_trip={a2a_total_round_trip:.3f}s, env2_processing={viz_exec_time:.3f}s, pure_network_overhead={a2a_network_overhead:.3f}s")
            
            # Calculate A2A timestamp: when A2A starts (env1 sends request to env2), to match other tools 
            # Env1 received at (viz_start + viz_exec_time); env1 sent = receive_time - a2a_network_time
            from datetime import datetime, timedelta
            if viz_timestamp:
                try:
                    viz_dt = datetime.fromisoformat(viz_timestamp.replace('Z', '+00:00') if 'Z' in viz_timestamp else viz_timestamp)
                    # Start of A2A = when env1 sent = (when env2 finished) - total round trip time
                    a2a_timestamp = (viz_dt + timedelta(seconds=(viz_exec_time or 0)) - timedelta(seconds=a2a_total_round_trip)).isoformat()
                except:
                    # Fallback: use current time minus network time
                    a2a_timestamp = (datetime.utcnow() - timedelta(seconds=a2a_total_round_trip)).isoformat()
            else:
                # Fallback: use current time minus network time
                a2a_timestamp = (datetime.utcnow() - timedelta(seconds=a2a_total_round_trip)).isoformat()
            
            if a2a_total_size > 0 or a2a_network_overhead > 0:
                from evaluations import a2a_communication_eval
                queue_evaluation(
                    tool_name="a2a_communication",
                    eval_func=a2a_communication_eval,
                    run_id=run_id,
                    energy=None,  # Not tracked: local machine idle during HTTP wait
                    tool_execution_ids=a2a_conversation_id,
                    cpu_utilization=None,  # Not tracked: local machine idle during HTTP wait
                    gpu_utilization=None,  # Not tracked: local machine idle during HTTP wait
                    execution_time=a2a_network_overhead if a2a_network_overhead > 0 else None,
                    cpu_energy=None,
                    gpu_energy=None,
                    ram_energy=None,
                    timestamp=a2a_timestamp,  # Timestamp for A2A communication (before visualization)
                    file_path=None,
                    nodes=nodes,
                    users=users,
                    a2a_request_size_bytes=a2a_request_size,
                    a2a_response_size_bytes=a2a_response_size,
                    a2a_total_size_bytes=a2a_total_size,
                )
                print(f"[Orchestrator]  Queued A2A Communication evaluation (size: {a2a_total_size}B, overhead: {a2a_network_overhead:.3f}s, timestamp: {a2a_timestamp})")
            else:
                print(f"[Orchestrator] ⚠️ Skipping A2A Communication evaluation (no A2A metrics found)")
        
        print(f"[Orchestrator] Evaluations queued. Background worker will process them asynchronously.")
        
    except Exception as e:
        print(f"[Orchestrator] ⚠️ Failed to queue evaluations: {e}")
    
    return payload


# Keep backward compatibility 
def run_env1_a2a(prompt: str, nodes: int = 3, users: int = 1) -> Dict[str, Any]:
    """Alias for run_env1_orchestrated with backward compatibility."""
    return run_env1_orchestrated(prompt, nodes=nodes, users=users)

