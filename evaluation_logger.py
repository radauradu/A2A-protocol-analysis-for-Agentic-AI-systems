"""
Evaluation Logger: Merges LLM evaluations with energy/utilization data and logs to CSV.
Matches Torrado's exact format from utils_copy3.py (and utils_copy1, utils_copy5, utils_copy10).
"""
import pandas as pd
import threading
from pathlib import Path
from typing import Optional, List, Union
import queue
import os


# Thread-safe CSV writing
csv_lock = threading.Lock()

def log_evaluation_to_csv(
    eval_df: pd.DataFrame,
    tool_name: str,
    run_id: str,
    file_path: Optional[str] = None,
    energy: Optional[Union[float, List[float]]] = None,
    tool_execution_id: Optional[Union[str, List[str]]] = None,
    cpu_utilization: Optional[Union[float, List[float]]] = None,
    gpu_utilization: Optional[Union[float, List[float]]] = None,
    execution_time: Optional[Union[float, List[float]]] = None,
    cpu_energy: Optional[float] = None,
    gpu_energy: Optional[float] = None,
    ram_energy: Optional[float] = None,
    emissions_rate: Optional[float] = None,
    timestamp: Optional[str] = None,
    nodes: Optional[int] = None,
    users: Optional[int] = None,
    a2a_request_size_bytes: Optional[int] = None,
    a2a_response_size_bytes: Optional[int] = None,
    a2a_total_size_bytes: Optional[int] = None,
):
    """

    
    Args:
        eval_df: DataFrame with evaluation results from Phoenix (score, label, context.span_id, etc.)
        tool_name: Name of the tool/agent being evaluated
        run_id: Unique run identifier (used as 'id' column)
        file_path: Path to output CSV file (if None, determined from nodes/users)
        energy: Energy consumption (kWh) - kept for backward compatibility but not used (read from CSV)
        tool_execution_id: Tool execution ID(s) - maps to id_tool column and used to read emissions CSV
        cpu_utilization: CPU utilization percentage
        gpu_utilization: GPU utilization percentage
        execution_time: Execution time in seconds (for A2A calls)
        cpu_energy: CPU energy in kWh (for A2A calls)
        gpu_energy: GPU energy in kWh (for A2A calls)
        ram_energy: RAM energy in kWh (for A2A calls)
        emissions_rate: Emissions rate (for A2A calls)
        timestamp: Actual execution timestamp (for A2A calls)
        nodes: Number of parallel nodes (for folder organization and emissions folder)
        users: Number of concurrent users (for folder organization)
    """
    if eval_df is None or eval_df.empty:
        print(f"[⚠️] Skipping log for {tool_name}: empty evaluation dataframe")
        return
    
    # Determine base directory based on environment (A2A vs non-A2A)
    
    otel_service = os.getenv("OTEL_SERVICE_NAME", "")
    if "env3" in otel_service.lower() or "non_a2a" in otel_service.lower():
        base_dir = "3Hour_Radu_nonA2A"
    else:
        base_dir = "3Hour_Radu"
    
    # Debug, Print detected base directory
    print(f"[evaluation_logger] Detected OTEL_SERVICE_NAME: {otel_service}")
    print(f"[evaluation_logger] Using base_dir: {base_dir}")
    
    # Determine file path based on nodes/users if not provided
    if file_path is None:
        if nodes is not None and users is not None:
         
            folder = Path(base_dir) / f"{users}_{nodes}"
            folder.mkdir(parents=True, exist_ok=True)
            file_path = str(folder / f"tool_evaluations_{nodes}.csv")
            print(f"[evaluation_logger] Created folder: {folder.absolute()}")
            print(f"[evaluation_logger] Will save to: {Path(file_path).absolute()}")
            print(f"[evaluation_logger] Current working directory: {Path.cwd()}")
        else:
            file_path = "tool_evaluations.csv"
            print(f"[evaluation_logger] WARNING: nodes={nodes}, users={users} - using default path: {file_path}")
    
    # Determine emissions folder based on nodes 
    emissions_dir = f"{base_dir}/{nodes}node" if nodes is not None else f"{base_dir}/3node"
    print(f"[evaluation_logger] Looking for emissions in: {Path(emissions_dir).absolute()}")
    
   
    eval_df = eval_df.copy()
    
    if not isinstance(eval_df.index, pd.RangeIndex):
        eval_df = eval_df.reset_index()
    
    eval_df["tool_name"] = tool_name
    eval_df["id"] = run_id
    
    # Extract context.span_id for potential use as id_tool, then drop it
    span_id_value = None
    if "context.span_id" in eval_df.columns:
        span_id_value = eval_df["context.span_id"].iloc[0] if len(eval_df) > 0 else None
    elif "index" in eval_df.columns:
        span_id_value = eval_df["index"].iloc[0] if len(eval_df) > 0 else None
    
    # Map tool_execution_id to id_tool 
    # Priority: tool_execution_id parameter > span_id_value
    if tool_execution_id is not None:
        if isinstance(tool_execution_id, list):
           
            num_ids = len(tool_execution_id)
            num_rows = len(eval_df)
            
            if num_ids == num_rows:
                # Perfect match: assign 1-to-1
                eval_df["id_tool"] = tool_execution_id
                print(f"[{tool_name}] Mapped {num_ids} execution IDs to {num_rows} eval rows (1-to-1)")
            elif num_rows < num_ids:
                # More IDs than rows: use first N IDs
                eval_df["id_tool"] = tool_execution_id[:num_rows]
                print(f"[{tool_name}] Mapped {num_rows} IDs to {num_rows} eval rows (truncated from {num_ids})")
            else:
                # More rows than IDs: assign IDs cyclically or pad
                eval_df["id_tool"] = (tool_execution_id * ((num_rows // num_ids) + 1))[:num_rows]
                print(f"[{tool_name}] Mapped {num_ids} IDs to {num_rows} eval rows (repeated/padded)")
        else:
            # Single execution ID, apply to all rows
            eval_df["id_tool"] = tool_execution_id
            print(f"[{tool_name}] Mapped single ID to all {len(eval_df)} rows")
    elif span_id_value is not None:
        # Fallback to span_id_value if tool_execution_id not provided
        eval_df["id_tool"] = span_id_value
        print(f"[{tool_name}] Used span_id as fallback for id_tool")
    else:
        eval_df["id_tool"] = None
        print(f"[{tool_name}] No id_tool available")
    

    if len(eval_df) > 1 and "id_tool" in eval_df.columns:
        try:
            original_len = len(eval_df)
            # Try to deduplicate across all columns first
            eval_df = eval_df.drop_duplicates(keep="first")
            if len(eval_df) < original_len:
                print(f"[{tool_name}] ⚠️  Removed {original_len - len(eval_df)} exact duplicate rows")
        except TypeError:
          
            print(f"[{tool_name}] ℹ️  Falling back to deduplication on id_tool")
            original_len = len(eval_df)
            eval_df = eval_df.drop_duplicates(subset=["id_tool"], keep="first")
            if len(eval_df) < original_len:
                print(f"[{tool_name}] ⚠️  Removed {original_len - len(eval_df)} duplicate rows based on id_tool")
    
    # Preserve score and label from Phoenix (if they exist)
    score_col = eval_df["score"] if "score" in eval_df.columns else None
    label_col = eval_df["label"] if "label" in eval_df.columns else None
    
    # Drop ALL Phoenix-specific columns now 
    phoenix_columns = ["context.span_id", "index", "explanation", "energy_kwh", "exceptions", 
                      "execution_status", "execution_seconds", "run_id"]
    for col in phoenix_columns:
        if col in eval_df.columns:
            eval_df = eval_df.drop(columns=[col], errors="ignore")
    
    # Initialize ALL required columns with None 
    required_columns = ["cpu_energy", "gpu_energy", "ram_energy", "emissions_rate", 
                       "execution_time", "total_energy", "timestamp",
                       "cpu_utilization", "gpu_utilization", "nodes", "users",
                       "score", "label"]
    for col in required_columns:
        if col not in eval_df.columns:
            eval_df[col] = None
    
    # Restore score and label if they were present
    if score_col is not None:
        eval_df["score"] = score_col
    if label_col is not None:
        eval_df["label"] = label_col
    
    # Set nodes and users values
    eval_df["nodes"] = nodes
    eval_df["users"] = users
    
    # Set CPU/GPU utilization values
    if isinstance(cpu_utilization, list) and len(cpu_utilization) == len(eval_df):
        eval_df["cpu_utilization"] = cpu_utilization
    elif isinstance(cpu_utilization, (int, float)):
        eval_df["cpu_utilization"] = cpu_utilization
    
    if isinstance(gpu_utilization, list) and len(gpu_utilization) == len(eval_df):
        eval_df["gpu_utilization"] = gpu_utilization
    elif isinstance(gpu_utilization, (int, float)):
        eval_df["gpu_utilization"] = gpu_utilization
    
    id_tool_col = eval_df["id_tool"]
    
    # Case 1: Multiple tool executions (list of id_tool values)
    if isinstance(id_tool_col, pd.Series) and id_tool_col.notna().any():
        # Check if we have multiple unique id_tool values
        unique_ids = id_tool_col.dropna().unique()
        if len(unique_ids) > 1 or (isinstance(tool_execution_id, list) and len(tool_execution_id) > 1):
            # Multiple executions, match each to eval_df rows
            for idx, tool_id in enumerate(id_tool_col):
                if pd.notna(tool_id) and tool_id:
                    emissions_file = Path(emissions_dir) / f"emissions_{run_id}_{tool_id}.csv"
                    if emissions_file.exists():
                        try:
                            row = pd.read_csv(emissions_file).iloc[0]  # Only one row expected
                            mask = eval_df["id_tool"] == tool_id
                            eval_df.loc[mask, "cpu_energy"] = row.get("cpu_energy")
                            eval_df.loc[mask, "gpu_energy"] = row.get("gpu_energy")
                            eval_df.loc[mask, "ram_energy"] = row.get("ram_energy")
                            eval_df.loc[mask, "emissions_rate"] = row.get("emissions_rate")
                            eval_df.loc[mask, "execution_time"] = row.get("duration")
                            eval_df.loc[mask, "total_energy"] = row.get("energy_consumed")
                            eval_df.loc[mask, "timestamp"] = row.get("timestamp")
                        except Exception as e:
                            print(f"⚠️ Error reading emissions for {tool_id}: {e}")
                    else:
                        print(f"⚠️ File not found: emissions_{run_id}_{tool_id}.csv")
        else:
            # Single execution, apply to all rows
            tool_id = unique_ids[0] if len(unique_ids) > 0 else (tool_execution_id if isinstance(tool_execution_id, str) else None)
            if tool_id:
                emissions_file = Path(emissions_dir) / f"emissions_{run_id}_{tool_id}.csv"
                if emissions_file.exists():
                    try:
                        row = pd.read_csv(emissions_file).iloc[0]
                        eval_df.loc[:, "cpu_energy"] = row.get("cpu_energy")
                        eval_df.loc[:, "gpu_energy"] = row.get("gpu_energy")
                        eval_df.loc[:, "ram_energy"] = row.get("ram_energy")
                        eval_df.loc[:, "emissions_rate"] = row.get("emissions_rate")
                        eval_df.loc[:, "execution_time"] = row.get("duration")
                        eval_df.loc[:, "total_energy"] = row.get("energy_consumed")
                        eval_df.loc[:, "timestamp"] = row.get("timestamp")
                    except Exception as e:
                        print(f"⚠️ Error reading emissions for {tool_id}: {e}")
                else:
                    print(f"⚠️ File not found: emissions_{run_id}_{tool_id}.csv")
    
    # Case 2: Single tool_execution_id provided directly
    elif isinstance(tool_execution_id, str):
        emissions_file = Path(emissions_dir) / f"emissions_{run_id}_{tool_execution_id}.csv"
        if emissions_file.exists():
            try:
                row = pd.read_csv(emissions_file).iloc[0]
                eval_df.loc[:, "cpu_energy"] = row.get("cpu_energy")
                eval_df.loc[:, "gpu_energy"] = row.get("gpu_energy")
                eval_df.loc[:, "ram_energy"] = row.get("ram_energy")
                eval_df.loc[:, "emissions_rate"] = row.get("emissions_rate")
                eval_df.loc[:, "execution_time"] = row.get("duration")
                eval_df.loc[:, "total_energy"] = row.get("energy_consumed")
                eval_df.loc[:, "timestamp"] = row.get("timestamp")
            except Exception as e:
                print(f"⚠️ Error reading emissions for {tool_execution_id}: {e}")
        else:
            print(f"⚠️ File not found: emissions_{run_id}_{tool_execution_id}.csv")
    
    # Case 3: List of tool_execution_ids
    elif isinstance(tool_execution_id, list) and len(tool_execution_id) > 0:
        for idx, exec_id in enumerate(tool_execution_id):
            if exec_id and idx < len(eval_df):
                emissions_file = Path(emissions_dir) / f"emissions_{run_id}_{exec_id}.csv"
                if emissions_file.exists():
                    try:
                        row = pd.read_csv(emissions_file).iloc[0]
                        # Match by index if id_tool not available
                        if "id_tool" in eval_df.columns and eval_df.loc[idx, "id_tool"] == exec_id:
                            mask = eval_df["id_tool"] == exec_id
                            eval_df.loc[mask, "cpu_energy"] = row.get("cpu_energy")
                            eval_df.loc[mask, "gpu_energy"] = row.get("gpu_energy")
                            eval_df.loc[mask, "ram_energy"] = row.get("ram_energy")
                            eval_df.loc[mask, "emissions_rate"] = row.get("emissions_rate")
                            eval_df.loc[mask, "execution_time"] = row.get("duration")
                            eval_df.loc[mask, "total_energy"] = row.get("energy_consumed")
                            eval_df.loc[mask, "timestamp"] = row.get("timestamp")
                        else:
                            # Match by index
                            eval_df.loc[idx, "cpu_energy"] = row.get("cpu_energy")
                            eval_df.loc[idx, "gpu_energy"] = row.get("gpu_energy")
                            eval_df.loc[idx, "ram_energy"] = row.get("ram_energy")
                            eval_df.loc[idx, "emissions_rate"] = row.get("emissions_rate")
                            eval_df.loc[idx, "execution_time"] = row.get("duration")
                            eval_df.loc[idx, "total_energy"] = row.get("energy_consumed")
                            eval_df.loc[idx, "timestamp"] = row.get("timestamp")
                    except Exception as e:
                        print(f"⚠️ Error reading emissions for {exec_id}: {e}")
    
    #   Use passed energy/CPU/GPU if no emissions CSV was found 
    #  essential for A2A calls (like create_visualization) where env2 tracks energy
    if eval_df["total_energy"].isna().all() and energy is not None:
        print(f"[{tool_name}] Using passed energy parameter as fallback: {energy}")
        if isinstance(energy, (int, float)):
            eval_df["total_energy"] = energy
        elif isinstance(energy, list) and len(energy) > 0:
            if len(energy) == len(eval_df):
                eval_df["total_energy"] = energy
            else:
                eval_df["total_energy"] = energy[0]  
    
    # Ensure CPU/GPU utilization is set (already handled above but double-check for A2A)
    if eval_df["cpu_utilization"].isna().all() and cpu_utilization is not None:
        print(f"[{tool_name}] Using passed cpu_utilization: {cpu_utilization}")
        eval_df["cpu_utilization"] = cpu_utilization if not isinstance(cpu_utilization, list) else (cpu_utilization[0] if len(cpu_utilization) > 0 else None)
    
    if eval_df["gpu_utilization"].isna().all() and gpu_utilization is not None:
        print(f"[{tool_name}] Using passed gpu_utilization: {gpu_utilization}")
        eval_df["gpu_utilization"] = gpu_utilization if not isinstance(gpu_utilization, list) else (gpu_utilization[0] if len(gpu_utilization) > 0 else None)
    
    # Fallback for execution_time (important for A2A calls)
    if eval_df["execution_time"].isna().all() and execution_time is not None:
        print(f"[{tool_name}] Using passed execution_time: {execution_time}")
        eval_df["execution_time"] = execution_time if not isinstance(execution_time, list) else (execution_time[0] if len(execution_time) > 0 else None)
    
    # Fallback for detailed energy breakdown (for A2A calls from env2)
    if eval_df["cpu_energy"].isna().all() and cpu_energy is not None:
        print(f"[{tool_name}] Using passed cpu_energy: {cpu_energy}")
        eval_df["cpu_energy"] = cpu_energy
    
    if eval_df["gpu_energy"].isna().all() and gpu_energy is not None:
        print(f"[{tool_name}] Using passed gpu_energy: {gpu_energy}")
        eval_df["gpu_energy"] = gpu_energy
    
    if eval_df["ram_energy"].isna().all() and ram_energy is not None:
        print(f"[{tool_name}] Using passed ram_energy: {ram_energy}")
        eval_df["ram_energy"] = ram_energy
    
    if eval_df["emissions_rate"].isna().all() and emissions_rate is not None:
        print(f"[{tool_name}] Using passed emissions_rate: {emissions_rate}")
        eval_df["emissions_rate"] = emissions_rate
    

    # For non-A2A tools: timestamps come from emissions CSV files 
    # For A2A tools (create_visualization, a2a_communication): timestamps come from passed parameter (env2 tracks them)
    
    timestamp_from_emissions = False
    if 'timestamp' in eval_df.columns:
        valid_mask = (
            eval_df["timestamp"].notna() & 
            (eval_df["timestamp"].astype(str).str.strip() != '') &
            (eval_df["timestamp"].astype(str).str.strip() != 'None') &
            (eval_df["timestamp"].astype(str).str.strip().str.lower() != 'nan')
        )
        timestamp_from_emissions = valid_mask.any()
    

    if tool_name in ("create_visualization", "a2a_communication"):
        if timestamp_from_emissions:
            # Non-A2A environment: timestamp already read from emissions CSV
            print(f"[{tool_name}] ✅ Using timestamp from emissions CSV (non-A2A, actual execution time)")
        elif timestamp is not None and str(timestamp).strip() != '' and str(timestamp).strip().lower() not in {"none", "nan", "nat"}:
            # A2A environment: use passed timestamp from env2
            eval_df["timestamp"] = str(timestamp).strip()
            print(f"[{tool_name}] ✅ Using env2 execution timestamp (A2A): {timestamp}")
        else:
            print(f"[{tool_name}] ⚠️  No valid passed timestamp, keeping emissions CSV value if present")
    else:
        # For non-A2A tools: emissions CSV timestamp is the source of truth 
        # Only use passed timestamp as fallback if emissions CSV had no timestamp
        if not timestamp_from_emissions and timestamp is not None and str(timestamp).strip() != '' and str(timestamp).strip().lower() not in {"none", "nan", "nat"}:
            eval_df["timestamp"] = str(timestamp).strip()
            print(f"[{tool_name}] Using passed timestamp as fallback (no emissions CSV timestamp): {timestamp}")
        elif timestamp_from_emissions:
            # Timestamp from emissions CSV is already set 
            print(f"[{tool_name}] ✅ Using timestamp from emissions CSV (actual execution time)")
        else:
            # No timestamp available from either source
            print(f"[{tool_name}] ⚠️  No timestamp available from emissions CSV or passed parameter")
    
    # Set A2A message size columns (for a2a_communication tool)
    if a2a_total_size_bytes is not None:
        eval_df["a2a_request_size_bytes"] = a2a_request_size_bytes
        eval_df["a2a_response_size_bytes"] = a2a_response_size_bytes
        eval_df["a2a_total_size_bytes"] = a2a_total_size_bytes
    else:
        # Initialize as None if not provided
        eval_df["a2a_request_size_bytes"] = None
        eval_df["a2a_response_size_bytes"] = None
        eval_df["a2a_total_size_bytes"] = None
    

    # Added A2A size columns for a2a_communication tool
    cols_order = [
        "tool_name", "id", "id_tool", "timestamp", "execution_time", "score", "label",
        "total_energy", "cpu_energy", "gpu_energy", "ram_energy", "emissions_rate",
        "cpu_utilization", "gpu_utilization",
        "a2a_request_size_bytes", "a2a_response_size_bytes", "a2a_total_size_bytes"
    ]
    
    # Ensure all required columns exist
    for col in cols_order:
        if col not in eval_df.columns:
            print(f"⚠️ Adding missing column: {col}")
            eval_df[col] = None
    
    # Select ONLY the columns i want (this drops everything else)
    eval_df = eval_df[cols_order]
    
    
    try:
        with csv_lock:
            file_exists_before = Path(file_path).exists()
            
            # If file exists, read it first to ensure we have all columns
            if file_exists_before:
                try:
                    existing_df = pd.read_csv(file_path)
                    
                    # Check for unnamed columns (A2A size data without headers)
                    unnamed_cols = [col for col in existing_df.columns if str(col).startswith('Unnamed')]
                    if unnamed_cols:
                        # Try to map the last 3 unnamed columns to A2A size columns
                        if len(unnamed_cols) >= 3:
                            last_unnamed = sorted(unnamed_cols, key=lambda x: int(str(x).replace('Unnamed: ', '')))[-3:]
                            rename_map = {
                                last_unnamed[0]: 'a2a_request_size_bytes',
                                last_unnamed[1]: 'a2a_response_size_bytes',
                                last_unnamed[2]: 'a2a_total_size_bytes'
                            }
                            existing_df = existing_df.rename(columns=rename_map)
                            print(f"[evaluation_logger] ✅ Fixed unnamed A2A columns in existing CSV")
                    
                    # Ensure all expected columns exist in existing CSV
                    for col in cols_order:
                        if col not in existing_df.columns:
                            existing_df[col] = None
                    
                    # Reorder existing columns to match expected order
                    existing_df = existing_df[cols_order]
                    
                   
                    
                    # Combine with new data
                    combined_df = pd.concat([existing_df, eval_df], ignore_index=True)
                except Exception as read_error:
                    print(f"[evaluation_logger] ⚠️  Error reading existing CSV: {read_error}, using new data only")
                    combined_df = eval_df
            else:
                combined_df = eval_df
            
            # Convert timestamp to datetime for proper sorting
            if 'timestamp' in combined_df.columns:
                # Use safe datetime conversion to preserve already-parsed timestamps
                def safe_to_datetime(x):
                    if pd.isna(x) or x is None or str(x).strip() in ('', 'None', 'NaT', 'nan'):
                        return pd.NaT
                    if isinstance(x, pd.Timestamp):
                        return x
                    try:
                        return pd.to_datetime(x)
                    except Exception:
                        return pd.NaT
                
                combined_df['timestamp'] = combined_df['timestamp'].apply(safe_to_datetime)
            
            # Sort by timestamp 
            if 'timestamp' in combined_df.columns and not combined_df['timestamp'].isna().all():
                combined_df = combined_df.sort_values('timestamp', ascending=True, na_position='last')
            else:
                # sort by index if timestamp is not available
                combined_df = combined_df.sort_index()
            
            # Convert timestamp back to string format for CSV
            if 'timestamp' in combined_df.columns:
                def format_timestamp(x):
                    if pd.notna(x) and hasattr(x, 'strftime'):
                        ts_str = x.strftime('%Y-%m-%dT%H:%M:%S.%f')
                        while ts_str.endswith('0') and '.' in ts_str:
                            ts_str = ts_str[:-1]
                        if ts_str.endswith('.'):
                            ts_str = ts_str[:-1]
                        return ts_str
                    elif pd.notna(x):
                        return str(x)
                    else:
                        return ''
                
                combined_df['timestamp'] = combined_df['timestamp'].apply(format_timestamp)
            
            # Write the complete sorted dataframe with full header
            file_path_abs = Path(file_path).absolute()
            print(f"[evaluation_logger] Writing to absolute path: {file_path_abs}")
            combined_df.to_csv(file_path_abs, mode="w", header=True, index=False)
            print(f"✅ Evaluation saved to {file_path_abs} ({len(eval_df)} rows added, {len(combined_df)} total rows, sorted by timestamp)")
            
            # Verify file was written
            if file_path_abs.exists():
                file_size = file_path_abs.stat().st_size
                print(f"[evaluation_logger] ✅ File verified: {file_size} bytes written")
            else:
                print(f"[evaluation_logger] ❌ ERROR: File was not created at {file_path_abs}")
    except Exception as e:
        print(f"❌ Error writing to CSV {file_path}: {e}")
        import traceback
        traceback.print_exc()
    
        try:
            fallback_path = Path("/tmp") / f"tool_evaluations_{tool_name}_error.csv"
            eval_df.to_csv(fallback_path, index=False)
            print(f"[evaluation_logger] Wrote error data to fallback: {fallback_path}")
        except:
            pass


# Background Evaluation Worker 

eval_queue = queue.Queue()

def eval_worker():
    """
    Background worker thread that processes evaluation tasks asynchronously.
    This prevents blocking the main request thread during expensive LLM evaluations.
    """
    while True:
        args = eval_queue.get()
        if args is None:
            break  # Shutdown signal
        
        try:
            
            if len(args) > 12:
                print(f"[eval_worker] DEBUG: args[12] (timestamp position) = {args[12]} (type: {type(args[12])})")
            (
                tool_name,
                eval_func,
                run_id,
                energy,
                tool_ids,
                cpu_util,
                gpu_util,
                exec_time,
                cpu_energy_val,
                gpu_energy_val,
                ram_energy_val,
                emissions_rate_val,
                timestamp_val,
                file_path,
                nodes,
                users,
                a2a_request_size_bytes,
                a2a_response_size_bytes,
                a2a_total_size_bytes,
            ) = args
            print(f"[eval_worker] Picked up {tool_name} from queue (remaining: ~{eval_queue.qsize()})")
            print(f"[eval_worker] DEBUG: timestamp_val after unpacking = {timestamp_val} (type: {type(timestamp_val)})")
            
            
            # create_visualization needs extra time because spans come from a different service (env2)
            import time
            wait_time = 10 if tool_name == "create_visualization" else (5 if tool_name in ["lookup_sales_data", "analyzing_data"] else 3)
            print(f"[Evaluation] Waiting {wait_time}s for Phoenix to index spans for {tool_name}...")
            time.sleep(wait_time)
            
            print(f"[Evaluation] Running {tool_name} evaluation for run_id: {run_id}")
            
            # Execute evaluation function 
            eval_df = eval_func(run_id)
            
            # Show what I got from the evaluation function
            if eval_df is None:
                print(f"[{tool_name}] ⚠️  eval_func returned None - skipping evaluation")
                print(f"[{tool_name}] This usually means Phoenix didn't find any spans for run_id: {run_id}")
            elif eval_df.empty:
                print(f"[{tool_name}] ⚠️  eval_func returned empty DataFrame - skipping evaluation")
                print(f"[{tool_name}] This usually means Phoenix found spans but they didn't match the evaluation criteria")
            else:
                print(f"[{tool_name}] ✅ eval_func returned {len(eval_df)} rows")
            
            if eval_df is not None and not eval_df.empty:
                
                num_expected = len(tool_ids) if isinstance(tool_ids, list) else 1
                if len(eval_df) == 1 and num_expected > 1:
                    print(f"[Evaluation] Found 1 span but {num_expected} executions - replicating evaluation")
                    # Replicate the single evaluation row for each execution ID
                    replicated_rows = []
                    for idx in range(num_expected):
                        row_copy = eval_df.iloc[0].copy()
                        replicated_rows.append(row_copy)
                    eval_df = pd.DataFrame(replicated_rows)
                    eval_df = eval_df.reset_index(drop=True)
                
                print(f"[eval_worker] DEBUG: About to call log_evaluation_to_csv for {tool_name} with timestamp={timestamp_val} (type: {type(timestamp_val)})")
                log_evaluation_to_csv(
                    eval_df,
                    tool_name=tool_name,
                    run_id=run_id,
                    energy=energy,
                    tool_execution_id=tool_ids,
                    cpu_utilization=cpu_util,
                    gpu_utilization=gpu_util,
                    execution_time=exec_time,
                    cpu_energy=cpu_energy_val,
                    gpu_energy=gpu_energy_val,
                    ram_energy=ram_energy_val,
                    emissions_rate=emissions_rate_val,
                    timestamp=timestamp_val,
                    file_path=file_path,
                    nodes=nodes,
                    users=users,
                    a2a_request_size_bytes=a2a_request_size_bytes,
                    a2a_response_size_bytes=a2a_response_size_bytes,
                    a2a_total_size_bytes=a2a_total_size_bytes,
                )
        except Exception as e:
            print(f"[⚠️] Error in eval_worker for {tool_name} ({run_id}): {e}")
            import traceback
            traceback.print_exc()
        
        eval_queue.task_done()

# Start background worker thread 
eval_thread = threading.Thread(target=eval_worker, daemon=True, name="EvalWorker")
eval_thread.start()
print(f"[evaluation_logger] ✅ Started evaluation worker thread: {eval_thread.name} (alive: {eval_thread.is_alive()})")


def queue_evaluation(
    tool_name: str,
    eval_func: callable,
    run_id: str,
    energy: Optional[Union[float, List[float]]] = None,
    tool_execution_ids: Optional[Union[str, List[str]]] = None,
    cpu_utilization: Optional[Union[float, List[float]]] = None,
    gpu_utilization: Optional[Union[float, List[float]]] = None,
    execution_time: Optional[Union[float, List[float]]] = None,
    cpu_energy: Optional[float] = None,
    gpu_energy: Optional[float] = None,
    ram_energy: Optional[float] = None,
    emissions_rate: Optional[float] = None,
    timestamp: Optional[str] = None,
    file_path: Optional[str] = None,
    nodes: Optional[int] = None,
    users: Optional[int] = None,
    a2a_request_size_bytes: Optional[int] = None,
    a2a_response_size_bytes: Optional[int] = None,
    a2a_total_size_bytes: Optional[int] = None,
):
    """
    Queue an evaluation task to be processed asynchronously in the background.
    
    Args:
        tool_name: Name of tool/agent
        eval_func: Evaluation function to call (e.g., sql_eval, analysis_eval)
        run_id: Unique run identifier
        energy: Energy consumption data (kept for backward compatibility, not used)
        tool_execution_ids: Tool execution ID(s) for matching emissions files
        cpu_utilization: CPU utilization data
        gpu_utilization: GPU utilization data
        execution_time: Execution time in seconds (for A2A calls)
        cpu_energy: CPU energy in kWh (for A2A calls)
        gpu_energy: GPU energy in kWh (for A2A calls)
        ram_energy: RAM energy in kWh (for A2A calls)
        emissions_rate: Emissions rate (for A2A calls)
        timestamp: Actual execution timestamp (for A2A calls)
        file_path: Output CSV file path (if None, determined from nodes/users)
        nodes: Number of parallel nodes (for folder organization and emissions folder)
        users: Number of concurrent users (for folder organization)
    """
    
    eval_queue.put((
        tool_name,
        eval_func,
        run_id,
        energy,
        tool_execution_ids,
        cpu_utilization,
        gpu_utilization,
        execution_time,
        cpu_energy,
        gpu_energy,
        ram_energy,
        emissions_rate,
        timestamp,
        file_path,
        nodes,
        users,
        a2a_request_size_bytes,
        a2a_response_size_bytes,
        a2a_total_size_bytes,
    ))
    print(f"[queue_evaluation] ✅ Added {tool_name} to queue (queue size: {eval_queue.qsize()})")
