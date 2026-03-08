import os
import duckdb
import pandas as pd
from typing import Dict, List, Optional
from codecarbon import EmissionsTracker
import uuid
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

# Reuse shared constants/tracing if available
try:
    from utils_copy import TRANSACTION_DATA_FILE_PATH, tracer
except Exception:
    TRANSACTION_DATA_FILE_PATH = 'data/Store_Sales_Price_Elasticity_Promotions_Data.parquet'
    tracer = None

# Import UsageMonitor for CPU/GPU tracking
try:
    from usage_monitor import UsageMonitor
except ImportError:
    UsageMonitor = None


# Torrado's exact SQL_Generation_Prompt
TORRADO_SQL_PROMPT = """ \
"Generate an SQL query based on the prompt. Please just reply with the SQL query and NO MORE, just the query. Really there is no need to create any comment besides the query, that's the only important thing. The prompt is : {prompt}" \
"The available columns are: {columns}. " \
"The table name is: {table_name}. " \
"If you need to use a DATE column with LIKE or pattern matching, first CAST it to VARCHAR like this: CAST(date_column AS VARCHAR) LIKE '%2021-11%' " \
"Return only the SQL query, with no explanations or markdown formatting." \
"" \
"Important: If you filter or compare date columns, always cast them to string using CAST(date_column AS VARCHAR)."\
If your query uses GROUP BY, every column in SELECT must either be in GROUP BY or be wrapped in an aggregate function like SUM(), COUNT(), MAX(), etc.
DO NOT use any column name (like "Store_Number") in the FROM clause. Only use the table name: {table_name}
All FROM or JOIN clauses MUST say: FROM {table_name}

NEVER write CAST(... LIKE ...) inside SELECT. It must be part of a WHERE clause.

If your query uses GROUP BY, every column in SELECT must either:
- Appear in the GROUP BY clause, OR
- Be wrapped in an aggregate function like SUM(), COUNT(), MAX(), AVG(), etc.

WARNING: Do NOT select columns like Store_Number, Product_Class_Code, etc. unless they are in GROUP BY or inside an aggregation.

If your query uses GROUP BY, every column in SELECT must either:
- Appear in the GROUP BY clause, OR
- Be wrapped in an aggregate function like SUM(), COUNT(), MAX(), AVG(), etc.

If you want to keep a non-aggregated column for display (and its exact value is not important), you may use ANY_VALUE(column) — but ONLY in the SELECT clause.

NEVER use ANY_VALUE(...) inside GROUP BY, ORDER BY, or WHERE clauses.
NEVER nest ANY_VALUE inside another aggregation (e.g. SUM(ANY_VALUE(...)) is invalid).
ONLY use ANY_VALUE in the SELECT clause, and only for columns not in GROUP BY.
Also, NEVER use column names as string literals (no quotes).


"""


def _make_llm_sql():
    try:
        from langchain_ollama import ChatOllama
        base = os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_API_BASE") or os.getenv("OLLAMA_BASE_URL", "").replace("/v1", "") or "http://host.docker.internal:11434"
        model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        # ChatOllama uses base_url 
        return ChatOllama(model=model, base_url=base, temperature=0.1, streaming=True)
    except Exception:
        return None


def _clean_sql(text: str) -> str:
    sql = text.strip()
    sql = sql.replace("```sql", "").replace("```", "").replace("`", "").strip()
    return sql


def _validate_sql(sql: str, table_name: str) -> str:
    sql_up = sql.strip().lower()
    if not sql_up.startswith("select"):
        raise ValueError("Only SELECT statements are allowed")
    if table_name.lower() not in sql_up:
        #  force FROM table if user omitted
        if " from " not in sql_up:
            raise ValueError("SQL must reference the sales table")
    
    forbidden = [";", " drop ", " delete ", " update ", " insert ", " create ", " alter "]
    for token in forbidden:
        if token in sql_up and not sql_up.startswith("select"):
            raise ValueError("Forbidden SQL token detected")
    return sql


