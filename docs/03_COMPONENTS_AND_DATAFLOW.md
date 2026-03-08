# Components and Dataflow

## A2A Workflow — Env1 → Env2 → Env1

### High-level call flow

```
HTTP POST /env1-then-env2-a2a
  └─ endpoint.py :: env1_then_env2_a2a()
       └─ env1_env2_a2a_wrapper.py :: run_env1_then_env2_a2a()
            └─ env1_a2a_graph.py :: run_env1_a2a()
                 ├─ orchestrator_node()          ← LLM decides next tool
                 ├─ sql_node()
                 │    └─ agents/sql_agent.py :: SQLAgent.run()
                 │         ├─ CodeCarbon EmissionsTracker (start)
                 │         ├─ UsageMonitor (start)
                 │         ├─ [parallel] LLM calls → SQL generation → DuckDB execution
                 │         ├─ UsageMonitor (stop) → cpu_mean, gpu_mean
                 │         └─ CodeCarbon EmissionsTracker (stop) → emissions_*.csv
                 ├─ analysis_node()
                 │    └─ agents/insight_agent.py :: InsightAgent.run()
                 │         ├─ CodeCarbon EmissionsTracker (start)
                 │         ├─ UsageMonitor (start)
                 │         ├─ [parallel] LLM calls → analysis summaries → fusion call
                 │         ├─ UsageMonitor (stop)
                 │         └─ CodeCarbon (stop) → emissions_*.csv
                 └─ visualization_node()
                      └─ a2a/client.py :: A2AClient.send_message("plot", "create_visualization", ...)
                           ├─ discover_agent("plot")
                           │    └─ AGENT_CARDS["plot"]  ← populated at Env2 startup
                           ├─ Serialize A2AMessage → measure request_size_bytes
                           ├─ HTTP POST http://env2:8001/agent/plot/a2a 
                           │    └─ env2_openai_service.py :: plot_a2a()
                           │         ├─ Deserialize A2AMessage
                           │         └─ run_plot_agent()
                           │              ├─ CodeCarbon (start in Env2)
                           │              ├─ UsageMonitor (start in Env2)
                           │              ├─ Runner.run(PlotAgent, ...)
                           │              │    ├─ LLM call 1: chart config (type, axes, title)
                           │              │    └─ LLM call 2: visualization code generation
                           │              ├─ UsageMonitor (stop in Env2)
                           │              └─ CodeCarbon (stop in Env2) → A2AResponse
                           ├─ Deserialize A2AResponse → measure response_size_bytes
                           ├─ Calculate a2a_network_time_seconds
                          
```

### State propagation

The LangGraph state is a `TypedDict` (`AgentState`) that accumulates results across nodes. Key fields:


| Field                | Set by                         | Consumed by                            |
| -------------------- | ------------------------------ | -------------------------------------- |
| `prompt`             | Input                          | All nodes                              |
| `data`               | `sql_node`                     | `analysis_node`, `visualization_node`  |
| `analysis`           | `analysis_node`                | `visualization_node`, final answer     |
| `visualization_code` | `visualization_node` (via A2A) | Final answer                           |
| `used_tools`         | Each node                      | `orchestrator_node` (prevents repeats) |
| `answer`             | Accumulated                    | Returned to caller                     |
| `a2a_*` metrics      | `visualization_node`           | `evaluation_logger`                    |


### Orchestrator decision logic

`orchestrator_node()` in `env1_a2a_graph.py` issues an LLM call with the current state and a prompt that instructs it to choose one of: `lookup_sales_data`, `analyzing_data`, `create_visualization`, or `end`. The orchestrator is invoked once at the start and once after each tool completes, forming a loop. Tool history is tracked in `used_tools` to avoid infinite repetition.

---

## Non-A2A Workflow — Env3

