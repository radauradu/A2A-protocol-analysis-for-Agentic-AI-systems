import os
from typing import Dict, List, Optional
from codecarbon import EmissionsTracker

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

try:
    from utils_copy import tracer
    from opentelemetry.trace import StatusCode
except Exception:
    tracer = None
    StatusCode = None

# Import A2A client for agent-to-agent communication
try:
    from a2a import A2AClient
except Exception:
    A2AClient = None

# Import UsageMonitor for CPU/GPU tracking
try:
    from usage_monitor import UsageMonitor
except ImportError:
    UsageMonitor = None


def _make_llm_insight():

    base = os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_API_BASE") or os.getenv("OLLAMA_BASE_URL", "").replace("/v1", "") or "http://host.docker.internal:11434"
    model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    return ChatOllama(model=model, base_url=base, temperature=0.1, streaming=True)


class InsightAgent:
    def __init__(self, enable_a2a: bool = False, use_parallel_analysis: bool = True, num_parallel_nodes: int = 3) -> None:
       
        self.llm = _make_llm_insight()
        self.enable_a2a = enable_a2a
        self.use_parallel_analysis = use_parallel_analysis
        self.num_parallel_nodes = num_parallel_nodes
        self.a2a_client = None
        
        if self.enable_a2a and A2AClient is not None:
            self.a2a_client = A2AClient()
            print("[InsightAgent] A2A communication enabled")
        
        if self.use_parallel_analysis:
            print(f"[InsightAgent] Parallel analysis enabled: {num_parallel_nodes} nodes")

    def _split_prompt_torrado_style(self, prompt: str) -> List[str]:
        base_patterns = [
            "Revenue trends",
            "Product category performance",
            "Promotional impact",
            "Store-level comparisons",
            "Time-based patterns",
            "Customer preferences",
            "High-performing SKUs",
            "Outlier detection",
            "Discount effectiveness",
            "Sales seasonality"
        ]
        variations = [
            "{} (statistical summary)",
            "{} using time series analysis",
            "{} with visual breakdowns",
            "{} focusing on November sales",
            "{} using moving averages",
            "{} across all stores",
            "{} per product class",
            "{} by weekday vs weekend",
            "{} with anomaly detection",
            "{} highlighting top performers",
        ]

        prompts = []
        for base in base_patterns:
            for variation in variations:
                prompts.append(f"{prompt} - {variation.format(base)}")

        return prompts[:self.num_parallel_nodes]
    
    def _analyze_single_emphasis(self, data_string: str, emphasis: str) -> str:
        """

        Uses the full data string (df.to_string()).
        
        Args:
            data_string: Full data as string (from df.to_string())
            emphasis: Specific analytical angle to focus on
            
        Returns:
            Analysis text for this emphasis
        """
        
        DATA_ANALYSIS_PROMPT = """
Analyze the following data: {data}
Your job is to answer the following question, that has an specific emphasis besides the original prompt passed by the user in this format "prompt-emphasis": {emphasis}

Please remember to just restrain yourself to explaining patterns, trends, insights or summaries of the data. There is NO need to create any code or any other thing, just the analysis of the data. 

If you feel the need to say something about code, just stick to explain the architecture of how to build a code (mentioning libraries, functions, etc.) but not the code itself.
"""
        formatted_prompt = DATA_ANALYSIS_PROMPT.format(data=data_string, emphasis=emphasis)
        
        try:
            res = self.llm.invoke(formatted_prompt)
            return getattr(res, "content", "").strip()
        except Exception as e:
            return f"Analysis failed for emphasis '{emphasis}': {str(e)}"
    
    def _fuse_analyses(self, analyses: List[str]) -> str:
        """
        Fuse multiple analyses into one summary.
        
        Args:
            analyses: List of analysis texts from different emphases
            
        Returns:
            Fused summary analysis
        """
        fusion_prompt = (
            "Given the following analysis outputs, produce a concise summary that captures the key insights from the list:\n\n"
            + str(analyses) +
            ", this by reading carefully and extracting the most important information from each of them. "
            "If something is repeated, please just keep one of them, or try to see if any subtle difference is there to summarize it into a more compact idea."
        )
        
        try:
            res = self.llm.invoke(fusion_prompt)
            return getattr(res, "content", "").strip().lower()
        except Exception as e:
            return f"Fusion failed: {str(e)}. Using first analysis."
    
    def run(self, rows: List[List], columns: List[str], prompt: str, request_visualization: bool = False, 
            run_id: Optional[str] = None, execution_id: Optional[str] = None, data_string: Optional[str] = None) -> Dict:
        # Start monitoring CPU/GPU
        usage_monitor = UsageMonitor(interval=0.5) if UsageMonitor else None
        if usage_monitor:
            usage_monitor.start()
        
        # Start CodeCarbon emissions tracking
        tracker = None
        if execution_id:
            # Create output directory if it doesn't exist
            from pathlib import Path
            # Detect environment to use correct base directory
            import os
            otel_service = os.getenv("OTEL_SERVICE_NAME", "")
            base_dir = "3Hour_Radu_nonA2A" if "env3" in otel_service.lower() else "3Hour_Radu"
            output_dir = f"{base_dir}/{self.num_parallel_nodes}node"
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            tracker = EmissionsTracker(
                project_name="insight_agent_v1",
                experiment_id=run_id or "default",
                measure_power_secs=1,
                log_level="critical",
                output_file=f"emissions_{run_id}_{execution_id}.csv",
                output_dir=output_dir
            )
            tracker.start()
        
        try:
            # Build a small preview for LLM context (10 rows to match Torrado's utils_copy)
            preview_records = []
            for r in rows[:10]:
                rec = {columns[i]: r[i] for i in range(min(len(columns), len(r)))}
                preview_records.append(rec)

            if self.llm is None:
                raise RuntimeError("InsightAgent LLM is not configured. Check OLLAMA_BASE_URL/OLLAMA_HOST.")

            # Choose analysis mode: parallel (Torrado's complex) or simple (fast)
            if self.use_parallel_analysis:
                print(f"[InsightAgent] Using parallel analysis (Torrado mode): {self.num_parallel_nodes} emphases + fusion")
                
                # Split prompt into N emphases
                sub_prompts = self._split_prompt_torrado_style(prompt)
                
                # Analyze each emphasis in parallel using LangGraph batch_as_completed
                from langgraph.graph import StateGraph, END
                from typing_extensions import TypedDict
                import uuid as uuid_module
                
                class AnalysisState(TypedDict):
                    prompt: str
                    data_string: str  # Full df.to_string() 
                    rows: List[List]
                    columns: List[str]
                    emphasis: str
                    analysis_id: str
                    run_id: str
                    analysis_result: Optional[str]
                    energy_analysis: Optional[float]
                    cpu_analysis: Optional[float]
                    gpu_analysis: Optional[float]
                
                def analyze_emphasis_node(substate: AnalysisState) -> AnalysisState:
                    """Node function for parallel analysis"""
                    analysis_id = substate["analysis_id"]
                    
                    # Start monitoring for this analysis
                    usage_monitor = UsageMonitor(interval=0.5) if UsageMonitor else None
                    if usage_monitor:
                        usage_monitor.start()
                    
                    # Create output directory if it doesn't exist
                    from pathlib import Path
                    # Detect environment to use correct base directory
                    import os
                    otel_service = os.getenv("OTEL_SERVICE_NAME", "")
                    base_dir = "3Hour_Radu_nonA2A" if "env3" in otel_service.lower() else "3Hour_Radu"
                    output_dir = f"{base_dir}/{self.num_parallel_nodes}node"
                    Path(output_dir).mkdir(parents=True, exist_ok=True)
                    
                    tracker = EmissionsTracker(
                        project_name="analyzing_data",
                        experiment_id=analysis_id,
                        measure_power_secs=1,
                        log_level="critical",
                        output_file=f"emissions_{substate['run_id']}_{analysis_id}.csv",
                        output_dir=output_dir
                    )
                    tracker.start()
                    
                    try:
                        analysis_result = self._analyze_single_emphasis(
                            substate["data_string"],
                            substate["emphasis"]
                        )
                        
                        # Stop monitoring
                        if usage_monitor:
                            usage_monitor.stop()
                            stats = usage_monitor.get_stats()
                            cpu_mean = stats["cpu_mean"]
                            gpu_mean = stats["gpu_mean"]
                        else:
                            cpu_mean = None
                            gpu_mean = None
                        
                        emissions = tracker.stop()
                        
                        return {
                            **substate,
                            "analysis_result": analysis_result,
                            "energy_analysis": emissions,
                            "cpu_analysis": cpu_mean,
                            "gpu_analysis": gpu_mean
                        }
                    except Exception as e:
                        if usage_monitor:
                            usage_monitor.stop()
                        tracker.stop()
                        return {
                            **substate,
                            "analysis_result": f"Analysis failed: {str(e)}",
                            "energy_analysis": 0.0,
                            "cpu_analysis": None,
                            "gpu_analysis": None
                        }
                
                # Create subgraph for parallel execution
                subgraph = StateGraph(AnalysisState)
                subgraph.add_node("analyze_emphasis", analyze_emphasis_node)
                subgraph.set_entry_point("analyze_emphasis")
                subgraph.add_edge("analyze_emphasis", END)
                compiled_subgraph = subgraph.compile()
                
                # Create substates for parallel execution
                sub_states = []
                for sub_prompt in sub_prompts:
                    analysis_id = str(uuid_module.uuid4())[:8]
                    sub_state = {
                        "prompt": prompt,
                        "data_string": data_string or "",  # Full df.to_string() 
                        "rows": rows,
                        "columns": columns,
                        "emphasis": sub_prompt,
                        "analysis_id": analysis_id,
                        "run_id": run_id or "unknown",
                        "analysis_result": None,
                        "energy_analysis": None,
                        "cpu_analysis": None,
                        "gpu_analysis": None
                    }
                    sub_states.append(sub_state)
                
                # Execute in parallel
                print(f"[InsightAgent] Running {len(sub_states)} parallel analyses...")
                parallel_results = list(compiled_subgraph.batch_as_completed(inputs=sub_states))
                
                # Extract results
                analyses = []
                analysis_energies = []
                analysis_ids = []
                cpu_analyses = []
                gpu_analyses = []
                
                for result_tuple in parallel_results:
                    if isinstance(result_tuple, tuple) and len(result_tuple) == 2:
                        _, result = result_tuple
                    else:
                        result = result_tuple
                    
                    analyses.append(result.get("analysis_result", ""))
                    analysis_energies.append(result.get("energy_analysis", 0.0))
                    analysis_ids.append(result.get("analysis_id", ""))
                    cpu_analyses.append(result.get("cpu_analysis"))
                    gpu_analyses.append(result.get("gpu_analysis"))
                
                # Fuse all analyses (1 more LLM call)
                print("[InsightAgent] Fusing analyses...")
                analysis = self._fuse_analyses(analyses)
                print(f"[InsightAgent] ✅ Parallel analysis complete ({len(analyses)} emphases fused)")
                
                # Store parallel metrics for evaluation
                result_metrics = {
                    "analysis_execution_ids": analysis_ids,
                    "energy_analyzing_data": analysis_energies,
                    "cpu_utilization_analyzing_data": cpu_analyses,
                    "gpu_utilization_analyzing_data": gpu_analyses,
                    "num_parallel_nodes": self.num_parallel_nodes
                }
            else:
                # Simple single-pass analysis (original fast mode)
                print("[InsightAgent] Using simple single-pass analysis (fast mode)")
                system = SystemMessage(content=(
                    "You are a data analyst. Given tabular sales data, produce a concise, factual analysis of trends. "
                    "Focus on:\n"
                    "- Overall trends (increasing, decreasing, stable)\n"
                    "- Notable spikes or drops in revenue or units\n"
                    "- Time-based patterns (beginning vs end of period)\n"
                    "- Total metrics if relevant\n"
                    "Be specific with numbers when available. Avoid speculation. Keep it under 150 words."
                ))
                human = HumanMessage(content=(
                    f"User prompt: {prompt}\n\n"
                    f"Data columns: {columns}\n"
                    f"Sample data (first {len(preview_records)} rows out of {len(rows)} total):\n{preview_records}\n\n"
                    f"Provide a brief analysis of the trends in this data."
                ))

                try:
                    res = self.llm.invoke([system, human])
                    analysis = getattr(res, "content", "").strip()
                except Exception as e:
                    raise RuntimeError(f"InsightAgent LLM call failed: {str(e)}. Check Ollama connectivity.")
            
            if not analysis:
                raise RuntimeError("InsightAgent LLM returned an empty analysis. Verify Ollama connectivity and model.")
            
            # Store result metrics if parallel analysis was used
            if self.use_parallel_analysis and 'result_metrics' in locals():
                # Will be added to final result
                pass
            else:
                result_metrics = {}

            # Minimal chart config with sensible defaults for sales data
            def pick_equal(keys, names):
                for n in names:
                    for k in keys:
                        if k.lower() == n:
                            return k
                return None

            x_pref = pick_equal(columns, ["day", "sold_date", "date", "sold date"])
            y_pref = None
            for target in ["revenue", "daily_revenue", "total_sale_value", "units", "daily_units_sold", "qty_sold"]:
                y_pref = next((c for c in columns if c.lower() == target), None)
                if y_pref:
                    break

            chart_config = {
                "chart_type": "line",
                "x_axis": x_pref or (columns[0] if columns else "x"),
                "y_axis": y_pref or (columns[1] if len(columns) > 1 else (columns[0] if columns else "y")),
                "title": "Auto chart",
            }

            # Trace analysis with proper attributes for evaluation
            if tracer is not None:
                with tracer.start_as_current_span("data_analysis", openinference_span_kind="chain") as span:
                    span.set_input({"prompt": prompt, "preview_rows": len(preview_records)})
                    span.set_output(analysis)
                    span.set_attribute("chart_type", chart_config.get("chart_type"))
                    if run_id:
                        span.set_attribute("agentrun_id", run_id)  # For evaluation queries
                        span.set_attribute("analysis.run_id", run_id)
                    if execution_id:
                        span.set_attribute("analysis.execution_id", execution_id)
            
            # Base response
            response = {
                "analysis": analysis,
                "chart_config": chart_config,
                "data_preview": preview_records,
                "provenance": {"sql_used": None, "row_count": len(rows)},
            }
            
            # Add parallel metrics if available
            if result_metrics:
                response.update(result_metrics)
            
            # If A2A enabled and visualization requested, send A2A message to PlotAgent
            if self.enable_a2a and request_visualization and self.a2a_client is not None:
                try:
                    print("[InsightAgent] Requesting visualization via A2A protocol...")
                    
                    # Create A2A payload
                    a2a_payload = {
                        "data": {
                            "rows": rows,           # All rows sent
                            "columns": columns      # All columns sent
                        },
                        "chart_config": chart_config,
                        "context": analysis[:300],  # First 300 chars of analysis as context
                        "preferences": chart_config,
                        "execute": False  # A2A code-only: no plot file creation (match Torrado's)
                    }
                
                    # Trace A2A message sending with full data transparency
                    if tracer is not None:
                        with tracer.start_as_current_span(
                            "a2a_send_to_plotagent",
                            openinference_span_kind="tool"
                        ) as a2a_span:
                            a2a_span.set_attribute("a2a.from_agent", "insight_agent_v1")
                            a2a_span.set_attribute("a2a.to_agent", "plot")
                            a2a_span.set_attribute("a2a.method", "create_visualization")
                            a2a_span.set_attribute("a2a.data_rows_sent", len(rows))
                            a2a_span.set_attribute("a2a.data_columns_sent", len(columns))
                            a2a_span.set_attribute("a2a.context_length", len(analysis[:300]))
                            
                            # Create data fingerprint for verification
                            import hashlib
                            import json
                            data_fingerprint = hashlib.md5(
                                json.dumps(rows, sort_keys=True).encode()
                            ).hexdigest()
                            a2a_span.set_attribute("a2a.data_fingerprint", data_fingerprint)
                            
                            # Show what's being sent (preview + metadata)
                            a2a_span.set_input({
                                "message": "Sending complete dataset to PlotAgent via A2A",
                                "data_transmission": {
                                    "total_rows_sent": len(rows),
                                    "total_columns": len(columns),
                                    "columns": columns,
                                    "preview_note": "Showing first 3 and last 1 row only. Full dataset is sent.",
                                    "first_3_rows": rows[:3],
                                    "last_row": rows[-1] if rows else None,
                                    "data_fingerprint": data_fingerprint
                                },
                                "analysis_context": {
                                    "full_analysis_length_chars": len(analysis),
                                    "context_sent_chars": len(analysis[:300]),
                                    "preview": analysis[:200]
                                },
                                "chart_config": chart_config
                            })
                            
                            # Send A2A message to PlotAgent
                            viz_response = self.a2a_client.send_message(
                                to_agent="plot",
                                method="create_visualization",
                                params=a2a_payload,
                                from_agent="insight_agent_v1"
                            )
                            
                            # Show what we received back
                            a2a_span.set_output({
                                "visualization_created": viz_response.get('image_path') is not None,
                                "image_path": viz_response.get('image_path'),
                                "a2a_conversation_id": viz_response.get('a2a_conversation_id'),
                                "a2a_execution_mode": viz_response.get('a2a_execution_mode'),
                                "a2a_environment": viz_response.get('a2a_environment')
                            })
                            a2a_span.set_status(StatusCode.OK)
                    else:
                        # No tracing - just send
                        viz_response = self.a2a_client.send_message(
                            to_agent="plot",
                            method="create_visualization",
                            params=a2a_payload,
                            from_agent="insight_agent_v1"
                        )
                
                    print(f"[InsightAgent] ✅ Received visualization from PlotAgent via A2A")
                    print(f"[InsightAgent] Image: {viz_response.get('image_path')}")
                    
                    # Add A2A response to output
                    response["a2a_visualization"] = viz_response
                    response["a2a_enabled"] = True
                    
                except Exception as e:
                    print(f"[InsightAgent] ⚠️ A2A visualization request failed: {e}")
                    print("[InsightAgent] Falling back to chart_config only")
                    response["a2a_error"] = str(e)
                    response["a2a_enabled"] = False
            else:
                response["a2a_enabled"] = False
            
            # Add monitoring metrics
            if usage_monitor:
                usage_monitor.stop()
                stats = usage_monitor.get_stats()
                response["cpu_utilization"] = stats["cpu_mean"]
                response["gpu_utilization"] = stats["gpu_mean"]
            
            # Stop emissions tracking
            if tracker:
                emissions = tracker.stop()
                response["energy_consumed"] = emissions
            
            return response
            
        except Exception as e:
            # Cleanup on error
            if usage_monitor:
                usage_monitor.stop()
            if tracker:
                tracker.stop()
            raise e