def _extract_date_range(prompt: str):
    """Extract date range from prompt using regex. Returns (start_date, end_date) strings or None."""
    import re
    # Look for patterns like "Nov 2021", "November 2021", "2021-11", "Dec 2022" etc.
    month_names = {
        'jan': '01', 'january': '01',
        'feb': '02', 'february': '02',
        'mar': '03', 'march': '03',
        'apr': '04', 'april': '04',
        'may': '05',
        'jun': '06', 'june': '06',
        'jul': '07', 'july': '07',
        'aug': '08', 'august': '08',
        'sep': '09', 'september': '09', 'sept': '09',
        'oct': '10', 'october': '10',
        'nov': '11', 'november': '11',
        'dec': '12', 'december': '12'
    }
    
    prompt_lower = prompt.lower()
    
    # Try to find "Month YYYY" or "Month, YYYY"
    for month_name, month_num in month_names.items():
        pattern = rf'\b{month_name}[\s,]+(\d{{4}})\b'
        match = re.search(pattern, prompt_lower)
        if match:
            year = match.group(1)
            start_date = f"{year}-{month_num}-01"
            # Calculate end date (first day of next month)
            if month_num == '12':
                end_year = str(int(year) + 1)
                end_date = f"{end_year}-01-01"
            else:
                next_month = str(int(month_num) + 1).zfill(2)
                end_date = f"{year}-{next_month}-01"
            return start_date, end_date
    
    # Try to find YYYY-MM or YYYY/MM format
    match = re.search(r'\b(\d{4})[-/](\d{1,2})\b', prompt_lower)
    if match:
        year = match.group(1)
        month = match.group(2).zfill(2)
        start_date = f"{year}-{month}-01"
        if month == '12':
            end_year = str(int(year) + 1)
            end_date = f"{end_year}-01-01"
        else:
            next_month = str(int(month) + 1).zfill(2)
            end_date = f"{year}-{next_month}-01"
        return start_date, end_date
    
    return None


def _canonical_daily_query(table: str, prompt: str = "") -> str:
    """Return the canonical daily aggregation query, with date range extracted from prompt if possible."""
    date_range = _extract_date_range(prompt)
    if date_range:
        start_date, end_date = date_range
    else:
        # In case of no date, fallback to Nov 2021
        start_date, end_date = "2021-11-01", "2021-12-01"
    
    return (
        "SELECT "
        "  CAST(date_trunc('day', Sold_Date) AS DATE) AS day, "
        "  SUM(Total_Sale_Value) AS revenue, "
        "  SUM(Qty_Sold) AS units "
        f"FROM {table} "
        f"WHERE Sold_Date >= DATE '{start_date}' AND Sold_Date < DATE '{end_date}' "
        "GROUP BY 1 "
        "ORDER BY 1"
    )


