"""
 handles tracing and formatting
"""

from typing import Dict, Any
from env3_openai_agents import run_env3_openai_agents


def run_env3_openai_agents_with_tracking(prompt: str, nodes: int = 3, users: int = 1) -> Dict[str, Any]:
    """
    wrapper function for Env3 OpenAI Agents SDK workflow.
    handles tracing setup and returns formatted response.
    
    Args:
        prompt: User prompt
        nodes: Number of parallel nodes (1, 3, 5, or 10)
        users: Number of concurrent users (for logging)
        
    Returns: dict with formatted response matching Env1 format
    """
    try:
        # Run the workflow
        result = run_env3_openai_agents(prompt, nodes=nodes, users=users)
        
        # Format response to match Env1 structure
        formatted_response = {
            "prompt": prompt,
            "run_id": result.get("id"),
            "sql": result.get("sql"),
            "rows": result.get("rows"),
            "columns": result.get("columns"),
            "analysis": result.get("analysis") or result.get("analyze_data"),
            "chart_config": result.get("chart_config"),
            "visualization": result.get("visualization"),
            "image_path": result.get("image_path"),
            "answer": result.get("answer", []),
            "used_tools": result.get("used_tools", []),
            "energy_decide_tool": result.get("energy_decide_tool", []),
            "energy_lookup_sales_data": result.get("energy_lookup_sales_data"),
            "energy_analyzing_data": result.get("energy_analyzing_data"),
            "energy_create_visualization": result.get("energy_create_visualization"),
            "nodes": nodes,
            "users": users,
        }
        
        # Add error if present
        if "error" in result:
            formatted_response["error"] = result["error"]
        
        return formatted_response
        
    except Exception as e:
        print(f"[Env3 Wrapper] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "prompt": prompt,
            "error": str(e),
            "nodes": nodes,
            "users": users,
        }

