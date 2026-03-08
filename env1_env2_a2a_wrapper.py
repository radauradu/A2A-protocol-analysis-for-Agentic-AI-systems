"""
A2A-Enabled Wrapper for Env1 + Env2

This wrapper enables Agent-to-Agent communication between InsightAgent and PlotAgent
using the A2A protocol. InsightAgent dynamically discovers PlotAgent and requests
visualization via A2A messages.
"""

from typing import Dict, Any
from uuid import uuid4
from opentelemetry.trace import StatusCode

from utils.response_formatter import format_old_response

try:
    from utils_copy import tracer
except Exception:
    tracer = None


def run_env1_then_env2_a2a(prompt: str, input_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run env1 with A2A-enabled InsightAgent that communicates with PlotAgent via A2A protocol.
    
    Flow:
    1. SQLAgent generates data
    2. InsightAgent analyzes data
    3. InsightAgent discovers PlotAgent via AgentCard
    4. InsightAgent sends A2A message to PlotAgent requesting visualization
    5. PlotAgent receives A2A message, creates visualization, responds
    6. InsightAgent receives visualization paths
    7. Merged result returned with A2A metadata
    
    Args:
        prompt: User prompt
        input_state: State dict with at least "id" field
        
    Returns:
        Dict with analysis, visualization, and A2A conversation metadata
    """
    print("[A2A Workflow] Starting env1-then-env2 with A2A protocol")
    
    run_id = input_state.get("id", str(uuid4()))
    
    if tracer is not None:
        with tracer.start_as_current_span("AgentRun_A2A", openinference_span_kind="agent") as span:
            span.set_attribute("debug_info", "env1_then_env2_a2a_execution")
            span.set_attribute("a2a.enabled", True)
            span.set_input({"prompt": prompt, "id": run_id})
            
            try:
                # Run env1 with A2A-enabled InsightAgent
                # This is handled by modifying the graph to use A2A
                from env1_a2a_graph import run_env1_a2a
                
                # Extract nodes and users from input_state for dynamic configuration
                nodes = input_state.get("nodes", 3)
                users = input_state.get("users", 1)
                
                env1_output = run_env1_a2a(prompt, nodes=nodes, users=users)
                
                # Extract A2A metadata
                a2a_viz = env1_output.get("a2a_visualization", {})
                a2a_enabled = env1_output.get("a2a_enabled", False)
                a2a_conversation_id = a2a_viz.get("a2a_conversation_id") if a2a_enabled else None
                
                # Format response
                formatted_response = format_old_response(env1_output, a2a_viz if a2a_enabled else None)
                
                # Add A2A metadata
                formatted_response["a2a_enabled"] = a2a_enabled
                if a2a_enabled:
                    formatted_response["a2a_conversation_id"] = a2a_conversation_id
                    formatted_response["a2a_agent"] = a2a_viz.get("a2a_agent", "plot")
                    formatted_response["image_path"] = a2a_viz.get("image_path")
                    formatted_response["csv_path"] = a2a_viz.get("csv_path")
                    formatted_response["chart_config_path"] = a2a_viz.get("chart_config_path")
                
                span.set_output(formatted_response.get("answer"))
                span.set_attribute("a2a.conversation_id", a2a_conversation_id or "none")
                span.set_status(StatusCode.OK)
                
                print(f"[A2A Workflow] Completed with A2A conversation: {a2a_conversation_id}")
                print(f"Este es el id: {run_id}")
                
                return formatted_response
                
            except Exception as e:
                span.set_status(StatusCode.ERROR)
                span.record_exception(e)
                print(f"[A2A Workflow] Error: {e}")
                raise e
    else:
        # No tracing
        from env1_a2a_graph import run_env1_a2a
        
        # Extract nodes and users from input_state for dynamic configuration
        nodes = input_state.get("nodes", 3)
        users = input_state.get("users", 1)
        
        env1_output = run_env1_a2a(prompt, nodes=nodes, users=users)
        a2a_viz = env1_output.get("a2a_visualization", {})
        a2a_enabled = env1_output.get("a2a_enabled", False)
        
        formatted_response = format_old_response(env1_output, a2a_viz if a2a_enabled else None)
        formatted_response["a2a_enabled"] = a2a_enabled
        if a2a_enabled:
            formatted_response["a2a_conversation_id"] = a2a_viz.get("a2a_conversation_id")
            formatted_response["image_path"] = a2a_viz.get("image_path")
            formatted_response["csv_path"] = a2a_viz.get("csv_path")
        
        print(f"[A2A Workflow] Completed")
        print(f"Este es el id: {run_id}")
        
        return formatted_response