class SQLAgent:
    def __init__(self, table_name: str = "sales", num_parallel_nodes: int = 1) -> None:
        self.table_name = table_name
        self.llm = _make_llm_sql()
        self.num_parallel_nodes = num_parallel_nodes
        if num_parallel_nodes > 1:
            print(f"[SQLAgent] Parallel query generation enabled: {num_parallel_nodes} nodes")

    def _generate_single_sql_query(self, prompt: str, state: Dict, query_id: str, temperature: float = 0.1) -> Dict:
        
        # Start monitoring for this query
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
            project_name="sql_query_gen",
            experiment_id=query_id,
            measure_power_secs=1,
            log_level="critical",
            output_file=f"emissions_{state.get('run_id', 'unknown')}_{query_id}.csv",
            output_dir=output_dir
        )
        tracker.start()
        
        try:
            columns = state.get("columns", [])
            # Torrado's exact SQL_Generation_Prompt 
            msg = TORRADO_SQL_PROMPT.format(
                prompt=prompt,
                columns=columns,
                table_name=self.table_name
            )
            
            # Create LLM with specific temperature
            from langchain_ollama import ChatOllama
            base = os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_API_BASE") or os.getenv("OLLAMA_BASE_URL", "").replace("/v1", "") or "http://host.docker.internal:11434"
            model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
            local_llm = ChatOllama(model=model, base_url=base, temperature=temperature, streaming=True)
            
            res = local_llm.invoke(msg)
            sql_query = _clean_sql(getattr(res, "content", str(res)))
            
            if not sql_query:
                sql_query = _canonical_daily_query(self.table_name, prompt)
            
            sql_query = _validate_sql(sql_query, self.table_name)
            
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
                "sql_query": sql_query,
                "energy_query": emissions,
                "query_id": query_id,
                "cpu_query": cpu_mean,
                "gpu_query": gpu_mean
            }
        except Exception as e:
            if usage_monitor:
                usage_monitor.stop()
            tracker.stop()
            # Return fallback query
            return {
                "sql_query": _canonical_daily_query(self.table_name, prompt),
                "energy_query": 0.0,
                "query_id": query_id,
                "cpu_query": None,
                "gpu_query": None,
                "error": str(e)
            }

    def _parallel_sql_gen(self, prompt: str, state: Dict) -> List[Dict]:
        # Substates for parallel execution
        temperatures = [0.1] * self.num_parallel_nodes
        substates = []
        for temp in temperatures:
            query_id = str(uuid.uuid4())[:8]
            substate = {
                **state,
                "temperature": temp,
                "query_id": query_id,
                "run_id": state.get("run_id", "unknown")
            }
            substates.append(substate)
        
        # Create subgraph for parallel execution
        class SQLGenState(TypedDict):
            prompt: str
            columns: List[str]
            table_name: str
            temperature: float
            query_id: str
            run_id: str
            sql_query: Optional[str]
            energy_query: Optional[float]
            cpu_query: Optional[float]
            gpu_query: Optional[float]
        
        def generate_query_node(substate: SQLGenState) -> SQLGenState:
            result = self._generate_single_sql_query(
                substate["prompt"],
                substate,
                substate["query_id"],
                substate["temperature"]
            )
            return {
                **substate,
                "sql_query": result["sql_query"],
                "energy_query": result["energy_query"],
                "cpu_query": result["cpu_query"],
                "gpu_query": result["gpu_query"]
            }
        
        subgraph = StateGraph(SQLGenState)
        subgraph.add_node("generate_sql_query", generate_query_node)
        subgraph.set_entry_point("generate_sql_query")
        subgraph.add_edge("generate_sql_query", END)
        compiled_subgraph = subgraph.compile()
        
        # Execute in parallel
        results = list(compiled_subgraph.batch_as_completed(inputs=substates))
        return results

    def run(self, prompt: str, run_id: Optional[str] = None, execution_id: Optional[str] = None) -> Dict:
        # Start monitoring CPU/GPU (for overall execution)
        usage_monitor = UsageMonitor(interval=0.5) if UsageMonitor else None
        if usage_monitor:
            usage_monitor.start()
        
        # Start CodeCarbon emissions tracking (for overall execution)
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
                project_name="sql_agent_v1",
                experiment_id=run_id or "default",
                measure_power_secs=1,
                log_level="critical",
                output_file=f"emissions_{run_id}_{execution_id}.csv",
                output_dir=output_dir
            )
            tracker.start()
        
        try:
            # 1) Load parquet and register duckdb table
            df = pd.read_parquet(TRANSACTION_DATA_FILE_PATH)
            duckdb.sql(f"DROP TABLE IF EXISTS {self.table_name}")
            duckdb.sql(f"CREATE TABLE {self.table_name} AS SELECT * FROM df")
            columns = list(df.columns)
            date_columns = df.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]).columns.tolist()

            # 2) Generate SQL queries (parallel or single)
            sql_queries = []
            query_energies = []
            query_ids = []
            cpu_queries = []
            gpu_queries = []
            
            if self.num_parallel_nodes > 1:
                # Parallel SQL generation 
                print(f"[SQLAgent] Generating {self.num_parallel_nodes} parallel SQL queries...")
                state = {
                    "prompt": prompt,
                    "columns": columns,
                    "table_name": self.table_name,
                    "run_id": run_id or "unknown"
                }
                parallel_results = self._parallel_sql_gen(prompt, state)
                
                for result_tuple in parallel_results:
                    # batch_as_completed returns (state_id, result_dict)
                    if isinstance(result_tuple, tuple) and len(result_tuple) == 2:
                        _, result = result_tuple
                    else:
                        result = result_tuple
                    
                    sql_queries.append(result.get("sql_query", ""))
                    query_energies.append(result.get("energy_query", 0.0))
                    query_ids.append(result.get("query_id", ""))
                    cpu_queries.append(result.get("cpu_query"))
                    gpu_queries.append(result.get("gpu_query"))
                
                # Use first valid query (or merge results if needed)
                sql = sql_queries[0] if sql_queries else _canonical_daily_query(self.table_name, prompt)
            else:
                drafted_sql = None
                if self.llm is not None:
                    # Torrado's exact SQL_Generation_Prompt
                    msg = TORRADO_SQL_PROMPT.format(
                        prompt=prompt,
                        columns=columns,
                        table_name=self.table_name
                    )
                    

                    if tracer is not None:
                        with tracer.start_as_current_span("sql_query_gen", openinference_span_kind="llm") as gen_span:
                            gen_span.set_input(msg)
                            if run_id:
                                gen_span.set_attribute("agentrun_id", run_id)
                                gen_span.set_attribute("sql.run_id", run_id)
                            try:
                                res = self.llm.invoke(msg)
                                drafted_sql = _clean_sql(getattr(res, "content", str(res)))
                                gen_span.set_output(drafted_sql or "")
                            except Exception as e:
                                drafted_sql = None
                                gen_span.set_attribute("error", str(e))
                    else:
                        try:
                            res = self.llm.invoke(msg)
                            drafted_sql = _clean_sql(getattr(res, "content", str(res)))
                        except Exception:
                            drafted_sql = None

                if not drafted_sql:
                    drafted_sql = _canonical_daily_query(self.table_name, prompt)

                sql = _validate_sql(drafted_sql, self.table_name)
                sql_queries = [sql]
                query_ids = [execution_id or str(uuid.uuid4())[:8]]
                query_energies = []
                cpu_queries = []
                gpu_queries = []

            lower_sql = sql.lower()
            bad_dims = any(k in lower_sql for k in ["store_number", "sku_coded", "product_class_code"])
            has_day = "date_trunc('day', sold_date" in lower_sql or " as day" in lower_sql or "cast(" in lower_sql
            if bad_dims or not has_day:
                sql = _canonical_daily_query(self.table_name, prompt)
                sql_queries[0] = sql

            # 3) Execute queries and merge results (if parallel)
            results_data = []
            for sql_query in sql_queries:
                # Cast date columns if needed 
                sql_query = self._cast_date_columns(sql_query, date_columns)
                
                if self.table_name.lower() not in sql_query.lower():
                    continue
                
                try:
                    result = duckdb.sql(sql_query).df()
                    if not result.empty:
                        results_data.append(result.head(50000))  # Limit rows
                except Exception:
                    continue

            # Merge results if multiple queries
            if len(results_data) > 1:
                base_df = results_data[0]
                for other in results_data[1:]:
                    common_cols = base_df.columns.intersection(other.columns)
                    if not common_cols.empty:
                        merge_ok = True
                        for col in common_cols:
                            if base_df[col].nunique() > 1000 or other[col].nunique() > 1000:
                                merge_ok = False
                                break
                        if merge_ok:
                            merged = pd.merge(base_df, other, how="inner", on=list(common_cols))
                            if len(merged) < 5000000:
                                base_df = merged
                result_df = base_df
            elif len(results_data) == 1:
                result_df = results_data[0]
            else:
                # Fallback: execute canonical query
                sql = _canonical_daily_query(self.table_name, prompt)
                result_df = duckdb.sql(sql).df()
            # Normalize datetime columns and replace NaN with None
            df_out = result_df.copy()
            for c in df_out.columns:
                if pd.api.types.is_datetime64_any_dtype(df_out[c]) or pd.api.types.is_datetime64tz_dtype(df_out[c]):
                    df_out[c] = pd.to_datetime(df_out[c]).dt.strftime("%Y-%m-%d")
            df_out = df_out.where(pd.notnull(df_out), None)

            rows: List[List] = df_out.values.tolist()
            columns: List[str] = list(df_out.columns)

            # Trace execution
            if tracer is not None:
                with tracer.start_as_current_span("env1_sqlagent_exec", openinference_span_kind="tool") as span:
                    span.set_input(prompt)
                    span.set_attribute("sql", sql)
                    span.set_attribute("row_count", len(rows))
                    span.set_attribute("num_parallel_nodes", self.num_parallel_nodes)
                    if run_id:
                        span.set_attribute("agentrun_id", run_id)
                        span.set_attribute("sql.run_id", run_id)
                    if execution_id:
                        span.set_attribute("sql.execution_id", execution_id)

            result = {
                "sql": sql,
                "rows": rows,
                "columns": columns,
                "table_name": self.table_name,
                "notes": "Generated and executed locally via DuckDB",
            }
            
            # Add parallel node metrics if applicable
            if self.num_parallel_nodes > 1:
                result["sql_execution_ids"] = query_ids
                result["energy_lookup_sales_data"] = query_energies
                result["cpu_utilization_lookup_sales_data"] = cpu_queries
                result["gpu_utilization_lookup_sales_data"] = gpu_queries
                result["num_parallel_nodes"] = self.num_parallel_nodes
            
            # Add monitoring metrics 
            if usage_monitor:
                usage_monitor.stop()
                stats = usage_monitor.get_stats()
                result["cpu_utilization"] = stats["cpu_mean"]
                result["gpu_utilization"] = stats["gpu_mean"]
            
            # Stop emissions tracking
            if tracker:
                emissions = tracker.stop()
                result["energy_consumed"] = emissions
            
            return result
            
        except Exception as e:
            # Cleanup on error
            if usage_monitor:
                usage_monitor.stop()
            if tracker:
                tracker.stop()
            raise e
    
    def _cast_date_columns(self, query: str, date_columns: list) -> str:
        import re
        for col in date_columns:
            # Support quotes, spaces, and/or table qualifications like table.col
            pattern = rf"(?<!CAST\()(?P<full>([\w\.]*{col}|\"{col}\")\s*~~)"
            query = re.sub(pattern, rf"CAST(\g<full> AS VARCHAR) ~~", query)
            
            pattern_like = rf"(?<!CAST\()(?P<full>([\w\.]*{col}|\"{col}\")\s*LIKE)"
            query = re.sub(pattern_like, rf"CAST(\g<full> AS VARCHAR) LIKE", query)

            # Comparisons: =, >, <
            for op in ["=", ">", "<"]:
                pattern_cmp = rf"(?<!CAST\()(?P<full>([\w\.]*{col}|\"{col}\")\s*\{op})"
                query = re.sub(pattern_cmp, rf"CAST(\g<full> AS VARCHAR) {op}", query)

        return query


