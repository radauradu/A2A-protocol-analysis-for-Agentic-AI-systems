#!/usr/bin/env python
# coding: utf-8



# # Evaluation of the agent (VisualAgent)

import os
#os.environ['OLLAMA_API_BASE'] = 'http://host.docker.internal:11434'
#os.environ['OLLAMA_BASE_URL'] = 'http://host.docker.internal:11434'
#os.environ['OLLAMA_HOST'] = 'http://host.docker.internal:11434'
#os.environ['LITELLM_BASE_URL'] = 'http://host.docker.internal:11434'
#os.environ['PHOENIX_CLIENT_HEADERS'] = 'api_key=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJBcGlLZXk6NCJ9.gMjwzAckOqbCjFv4kdwvNn0q6XUcf4TxmLXiJYN1MCQ'
#os.environ['PHOENIX_COLLECTOR_ENDPOINT'] = 'https://app.phoenix.arize.com'
#os.environ['OTEL_EXPORTER_OTLP_HEADERS'] = 'api_key=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJBcGlLZXk6NCJ9.gMjwzAckOqbCjFv4kdwvNn0q6XUcf4TxmLXiJYN1MCQ'
#os.environ["PHOENIX_ENDPOINT"] = "https://app.phoenix.arize.com"

from tqdm import tqdm
from phoenix.evals import llm_classify, TOOL_CALLING_PROMPT_TEMPLATE, PromptTemplate, LiteLLMModel
from litellm import completion
from phoenix.trace import SpanEvaluations
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
from opentelemetry import trace

import json
import pandas as pd
# === Phoenix core ===
import phoenix as px
import os
from phoenix.trace.dsl import SpanQuery

# === Evaluaciones automáticas ===
from phoenix.evals import (
    TOOL_CALLING_PROMPT_TEMPLATE,
    llm_classify,
    PromptTemplate,
)
from openinference.instrumentation import suppress_tracing
import nest_asyncio
nest_asyncio.apply()
import pprint
import warnings


warnings.filterwarnings('ignore')

PROJECT_NAME = "evaluating-agent"

# === SQL Generation Evaluation ===
SQL_EVAL_GEN_PROMPT = """
SQL Evaluation Prompt:
-----------------------
You are evaluating the correctness and quality of an SQL query generated in response to an instruction.

You must consider:
1. Whether the SQL query syntactically makes sense and could be executed.
2. Whether it logically addresses the instruction (i.e., filters, aggregates, or selects the right information).
3. Whether it uses appropriate SQL constructs, column names, and structure (e.g., proper GROUP BY usage).
4. Whether the query output would help answer the instruction.
5. Whether the answer/result aligns with what the instruction asked for.

Information provided:
- [Instruction]: {question}
- [Generated SQL]: {query_gen}

Evaluation (respond only with a label):
-----------
- Respond **only** with "correct" or "incorrect".
- "correct" = the query is syntactically valid, logically appropriate, and solves the instruction.
- "incorrect" = any failure in syntax, logic, or usefulness toward the instruction.

Respond only with the label: correct or incorrect.

"""

# === Data Analysis Evaluation ===
CLARITY_LLM_JUDGE_PROMPT = """
In this task, you will be presented with a query and an answer. Your objective is to evaluate the clarity 
of the answer in addressing the query. A clear response is one that is precise, coherent, and directly 
addresses the query without introducing unnecessary complexity or ambiguity. An unclear response is one 
that is vague, disorganized, or difficult to understand, even if it may be factually correct.

[BEGIN DATA]
Query: {query}
Answer: {response}
[END DATA]

Return the output in this format (First, explain your reasoning. Then, on a new line, write):

Label: clear
(or)
Label: unclear
"""

# === Visualization Evaluation ===
VIZ_QUALITY_TEMPLATE = PromptTemplate("""
Evaluate this visualization configuration:
1. Appropriateness of chart type for the data
2. Correct mapping of axes
3. Clarity of visualization goal

Goal: {input}
Data Sample: {reference_data}
Configuration: {output}

Respond with "good" or "poor" and a brief reason.
""")

tools = [
    {
        "name": "lookup_sales_data",
        "description": "Fetch historical data of sales for a product or category."
    },
    {
        "name": "analyzing_data",
        "description": "Does a statistical analysis of the data available, giving an output in form of a summary of trends/patterns found for example."
    },
    {
        "name": "create_visualization",
        "description": "Generates a visualization schema of the data processed according to the user's configuration."
    }
]

# Use same LLM config as env3/evaluations.py (which works)
# LiteLLM uses environment variables for API base, not constructor parameter
# Note: Use OLLAMA_HOST (without /v1 suffix) for LiteLLM with ollama
if not os.getenv("LITELLM_API_BASE") and not os.getenv("OLLAMA_API_BASE"):
    _ollama_base = os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_API_BASE") or "http://ollama:11434"
    os.environ["LITELLM_API_BASE"] = _ollama_base
_ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
model = LiteLLMModel(model=f"ollama_chat/{_ollama_model}", temperature=0.1)
input_state = {"prompt": "Show me sales in Nov 2021"}


#verify traces
def decide_tool_eval(run_id):
    decide_query = (
        SpanQuery()
        .where(f"name == 'tool_choice' and span_kind == 'TOOL' and agentrun_id == '{run_id}'")
    ).select(
        question="input.value",
        tool_call="output.value",
    )
    print(f"[decide_tool_eval] Querying Phoenix for run_id: {run_id}")
    tool_calls_df = px.Client().query_spans(decide_query, project_name=PROJECT_NAME, timeout=None)
    print(f"[decide_tool_eval] Found {len(tool_calls_df)} decide_tool spans")
    tool_calls_df = tool_calls_df.dropna(subset=["tool_call"])
    print(f"[decide_tool_eval] After dropna: {len(tool_calls_df)} spans")
    
    if tool_calls_df.empty:
        print(f"[WARNING] No decide_tool spans found for run_id: {run_id}")
        return pd.DataFrame()

    tool_call_eval = llm_classify(
        dataframe=tool_calls_df,
        template=TOOL_CALLING_PROMPT_TEMPLATE.template[0].template.replace(
            "{tool_definitions}", json.dumps(tools).replace("{", '"').replace("}", '"')),
        rails=['correct', 'incorrect'],
        provide_explanation=True,
        model=model,
        concurrency=1,
    )

    tool_call_eval['score'] = tool_call_eval.apply(lambda x: 1 if x['label']=='correct' else 0, axis=1)

    px.Client().log_evaluations(
        SpanEvaluations(eval_name="Tool Calling Eval", dataframe=tool_call_eval)
    )
    return tool_call_eval



# === SQL Generation Evaluation ===
def sql_eval(run_id):   
    # Try multiple span name patterns and field names - Phoenix structure varies
    # From Phoenix screenshot: span name is "generate_sql_query", SQL is in "sql_query" field
    patterns_to_try = [
        ("name == 'generate_sql_query' and agentrun_id == '{run_id}'", "generate_sql_query with agentrun_id", "sql_query"),
        ("name == 'sql_query_gen' and agentrun_id == '{run_id}'", "sql_query_gen with agentrun_id", "output.value"),
        ("span_kind == 'LLM' and agentrun_id == '{run_id}'", "LLM spans with agentrun_id", "output.value"),
        ("name == 'generate_sql_query'", "generate_sql_query (any run)", "sql_query"),
    ]
    
    sql_df = pd.DataFrame()
    for pattern_template, description, output_field in patterns_to_try:
        pattern = pattern_template.format(run_id=run_id)
        
        try:
            # Query with simple paths - Phoenix can't handle nested dict keys in .select()
            sql_query = (
                SpanQuery()
                .where(pattern)
            ).select(
                input_data="input.value",
                output_data="output.value",
            )
            
            print(f"[sql_eval] Trying pattern: {description} (field: {output_field})")
            sql_df = px.Client().query_spans(sql_query, project_name=PROJECT_NAME, timeout=None)
            print(f"[sql_eval] Found {len(sql_df)} SQL spans")
            
            if not sql_df.empty:
                # Now extract the actual fields from the dicts
                import json
                
                def extract_prompt(input_val):
                    try:
                        if isinstance(input_val, dict):
                            return input_val.get('prompt', str(input_val))
                        elif isinstance(input_val, str) and input_val.startswith('{'):
                            return json.loads(input_val).get('prompt', input_val)
                        return input_val
                    except:
                        return input_val
                
                def extract_sql(output_val):
                    try:
                        if isinstance(output_val, dict):
                            return output_val.get('sql_query', output_val.get('sql', str(output_val)))
                        elif isinstance(output_val, str) and output_val.startswith('{'):
                            data = json.loads(output_val)
                            return data.get('sql_query', data.get('sql', output_val))
                        return output_val
                    except:
                        return output_val
                
                sql_df['question'] = sql_df['input_data'].apply(extract_prompt)
                sql_df['query_gen'] = sql_df['output_data'].apply(extract_sql)
                sql_df = sql_df.drop(columns=['input_data', 'output_data'])
                
                print(f"[sql_eval] ✅ Success with pattern: {description}")
                break
        except Exception as e:
            print(f"[sql_eval] Error with pattern {description}: {e}")
            continue
    
    if sql_df.empty:
        print(f"[WARNING] No SQL queries found for run_id: {run_id} after trying all patterns")
        print(f"[WARNING] This means Phoenix hasn't indexed the spans yet or the span names don't match")
        return pd.DataFrame() 
    else:
        # Debug: Show what data we're evaluating
        print(f"[sql_eval] Sample data being evaluated:")
        print(f"  - question (first 100 chars): {str(sql_df['question'].iloc[0])[:100] if 'question' in sql_df.columns else 'N/A'}")
        print(f"  - query_gen (first 200 chars): {str(sql_df['query_gen'].iloc[0])[:200] if 'query_gen' in sql_df.columns else 'N/A'}")
        
        with suppress_tracing():
            sql_eval = llm_classify(
                dataframe=sql_df,
                template=SQL_EVAL_GEN_PROMPT,
                rails=["correct", "incorrect"],
                model=model,
            )

        sql_eval ['score'] = sql_eval.apply(lambda x: 1 if x['label']=='correct' else 0, axis=1)
        sql_eval.head()
        px.Client().log_evaluations(
            SpanEvaluations(eval_name="SQL Generation Eval", dataframe=sql_eval),
        )
        return sql_eval



