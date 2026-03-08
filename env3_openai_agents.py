"""
Environment 3: OpenAI Agents SDK Implementation

Replicates Torrado's original LangGraph workflow but using OpenAI Agents SDK.
.
"""

import os
import json
import difflib
from uuid import uuid4
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

import pandas as pd
from codecarbon import EmissionsTracker
from langchain_ollama import ChatOllama

# Import agents
from agents.sql_agent import SQLAgent
from agents.insight_agent import InsightAgent

# Import tracing and evaluation
try:
    from utils_copy import tracer, llm as default_llm
    from opentelemetry.trace import StatusCode
except Exception:
    tracer = None
    default_llm = None
    StatusCode = None

# Import UsageMonitor for CPU/GPU tracking
try:
    from usage_monitor import UsageMonitor
except ImportError:
    UsageMonitor = None

# Import evaluation functions
try:
    from prueba import decide_tool_eval, sql_eval, analysis_eval, visualization_eval
    from evaluation_logger import queue_evaluation
except Exception:
    decide_tool_eval = None
    sql_eval = None
    analysis_eval = None
    visualization_eval = None
    queue_evaluation = None

# Initialize LLM if not available
if default_llm is None:
    base = os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_API_BASE") or os.getenv("OLLAMA_BASE_URL", "").replace("/v1", "") or "http://host.docker.internal:11434"
    model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    default_llm = ChatOllama(model=model, base_url=base, temperature=0.1, streaming=True)


# Torrado's original prompts for create_visualization 


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


def extract_chart_config(state: Dict[str, Any], llm_instance) -> Dict[str, Any]:
    """
    Torrado's extract_chart_config function.
    Calls LLM to determine chart type, axes, and title.
    """
    data = state.get("data")
    if not data:
        print("[extract_chart_config] No data available for visualization")
        return {**state, "chart_config": None}
    
    # Torrado's default config
    default_cfg = {
        "chart_type": "line",
        "x_axis": "day",
        "y_axis": "revenue",
        "title": "Revenue by day - Nov 2021",
        "data": state.get("data"),  
    }
    
    # Get visualization goal 
    visualization_goal = state.get("visualization_goal") or state.get("prompt")
    
    # Torrado's approach: send FULL data to LLM 
    try:
        formatted_prompt = CHART_CONFIGURATION_PROMPT.format(
            data=data,  # Full data string 
            visualization_goal=visualization_goal,
        )
        
        print(f"[extract_chart_config] Calling LLM with full data string...")
        resp = llm_instance.invoke(formatted_prompt).content.strip()
        print(f"[extract_chart_config] LLM raw response:\n{resp}")
        
        # Try to parse JSON first
        try:
            cfg = json.loads(resp)
            for k in ("chart_type", "x_axis", "y_axis", "title"):
                if k not in cfg:
                    raise ValueError("missing keys")
            chart_config = cfg
        except (json.JSONDecodeError, ValueError):
            # Try key: value parsing as fallback 
            config = {}
            for line in resp.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    config[key.strip().lower()] = value.strip()
            
            required_keys = {"chart_type", "x_axis", "y_axis", "title"}
            if required_keys.issubset(config.keys()):
                chart_config = {
                    "chart_type": config["chart_type"],
                    "x_axis": config["x_axis"],
                    "y_axis": config["y_axis"],
                    "title": config["title"],
                    "data": state["data"], 
                }
            else:
                raise ValueError(f"Missing keys in config: {config.keys()}")
        
        # Ensure data is included in chart_config 
        if "data" not in chart_config:
            chart_config["data"] = state["data"]
        
        print(f"[extract_chart_config] Chart config generated (data included)")
        
    except Exception as e:
        print(f"[extract_chart_config] LLM parsing failed, using default: {e}")
        chart_config = default_cfg
    
    # Return state with chart_config 
    return {
        **state,
        "visualization_goal": visualization_goal,
        "chart_config": chart_config,
        "analyze_data": state.get("analyze_data"),
        "used_tools": state.get("used_tools", [])
    }