```
HTTP POST /env3-openai-agents
  └─ endpoint.py :: env3_openai_agents()
       └─ env3_openai_agents_wrapper.py :: run_env3_openai_agents_with_tracking()
            └─ env3_openai_agents.py :: run_env3_openai_agents()
                 ├─ OpenAI Agents SDK: Agent + Runner
                 ├─ lookup_sales_data tool
                 │    ├─ CodeCarbon (start)
                 │    ├─ UsageMonitor (start)
                 │    ├─ [parallel, nodes copies] LLM SQL generation + DuckDB execution
                 │    ├─ UsageMonitor (stop)
                 │    └─ CodeCarbon (stop)
                 ├─ analyzing_data tool
                 │    ├─ (same lifecycle as above)
                 │    └─ LLM parallel analysis + fusion
                 └─ create_visualization tool
                      ├─ CodeCarbon (start)
                      ├─ UsageMonitor (start)
                      ├─ LLM call 1: chart config
                      ├─ LLM call 2: chart code generation
                      ├─ UsageMonitor (stop)
                      └─ CodeCarbon (stop)
```

In Env3, all three tools run inside the same Python process and the same Docker container (`env3`). 

---

## Startup paths

### Env1 startup

1. `uvicorn endpoint:app --host 0.0.0.0 --port 8000` (started by Docker)
2. FastAPI initialises; `@app.on_event("startup")` triggers `register_local_agents()`
3. `register_local_agents()` in `endpoint.py`:
  - Imports `SQL_AGENT_CARD`, `INSIGHT_AGENT_CARD` from `a2a/agent_cards.py`
  - Stores them in `AGENT_CARDS["sql"]` and `AGENT_CARDS["insight"]`
  - Logs equivalent byte sizes to stdout (no HTTP involved)
4. `AGENT_CARDS` is now `{"sql": ..., "insight": ...}` — `"plot"` is missing until Env2 registers

### Env2 startup

1. `uvicorn env2_openai_service:app --host 0.0.0.0 --port 8001` (started by Docker)
2. FastAPI initialises; `@app.on_event("startup")` triggers `register_plot_agent()`
3. `register_plot_agent()` in `env2_openai_service.py`:
  - Imports `PLOT_AGENT_CARD` from `a2a/agent_cards.py`
  - Serialises it: `payload = json.dumps(PLOT_AGENT_CARD.dict()).encode("utf-8")` → ~1,396 bytes
  - Logs `bytes_sent`
  - POSTs to `{A2A_BASE_URL}/register/plot` (= `http://env1:8000/register/plot`) 
4. `endpoint.py` handles `POST /register/plot`:
  - Deserialises the body, validates it as an `AgentCard`
  - Stores it in `AGENT_CARDS["plot"]`
  - Returns `{"status": "registered", "bytes_received": ...}`
5. `AGENT_CARDS` in Env1 now contains all three agents

### Env3 startup

1. `uvicorn endpoint:app --host 0.0.0.0 --port 8000` (started by Docker with `env3-only` profile)
2. The same `endpoint.py` is used; `register_local_agents()` runs but is not meaningful for Env3 (no A2A calls are made from `env3-openai-agents` route)
3. All tools run in-process; no agent card lookup is performed

---

## Agent Card Registry flow (detailed)

```
                         docker network
 ┌─────────────────────────────────┐   ┌──────────────────────┐
 │  Env1 (env1 container)          │   │  Env2 (env2 container)│
 │                                 │   │                       │
 │  AGENT_CARDS = {}  (import)     │   │  startup → serialize  │
 │                                 │   │  PLOT_AGENT_CARD      │
 │  startup:                       │   │  (~1,396 bytes)       │
 │    AGENT_CARDS["sql"]   = ...   │   │        │              │
 │    AGENT_CARDS["insight"]= ...  │   │        │ HTTP POST    │
 │                                 │◄──┼────────┘              │
 │  POST /register/plot            │   │  /register/plot        │
 │    → AGENT_CARDS["plot"] = ...  │   │                       │
 └─────────────────────────────────┘   └──────────────────────┘

 Later, during A2A call:
   A2AClient.discover_agent("plot")
     → AGENT_CARDS["plot"].endpoints.a2a
     = "http://env2:8001/agent/plot/a2a"
   → HTTP POST to Env2
```

The `A2AClient.discover_agent()` method first checks `AGENT_CARDS`. All three agents are registered in-memory by the time the first request arrives.

---