# === Data Analysis Evaluation ===
def analysis_eval(run_id):
    analysis_query = (
        SpanQuery()
        .where(f"name == 'data_analysis' and agentrun_id == '{run_id}'")
    ).select(
        query="input.value",
        response="output.value",
    )
    print(f"[analysis_eval] Querying Phoenix for run_id: {run_id}")
    clarity_df = px.Client().query_spans(analysis_query, project_name=PROJECT_NAME, timeout=None)
    print(f"[analysis_eval] Found {len(clarity_df)} analysis spans")
    
    if clarity_df.empty:
        print(f"[WARNING] No analysis spans found for run_id: {run_id}")
        return pd.DataFrame()
    
    # Debug: Show what data we're evaluating
    print(f"[analysis_eval] Sample data being evaluated:")
    print(f"  - query (first 100 chars): {str(clarity_df['query'].iloc[0])[:100] if 'query' in clarity_df.columns else 'N/A'}")
    print(f"  - response (first 200 chars): {str(clarity_df['response'].iloc[0])[:200] if 'response' in clarity_df.columns else 'N/A'}")
    
    # Fix: Extract plain text prompt from JSON query field
    if 'query' in clarity_df.columns:
        import json
        def extract_prompt(query_val):
            try:
                if isinstance(query_val, str) and query_val.startswith('{'):
                    query_dict = json.loads(query_val)
                    return query_dict.get('prompt', query_val)
                elif isinstance(query_val, dict):
                    return query_val.get('prompt', str(query_val))
                return query_val
            except:
                return query_val
        clarity_df['query'] = clarity_df['query'].apply(extract_prompt)
        print(f"[analysis_eval] After extracting prompt: {str(clarity_df['query'].iloc[0])[:100]}")
    
    clarity_df.head()
    with suppress_tracing():
        clarity_eval = llm_classify(
            dataframe=clarity_df,
            template=CLARITY_LLM_JUDGE_PROMPT,
            rails=["clear", "unclear"],
            model=model,
        )
    clarity_eval['score'] = clarity_eval.apply(lambda x: 1 if x['label']=='clear' else 0, axis=1)

    clarity_eval.head()

    px.Client().log_evaluations(
        SpanEvaluations(eval_name="Response Clarity", dataframe=clarity_eval),
    )
    return clarity_eval




# === Visualization Evaluation ===
def visualization_eval(run_id):
    viz_query = (
        SpanQuery()
        .where(f"name == 'gen_visualization' and agentrun_id == '{run_id}'")
    ).select(
        input="input.value",
        generated_code="output.value",
    )
    print(f"[visualization_eval] Querying Phoenix for run_id: {run_id}")
    code_gen_df = px.Client().query_spans(viz_query, project_name=PROJECT_NAME, timeout=None)
    print(f"[visualization_eval] Found {len(code_gen_df)} visualization spans")
    
    if code_gen_df.empty:
        print(f"[WARNING] No visualization spans found for run_id: {run_id}")
        return pd.DataFrame()
    
    code_gen_df.head()

    def code_is_runnable(output:str) -> bool:
        if not output or not isinstance(output, str):
            return False  
        
        output = output.replace("```python", "").replace("```", "").strip()
        
        try:
            exec(output, {}, {})  
            return True
        except Exception:
            return False
        
    code_gen_df['label'] = code_gen_df['generated_code'].apply(code_is_runnable).map({True: "runnable", False: "not_runnable"})
    code_gen_df['score'] = code_gen_df['label'].apply(lambda x: 1 if x=='runnable' else 0)

    px.Client().log_evaluations(
        SpanEvaluations(eval_name="Runnable Code Eval", dataframe=code_gen_df),
    )
    return code_gen_df