def create_chart_code(state: Dict[str, Any], llm_instance) -> str:
    """
    Torrado's create_chart function.
    Calls LLM to generate Python code for the chart.
    """
    try:
        chart_config = state.get("chart_config", {})
        formatted_prompt = CREATE_CHART_PROMPT.format(config=chart_config)
        
        print(f"[create_chart] Calling LLM to generate chart code...")
        response = llm_instance.invoke(formatted_prompt)
        code = response.content
        code = code.replace("```python", "").replace("```", "")
        print(f"[create_chart] ✅ Generated code ({len(code)} chars)")
        return code
    except Exception as e:
        print(f"[create_chart] Error creating chart: {e}")
        return f"# Error generating chart code: {e}"


def decide_tool(state: Dict[str, Any], llm_instance) -> str:
    """
    Torrado's decide_tool: Single LLM call per invocation (no parallelization).
    """
    # Track orchestrator energy (lists for sequential results)
    if "energy_decide_tool" not in state:
        state["energy_decide_tool"] = []
    if "decide_tool_execution_ids" not in state:
        state["decide_tool_execution_ids"] = []
    if "cpu_utilization_decide_tool" not in state:
        state["cpu_utilization_decide_tool"] = []
    if "gpu_utilization_decide_tool" not in state:
        state["gpu_utilization_decide_tool"] = []
    
    nodes = state.get("nodes", 3)
    
 
    usage_monitor = UsageMonitor(interval=0.5) if UsageMonitor else None
    # note: Intentionally NOT calling usage_monitor.start() to match Torrado's behavior
    
    decision_exec_id = str(uuid4())[:8]
    
    # Create output directory
    output_dir = f"3Hour_Radu_nonA2A/{nodes}node"
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
    print(f"[Orchestrator] DECISION CONTEXT (single LLM call)")
    print(f"{'='*80}")
    print(f"  - Full prompt: {state['prompt']}")
    print(f"  - used_tools: {used_tools}")
    print(f"  - has_data: {has_data}")
    print(f"  - has_analysis: {has_analysis}")
    print(f"{'='*80}\n")
    
    # Torrado's original hardcoded tool descriptions
    tools_description = """You have access to the following tools:
    - lookup_sales_data: Retrieve raw sales data. (Must be run first)
    - analyzing_data: Analyze the sales data to extract trends and insights. (Run only after lookup_sales_data)
    - create_visualization: Create a chart or graph based on the data and its analysis. (Run only after analyzing_data)
    - end: Conclude the process if the user's request is fully satisfied.
    """
    
    # Torrado's exact prompt format 
    decision_prompt = f"""
    Current user request: {state['prompt']}
    Current state details:
    - Answer so far: {state.get('answer', [])}
    - Tools already used: {state.get('used_tools', [])}
    - Data available: {"yes" if state.get("data") or state.get("rows") else "no"}

    You are a decision-making agent whose job is to determine the next step, choosing from these tools: {tools_description}. In a fixed workflow to fully answer a user's request. The workflow for a typical sales query that requires a full answer is strictly ordered as follows:

    1. lookup_sales_data: Retrieve the raw sales data from a Parquet file using an SQL query. This step must be performed first.
    2. analyzing_data: Analyze the retrieved sales data to extract patterns, trends, insights, or summaries. This step must be performed after the data has been retrieved.
    3. create_visualization: Create a chart, graph, or visual representation based on the sales data and its analysis. This step must be performed after the analysis is done.
    4. end: Conclude the process when the user's request is completely satisfied and no further action is needed.
    
    Based on the current state and the user prompt, decide which tool to use next. Choose just between the tools. In this case, please just minimize the answer to the name of the tool you choose. 
    Besides this, do not use any tool that is already in :{used_tools}.

    To provide you a better understanding for this, the functions should have a number of hierarchy and order. So, lookup_sales_data [1], analyzing_data [2], create_visualization [3], end [4]. More specifically, this hierarchy needs to be respected [1] should never appear after [2], [3] or [4], neither should [1] appear after [1] was used at least once before, a flow [1], [2] ... [1], or [1], [2], [2] should never happen for example. [2] should never appear after [3] or [4]. [3] should never appear after [4]. And the only one that can be used at any time is "end" or [4], also know that's better to end than to have a repeated tool. 

    A more visual representation of the workflow is as follows:
    Examples of a flow: lookup_sales_data -> analyzing_data -> create_visualization -> end
    Examples of a flow: lookup_sales_data -> analyzing_data -> end
    Examples of a flow: lookup_sales_data -> create_visualization -> end
    Examples of a flow: lookup_sales_data -> end


    WHAT NOT TO DO? 
    What is NOT an example of a flow: analyzing_data -> create_visualization -> end
    What is NOT an example of a flow: create_visualization -> end
    What is NOT an example of a flow: end -> end
    What is NOT an example of a flow: end -> create_visualization or lookup_sales_data or analyzing_data
    What is NOT an example of a flow: lookup_sales_data -> lookup_sales_data or analyzing_data or create_visualization
    What is NOT an example of a flow: lookup_sales_data -> analyzing_data -> lookup_sales_data ....
    ---
    Guidelines:
    - If there is no data available, you must choose "lookup_sales_data".
    - If data is available but no analysis has been performed yet, and the user's request includes terms like "trend", "insight", "analysis", or "summary", then choose "analyzing_data".
    - If both data and analysis are available and the request explicitly asks for a visualization (e.g., "create a chart", "plot the data", "visualize"), then choose "create_visualization".
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
                "agentrun_id": state["id"],
                "valid_tools": json.dumps(["lookup_sales_data", "analyzing_data", "create_visualization", "end"]),
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
    valid_tools = ["lookup_sales_data", "analyzing_data", "create_visualization", "end"]
    matched_tool = difflib.get_close_matches(tool_choice, valid_tools, n=1, cutoff=0.6)
    matched_tool = matched_tool[0] if matched_tool else "end"
    
    # Torrado's duplicate prevention
    if matched_tool in used_tools:
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
    state["decide_tool_execution_ids"].append(decision_exec_id)
    state["energy_decide_tool"].append(emissions)
    state["cpu_utilization_decide_tool"].append(cpu_util)
    state["gpu_utilization_decide_tool"].append(gpu_util)
    
    # Update used_tools in state
    current_used_tools = state.get("used_tools", [])
    if matched_tool not in current_used_tools:
        state["used_tools"] = current_used_tools + [matched_tool]
    
    print(f"[Orchestrator] Decision: {matched_tool}")
    print(f"[Orchestrator] used_tools: {state['used_tools']}")
    
    # Queue single evaluation
    if queue_evaluation and decide_tool_eval:
        queue_evaluation(
            tool_name="decide_tool",
            eval_func=decide_tool_eval,
            run_id=state.get("id"),
            energy=emissions,
            tool_execution_ids=decision_exec_id,
            cpu_utilization=cpu_util,
            gpu_utilization=gpu_util,
            nodes=state.get("nodes"),
            users=state.get("users")
        )
    
    return matched_tool


def lookup_sales_data(state: Dict[str, Any], nodes: int) -> Dict[str, Any]:
    #Execute SQL agent to retrieve sales data
    print(f"[Orchestrator→SQL] Executing lookup_sales_data with {nodes} nodes...")
    
    # Generate execution ID
    sql_execution_id = str(uuid4())[:8]
    
    # Create SQL agent with configurable nodes
    sql_agent = SQLAgent(num_parallel_nodes=nodes)
    
    # Start monitoring CPU/GPU
    usage_monitor = UsageMonitor(interval=0.5) if UsageMonitor else None
    if usage_monitor:
        usage_monitor.start()
    
    # Create output directory
    output_dir = f"3Hour_Radu_nonA2A/{nodes}node"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Track emissions
    tracker = EmissionsTracker(
        project_name="lookup_sales_data",
        experiment_id=state.get("id", "unknown"),
        measure_power_secs=1,
        log_level="critical",
        output_file=f"emissions_{state.get('id', 'unknown')}_{sql_execution_id}.csv",
        output_dir=output_dir
    )
    tracker.start()
    
    try:
        # Execute SQL agent
        res = sql_agent.run(
            state["prompt"],
            run_id=state.get("id"),
            execution_id=sql_execution_id
        )
        
        # Stop monitoring
        if usage_monitor:
            usage_monitor.stop()
            stats = usage_monitor.get_stats()
            cpu_util = stats["cpu_mean"]
            gpu_util = stats["gpu_mean"]
        else:
            cpu_util = None
            gpu_util = None
        
        emissions = tracker.stop()
        
        # Extract parallel execution IDs if available (for multi-node runs)
        sql_execution_ids = res.get("sql_execution_ids", [sql_execution_id])
        energy_list = res.get("energy_lookup_sales_data", [emissions])
        cpu_list = res.get("cpu_utilization_lookup_sales_data", [cpu_util])
        gpu_list = res.get("gpu_utilization_lookup_sales_data", [gpu_util])
        
        print(f"[Orchestrator→SQL] ℹ️  Parallel results: {len(sql_execution_ids)} execution IDs")
        
        # Convert rows/columns to formatted DataFrame string
        rows = res.get("rows", [])
        columns = res.get("columns", [])
        if rows and columns:
            df_for_prompt = pd.DataFrame(rows, columns=columns)
            data_string = df_for_prompt.to_string()
        else:
            data_string = ""
        
        # Update state 
        result = {
            **state,
            "sql": res.get("sql"),
            "rows": rows,
            "data": data_string,  # Full merged result 
            "columns": columns,
            "table_name": res.get("table_name"),
            "notes": res.get("notes"),
            "energy_lookup_sales_data": energy_list,
            "sql_execution_ids": sql_execution_ids,  
            "cpu_utilization_lookup_sales_data": cpu_list,
            "gpu_utilization_lookup_sales_data": gpu_list
        }
        
    
        if queue_evaluation and sql_eval:
            queue_evaluation(
                tool_name="lookup_sales_data",
                eval_func=sql_eval,
                run_id=state.get("id"),
                energy=energy_list, 
                tool_execution_ids=sql_execution_ids,  
                cpu_utilization=cpu_list,  
                gpu_utilization=gpu_list,  
                nodes=nodes,
                users=state.get("users")
            )
        
        print(f"[SQL→Orchestrator] ✅ lookup_sales_data completed. Generated SQL with {len(res.get('rows', []))} rows")
        return result
        
    except Exception as e:
        print(f"[SQL→Orchestrator] ❌ Error in lookup_sales_data: {e}")
        if usage_monitor:
            usage_monitor.stop()
        tracker.stop()
        return {**state, "error": f"lookup_sales_data failed: {e}"}


def analyzing_data(state: Dict[str, Any], nodes: int) -> Dict[str, Any]:
    #Execute Insight agent to analyze sales data
    print(f"[Orchestrator→Insight] Executing analyzing_data with {nodes} nodes... Analyzing {len(state.get('rows', []))} rows")
    
    # Generate execution ID
    insight_execution_id = str(uuid4())[:8]
    
    # Create Insight agent with configurable nodes
    insight_agent = InsightAgent(enable_a2a=False, use_parallel_analysis=True, num_parallel_nodes=nodes)
    
    # Start monitoring CPU/GPU
    usage_monitor = UsageMonitor(interval=0.5) if UsageMonitor else None
    if usage_monitor:
        usage_monitor.start()
    
    # Create output directory
    output_dir = f"3Hour_Radu_nonA2A/{nodes}node"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Track emissions
    tracker = EmissionsTracker(
        project_name="analyzing_data",
        experiment_id=state.get("id", "unknown"),
        measure_power_secs=1,
        log_level="critical",
        output_file=f"emissions_{state.get('id', 'unknown')}_{insight_execution_id}.csv",
        output_dir=output_dir
    )
    tracker.start()
    
    try:
        # Execute Insight agent 
        res = insight_agent.run(
            state.get("rows", []),
            state.get("columns", []),
            state["prompt"],
            request_visualization=False,
            run_id=state.get("id"),
            execution_id=insight_execution_id,
            data_string=state.get("data", "")  # Pass full df.to_string() for Torrado's prompt
        )
        
        # Stop monitoring
        if usage_monitor:
            usage_monitor.stop()
            stats = usage_monitor.get_stats()
            cpu_util = stats["cpu_mean"]
            gpu_util = stats["gpu_mean"]
        else:
            cpu_util = None
            gpu_util = None
        
        emissions = tracker.stop()
        
        # Extract parallel execution IDs if available (for 3-node runs)
        analysis_execution_ids = res.get("analysis_execution_ids", [insight_execution_id])
        energy_list = res.get("energy_analyzing_data", [emissions])
        cpu_list = res.get("cpu_utilization_analyzing_data", [cpu_util])
        gpu_list = res.get("gpu_utilization_analyzing_data", [gpu_util])
        
        print(f"[Orchestrator→Insight] ℹ️  Parallel results: {len(analysis_execution_ids)} execution IDs")
        
        # Update state 
        result = {
            **state,
            "analysis": res.get("analysis"),
            "analyze_data": res.get("analysis"),  # Also store as "analyze_data" for compatibility
            "chart_config": res.get("chart_config"),
            "data_preview": res.get("data_preview"),
            "provenance": res.get("provenance"),
            "energy_analyzing_data": energy_list,
            "insight_execution_ids": analysis_execution_ids,  # Store list of IDs
            "cpu_utilization_analyzing_data": cpu_list,
            "gpu_utilization_analyzing_data": gpu_list
        }
        

        if queue_evaluation and analysis_eval:
            queue_evaluation(
                tool_name="analyzing_data",
                eval_func=analysis_eval,
                run_id=state.get("id"),
                energy=energy_list,  
                tool_execution_ids=analysis_execution_ids,  
                cpu_utilization=cpu_list,  
                gpu_utilization=gpu_list,  
                nodes=nodes,
                users=state.get("users")
            )
        
        print(f"[Insight→Orchestrator] ✅ analyzing_data completed with analysis and chart config")
        return result
        
    except Exception as e:
        print(f"[Insight→Orchestrator] ❌ Error in analyzing_data: {e}")
        if usage_monitor:
            usage_monitor.stop()
        tracker.stop()
        return {**state, "error": f"analyzing_data failed: {e}"}


def create_visualization(state: Dict[str, Any], nodes: int) -> Dict[str, Any]:
    """
    1. LLM call to extract_chart_config (determine chart type, axes, title)
    2. LLM call to create_chart_code (generate Python code)
    No execution: we do NOT call PlotAgent.run() so no file is created 
    """
    print(f"[Orchestrator→Plot] Executing create_visualization with {nodes} nodes (code-only, no PlotAgent.run)...")
    
    # Generate execution ID
    viz_execution_id = str(uuid4())[:8]
    
    # Start monitoring CPU/GPU
    usage_monitor = UsageMonitor(interval=0.5) if UsageMonitor else None
    if usage_monitor:
        usage_monitor.start()
    
    # Create output directory
    output_dir = f"3Hour_Radu_nonA2A/{nodes}node"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Track emissions
    tracker = EmissionsTracker(
        project_name="create_visualization",
        experiment_id=state.get("id", "unknown"),
        measure_power_secs=1,
        log_level="critical",
        output_file=f"emissions_{state.get('id', 'unknown')}_{viz_execution_id}.csv",
        output_dir=output_dir
    )
    tracker.start()
    
    try:
         #2 LLM calls only; no PlotAgent execution
        
        # LLM CALL #1: Extract chart configuration (chart type, axes, title)
        
        state_with_config = extract_chart_config(state, default_llm)
        chart_config = state_with_config.get("chart_config")
        if chart_config is None:
            chart_config = {
                "chart_type": "line",
                "x_axis": state.get("columns", ["x"])[0] if state.get("columns") else "x",
                "y_axis": state.get("columns", ["y"])[-1] if state.get("columns") else "y",
                "title": "Sales Chart"
            }
        
        # LLM CALL #2: Generate Python code for the chart
        
        viz_code = create_chart_code(state_with_config, default_llm)
        
        res = {
            "generated_code": viz_code,
            "image_path": None,
            "csv_path": None,
            "chart_config_path": None,
        }
        
   
        if tracer is not None:
            try:
                with tracer.start_as_current_span("gen_visualization", openinference_span_kind="tool") as span:
                    span.set_input({
                        "chart_config": chart_config,
                        "data_shape": f"{len(state.get('rows', []))} rows x {len(state.get('columns', []))} columns"
                    })
                    span.set_output(viz_code if len(viz_code) < 1000 else viz_code[:1000] + "...")
                    span.set_attribute("agentrun_id", state.get("id"))
                    span.set_attribute("viz.execution_id", viz_execution_id)
                    span.set_attribute("viz.chart_type", chart_config.get('chart_type', 'line'))
                    span.set_attribute("viz.row_count", len(state.get('rows', [])))
                    if StatusCode:
                        span.set_status(StatusCode.OK)
                    print(f"[create_visualization] ✅ Created gen_visualization span for evaluation")
            except TypeError:
                # Fallback if openinference_span_kind not supported
                with tracer.start_as_current_span("gen_visualization") as span:
                    span.set_input({
                        "chart_config": chart_config,
                        "data_shape": f"{len(state.get('rows', []))} rows x {len(state.get('columns', []))} columns"
                    })
                    span.set_output(viz_code if len(viz_code) < 1000 else viz_code[:1000] + "...")
                    span.set_attribute("agentrun_id", state.get("id"))
                    span.set_attribute("viz.execution_id", viz_execution_id)
                    span.set_attribute("viz.chart_type", chart_config.get('chart_type', 'line'))
                    span.set_attribute("viz.row_count", len(state.get('rows', [])))
                    if StatusCode:
                        span.set_status(StatusCode.OK)
                    print(f"[create_visualization] ✅ Created gen_visualization span (fallback)")
        
        # Stop monitoring
        if usage_monitor:
            usage_monitor.stop()
            stats = usage_monitor.get_stats()
            cpu_util = stats["cpu_mean"]
            gpu_util = stats["gpu_mean"]
        else:
            cpu_util = None
            gpu_util = None
        
        emissions = tracker.stop()
        
        # Update state 
        # Include visualization_goal and generated_code like Torrado
        result = {
            **state,
            "visualization": res,
            "image_path": res.get("image_path"),
            "csv_path": res.get("csv_path"),
            "chart_config_path": res.get("chart_config_path"),
            "config": chart_config,  
            "visualization_goal": state_with_config.get("visualization_goal"),
            "chart_config": chart_config,
            "analyze_data": state.get("analyze_data"),
            "answer": state.get("answer", []) + [f"This is the code to visualize: {viz_code}"],  
            "energy_create_visualization": emissions,
            "ids_create_visualization": viz_execution_id,  
            "viz_execution_id": viz_execution_id,
            "cpu_utilization_create_visualization": cpu_util,
            "gpu_utilization_create_visualization": gpu_util
        }
        
        # Queue evaluation
        if queue_evaluation and visualization_eval:
            queue_evaluation(
                tool_name="create_visualization",
                eval_func=visualization_eval,
                run_id=state.get("id"),
                energy=emissions,
                tool_execution_ids=viz_execution_id,
                cpu_utilization=cpu_util,
                gpu_utilization=gpu_util,
                nodes=nodes,
                users=state.get("users")
            )
        
        print(f"[Plot→Orchestrator] ✅ create_visualization completed (code-only)")
        return result
        
    except Exception as e:
        print(f"[Plot→Orchestrator] ❌ Error in create_visualization: {e}")
        if usage_monitor:
            usage_monitor.stop()
        tracker.stop()
        return {**state, "error": f"create_visualization failed: {e}"}


def run_env3_openai_agents(prompt: str, nodes: int = 3, users: int = 1) -> Dict[str, Any]:
    """
    Run Env3 with OpenAI Agents SDK, replicates Torrado's original LangGraph workflow.
    
    Args:
        prompt: User prompt
        nodes: Number of parallel nodes (1, 3, 5, or 10) - configures SQL and Insight agents
        users: Number of concurrent users (for result organization)
        
    Returns:
        Dict with SQL results, analysis, optional visualization, and orchestrator energy
    """
    # Validate nodes
    if nodes not in [1, 3, 5, 10]:
        print(f"[WARNING] Invalid nodes={nodes}, using default: 3")
        nodes = 3
    
    run_id = str(uuid4())
    state = {
        "prompt": prompt,
        "id": run_id,
        "used_tools": [],
        "answer": [],
        "energy_decide_tool": [],
        "decide_tool_execution_ids": [],
        "nodes": nodes,
        "users": users,
        "data": None,  # Explicitly None - no data yet
        "rows": None,  # Explicitly None - no data yet
        "columns": None,
        "sql": None,  # Explicitly None
        "analysis": None,
        "analyze_data": None,
        "chart_config": None,
    }
    
    print(f"[Env3 OpenAI Agents]  Initialized state for run {run_id}")
    print(f"[Env3 OpenAI Agents]  Initial state - has_data: {bool(state.get('rows') or state.get('data'))}, used_tools: {state.get('used_tools', [])}")
    
    print(f"\n{'='*80}")
    print(f"[Env3 OpenAI Agents]  STARTING NEW WORKFLOW")
    print(f"{'='*80}")
    print(f"[Env3 OpenAI Agents] Prompt: {prompt}")
    print(f"[Env3 OpenAI Agents] Configuration: {nodes} nodes, {users} users")
    print(f"[Env3 OpenAI Agents] Run ID: {run_id}")
    print(f"{'='*80}\n")
    
    # Main orchestration loop
    max_iterations = 10  # Safety limit
    iteration = 0
    
    if tracer is not None:
        with tracer.start_as_current_span("Env3OpenAIAgentsRun", openinference_span_kind="agent") as span:
            span.set_attribute("agentrun_id", run_id)
            span.set_input({"prompt": prompt, "nodes": nodes, "users": users})
            
            while iteration < max_iterations:
                iteration += 1
                print(f"\n{'─'*80}")
                print(f"[Env3 OpenAI Agents]  ITERATION {iteration}/{max_iterations}")
                print(f"{'─'*80}")
                print(f"[State] used_tools: {state.get('used_tools', [])}")
                print(f"[State] has_data (rows): {len(state.get('rows', [])) if state.get('rows') else 0} rows")
                print(f"[State] has_analysis: {bool(state.get('analysis'))}")
                print(f"[State] has_chart_config: {bool(state.get('chart_config'))}")
                
                # Orchestrator decides next tool
                print(f"\n Orchestrator deciding next action...")
                tool_choice = decide_tool(state, default_llm)
                print(f"\n✅ Orchestrator decision: '{tool_choice}'")
                print(f"[State] Updated used_tools: {state.get('used_tools', [])}")
                
                # Execute selected tool (Torrado's approach: rely on LLM instructions, no programmatic guards)
                print(f"\n▶️  Executing tool: {tool_choice}")
                
                if tool_choice == "lookup_sales_data":
                    state = lookup_sales_data(state, nodes)
                    # used_tools already updated in decide_tool (Torrado's approach)
                    print(f"✅ lookup_sales_data completed - Retrieved {len(state.get('rows', []))} rows")
                    
                elif tool_choice == "analyzing_data":
                    if not state.get("rows"):
                        print(f"⚠️  WARNING: No data available for analysis!")
                    state = analyzing_data(state, nodes)
                    # used_tools already updated in decide_tool (Torrado's approach)
                    print(f"✅ analyzing_data completed - Analysis length: {len(str(state.get('analysis', '')))}")
                    
                elif tool_choice == "create_visualization":
                    if not state.get("analysis"):
                        print(f"⚠️  WARNING: No analysis available for visualization!")
                    state = create_visualization(state, nodes)
                    # used_tools already updated in decide_tool (Torrado's approach)
                    print(f"✅ create_visualization completed")
                    
                elif tool_choice == "end":
                    print(f"\n{'='*80}")
                    print(f"[Env3 OpenAI Agents] ✅ WORKFLOW COMPLETE")
                    print(f"{'='*80}")
                    print(f"Tools executed: {state.get('used_tools', [])}")
                    print(f"{'='*80}\n")
                    break
                else:
                    print(f"\n{'='*80}")
                    print(f"[Env3 OpenAI Agents] ⚠️  UNKNOWN TOOL: {tool_choice}")
                    print(f"{'='*80}\n")
                    break
                
                # Check for errors
                if "error" in state:
                    print(f"\n{'='*80}")
                    print(f"[Env3 OpenAI Agents] ❌ ERROR IN WORKFLOW")
                    print(f"{'='*80}")
                    print(f"Error: {state['error']}")
                    print(f"{'='*80}\n")
                    break
            
            if iteration >= max_iterations:
                print(f"[Env3 OpenAI Agents] ⚠️ Reached max iterations ({max_iterations}). Ending workflow.")
            
            span.set_output(state.get("answer", []))
            if StatusCode:
                span.set_status(StatusCode.OK)
    else:
        # Same logic without tracing
        while iteration < max_iterations:
            iteration += 1
            print(f"\n{'─'*80}")
            print(f"[Env3 OpenAI Agents] 📍 ITERATION {iteration}/{max_iterations}")
            print(f"{'─'*80}")
            print(f"[State] used_tools: {state.get('used_tools', [])}")
            print(f"[State] has_data (rows): {len(state.get('rows', [])) if state.get('rows') else 0} rows")
            print(f"[State] has_analysis: {bool(state.get('analysis'))}")
            print(f"[State] has_chart_config: {bool(state.get('chart_config'))}")
            
            print(f"\n🤔 Orchestrator deciding next action...")
            tool_choice = decide_tool(state, default_llm)
            print(f"\n✅ Orchestrator decision: '{tool_choice}'")
            print(f"[State] Updated used_tools: {state.get('used_tools', [])}")
            
            # Execute selected tool (Torrado's approach: rely on LLM instructions, no programmatic guards)
            print(f"\n▶️  Executing tool: {tool_choice}")
            
            if tool_choice == "lookup_sales_data":
                state = lookup_sales_data(state, nodes)
                # used_tools already updated in decide_tool (Torrado's approach)
                print(f"✅ lookup_sales_data completed - Retrieved {len(state.get('rows', []))} rows")
                
            elif tool_choice == "analyzing_data":
                if not state.get("rows"):
                    print(f"⚠️  WARNING: No data available for analysis!")
                state = analyzing_data(state, nodes)
                # used_tools already updated in decide_tool (Torrado's approach)
                print(f"✅ analyzing_data completed - Analysis length: {len(str(state.get('analysis', '')))}")
                
            elif tool_choice == "create_visualization":
                if not state.get("analysis"):
                    print(f"⚠️  WARNING: No analysis available for visualization!")
                state = create_visualization(state, nodes)
                # used_tools already updated in decide_tool (Torrado's approach)
                print(f"✅ create_visualization completed")
                
            elif tool_choice == "end":
                print(f"\n{'='*80}")
                print(f"[Env3 OpenAI Agents] ✅ WORKFLOW COMPLETE")
                print(f"{'='*80}")
                print(f"Tools executed: {state.get('used_tools', [])}")
                print(f"{'='*80}\n")
                break
            else:
                print(f"\n{'='*80}")
                print(f"[Env3 OpenAI Agents] ⚠️  UNKNOWN TOOL: {tool_choice}")
                print(f"{'='*80}\n")
                break
            
            # Check for errors
            if "error" in state:
                print(f"\n{'='*80}")
                print(f"[Env3 OpenAI Agents] ❌ ERROR IN WORKFLOW")
                print(f"{'='*80}")
                print(f"Error: {state['error']}")
                print(f"{'='*80}\n")
                break
        
        if iteration >= max_iterations:
            print(f"[Env3 OpenAI Agents] ⚠️ Reached max iterations ({max_iterations}). Ending workflow.")
    
    print(f"[Env3 OpenAI Agents] ✅ Workflow completed after {iteration} iterations")
    return state

