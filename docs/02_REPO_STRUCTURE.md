# Repository Structure

## Directory Tree

```
A2A-protocol-analysis-for-Agentic-AI-systems/
├── a2a/                          # A2A protocol layer
│   ├── __init__.py
│   ├── agent_cards.py            # AgentCard definitions + in-memory registry
│   ├── client.py                 # A2AClient: discovery + HTTP message dispatch
│   ├── executor.py               # A2AAgentExecutor: wraps agents for A2A handling
│   └── protocol.py               # Pydantic models: AgentCard, A2AMessage, A2AResponse
├── agents/                       # Agent implementations
│   ├── __init__.py
│   ├── insight_agent.py          # InsightAgent: parallel LLM data-analysis subgraph
│   ├── plot_agent.py             # PlotAgent: create_visualization tool
│   └── sql_agent.py              # SQLAgent: SQL generation + DuckDB execution
├── utils/
│   ├── __init__.py
│   └── response_formatter.py     # Cleans/formats LLM text output
├── tests/
│   └── jmeter_test/              # JMeter test plans + prompt CSV
│       ├── ReqVM3_a2a_1_1.jmx
│       ├── ReqVM3_a2a_1_3.jmx
│       ├── ReqVM3_a2a_1_5.jmx
│       ├── ReqVM3_env3_1_1.jmx
│       ├── ReqVM3_env3_1_3.jmx
│       ├── ReqVM3_env3_1_5.jmx
│       └── prompts_for_jmeter.csv
├── 3Hour_Radu/                   # A2A experiment results 
│   ├── 1_1/
│   ├── 1_3/
│   └── 1_5/
├── 3Hour_Radu_nonA2A/            # Non-A2A experiment results 
│   ├── 1_1/
│   ├── 1_3/
│   └── 1_5/
├── emissions/                    # Per-run CodeCarbon emissions CSVs 
├── endpoint.py                   # FastAPI app: Env1 (A2A) + Env3 (non-A2A) routes
├── env1_a2a_graph.py             # LangGraph A2A orchestration graph
├── env1_env2_a2a_wrapper.py      # Thin wrapper: calls env1_a2a_graph + handles tracing
├── env2_openai_service.py        # FastAPI app: Env2 PlotAgent service
├── env3_openai_agents.py         # Env3 workflow core
├── env3_openai_agents_wrapper.py # Thin wrapper: calls env3 + handles tracing
├── evaluation_logger.py          # Merges Phoenix evals + energy + utilization → CSV
├── evaluations.py                # Phoenix LLM-as-judge evaluation functions per tool
├── functionalities.py            # LLM utility functions (SQL generation, analysis, etc.)
├── graphs.py                     # LangGraph non-A2A graph 
├── process_jmeter_results.py     # CLI: reads tool_evaluations CSV → generates plots
├── prompts_for_jmeter.csv        # 12 test prompts (root-level copy)
├── usage_monitor.py              # UsageMonitor: background CPU/GPU polling thread
├── utilization_avg.py            # Post-hoc utilization averaging helper
├── utils_copy.py                 # Phoenix tracing setup + run_graph_with_tracing()
├── bounds.py                     # Bounds/limit helper utilities
├── phoenix_shim.py               # Compatibility shim for Arize Phoenix imports
├── plottingcomparisons.py        # Cross-scenario comparison plot generation
├── plottingstd.py                # Standard deviation plot generation
├── summaries.py                  # Summarisation helpers for analysis output
├── prueba.py                     
├── run_jmeter_with_processing.sh # Shell helper: run JMeter + trigger post-processing
├── test_processing.sh            # Shell test script for process_jmeter_results.py
├── Dockerfile                    # Single Dockerfile for Env1, Env2, and Env3 images
├── docker-compose.yml            # Multi-service orchestration (profiles: two-env, env3-only)
└── requirements.txt              # Python dependencies
```

---

## Per-folder explanation

### `a2a/`

Implements the A2A (Agent-to-Agent) protocol layer. Agents announce capabilities via `AgentCard` objects. The `A2AClient` discovers agents either from the local in-memory registry or by fetching `/.well-known/agent-card.json`, then dispatches messages as JSON-over-HTTP `POST` requests.

### `agents/`

Self-contained agent modules. Each agent exposes a `run()` method and is responsible for its own LLM calls, CodeCarbon tracking, and `UsageMonitor` lifecycle. Agents are used both directly (Env3, local Env1 execution) and wrapped via `a2a/executor.py` for A2A dispatch.

### `utils/`

Stateless helper code shared across agents and graphs.

### `tests/jmeter_test/`

Apache JMeter test plans (`.jmx`) and the prompt CSV. The JMX files drive load generation against the running service and embed SSHMonSampler configuration for host-level metrics.

### `3Hour_Radu/` and `3Hour_Radu_nonA2A/`

Runtime output directories mounted by Docker volumes. Each scenario subfolder (`1_1/`, `1_3/`, `1_5/`) collects the `tool_evaluations_{N}.csv` that is the primary analysis input.

---

## Important file details

| File                            | Purpose                                                                                              | Executed by                                                          |
| ------------------------------- | ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `endpoint.py`                   | FastAPI app: routes `/env1-then-env2-a2a` (A2A) and `/env3-openai-agents` (non-A2A)                  | `uvicorn endpoint:app` (via Docker)                                  |
| `env1_a2a_graph.py`             | LangGraph state machine: orchestrates SQL → Analysis → A2A Visualization                             | Called by `env1_env2_a2a_wrapper.py`                                 |
| `env1_env2_a2a_wrapper.py`      | Adds Phoenix span around the A2A graph run                                                           | Called by `endpoint.py`                                              |
| `env2_openai_service.py`        | FastAPI app: `/agent/plot/a2a` endpoint; runs PlotAgent via OpenAI Agents SDK `Runner`               | `uvicorn env2_openai_service:app` (via Docker)                       |
| `env3_openai_agents.py`         | Monolithic non-A2A workflow: SQL + Analysis + Visualization in one process                           | Called by `env3_openai_agents_wrapper.py`                            |
| `env3_openai_agents_wrapper.py` | Adds Phoenix span around the Env3 run                                                                | Called by `endpoint.py`                                              |
| `evaluation_logger.py`          | Thread-safe CSV logger: merges Phoenix evaluation, CodeCarbon emissions, utilization                 | Background worker thread; called by graph nodes                      |
| `evaluations.py`                | Phoenix LLM-as-judge evaluation functions for SQL, analysis, and visualization                       | Called by `evaluation_logger.py` via `queue_evaluation()`            |
| `usage_monitor.py`              | Background thread polling `psutil.cpu_percent()` + `nvidia-smi` every 0.5 s                          | Started/stopped around each tool call                                |
| `a2a/client.py`                 | Discovers agents and sends A2A HTTP messages; measures payload sizes and round-trip time             | Called by `env1_a2a_graph.py`                                        |
| `a2a/agent_cards.py`            | Defines `AgentCard` objects for SQL, Insight, and Plot agents; holds the `AGENT_CARDS` registry dict | Imported at startup                                                  |
| `process_jmeter_results.py`     | CLI post-processor: reads `tool_evaluations_{N}.csv`, computes mean/STD per tool, writes PNG plots   | `python process_jmeter_results.py --csv ... --users ... --nodes ...` |
| `docker-compose.yml`            | Defines all services and their profiles                                                              | `docker compose --profile <name> up`                                 |
| `Dockerfile`                    | Single multi-purpose image for Env1, Env2, Env3                                                      | `docker compose build`                                               |

---

## "Where is X implemented?" index


| Component                                  | File                                                                                           | Function / Class                                              |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| **Orchestrator / tool decision**           | `env1_a2a_graph.py`                                                                            | `orchestrator_node()`                                         |
| **LangGraph state machine**                | `env1_a2a_graph.py`                                                                            | `run_env1_a2a()`                                              |
| **SQLAgent**                               | `agents/sql_agent.py`                                                                          | `SQLAgent.run()`                                              |
| **InsightAgent**                           | `agents/insight_agent.py`                                                                      | `InsightAgent.run()`                                          |
| **PlotAgent**                              | `agents/plot_agent.py`                                                                         | `PlotAgent`, `create_visualization()`                         |
| **create_visualization tool**              | `agents/plot_agent.py`                                                                         | `create_visualization()` function                             |
| **Env2 Runner loop**                       | `env2_openai_service.py`                                                                       | `run_plot_agent()` → `Runner.run()`                           |
| **A2A client (send_message)**              | `a2a/client.py`                                                                                | `A2AClient.send_message()`                                    |
| **A2A client (discovery)**                 | `a2a/client.py`                                                                                | `A2AClient.discover_agent()`                                  |
| **AgentCard registry**                     | `a2a/agent_cards.py`                                                                           | `AGENT_CARDS` dict                                            |
| **AgentCard definitions**                  | `a2a/agent_cards.py`                                                                           | `SQL_AGENT_CARD`, `INSIGHT_AGENT_CARD`, `PLOT_AGENT_CARD`     |
| **Agent Card endpoint (well-known)**       | `endpoint.py`                                                                                  | `GET /.well-known/agent-card.json`                            |
| **Agent Card registration (HTTP)**         | `endpoint.py`                                                                                  | `POST /register/{agent_slug}`                                 |
| **In-process registration (Env1 startup)** | `endpoint.py`                                                                                  | `register_local_agents()`                                     |
| **Env2 startup registration**              | `env2_openai_service.py`                                                                       | `register_plot_agent()`                                       |
| **CodeCarbon integration**                 | `agents/sql_agent.py`, `agents/insight_agent.py`, `env3_openai_agents.py`, `env1_a2a_graph.py` | `EmissionsTracker` start/stop around each tool                |
| **Utilization sampling**                   | `usage_monitor.py`                                                                             | `UsageMonitor` class                                          |
| **A2A bytes computation**                  | `a2a/client.py`                                                                                | `send_message()`: `request_size_bytes`, `response_size_bytes` |
| **A2A time measurement**                   | `a2a/client.py`                                                                                | `send_message()`: `a2a_start_time` / `a2a_network_time`       |
| **CSV logging**                            | `evaluation_logger.py`                                                                         | `log_evaluation_to_csv()`, `queue_evaluation()`               |
| **Phoenix tracing setup**                  | `utils_copy.py`                                                                                | `tracer` object, `run_graph_with_tracing()`                   |
| **JMeter test plans**                      | `tests/jmeter_test/`                                                                           | `ReqVM3_a2a_*.jmx`, `ReqVM3_env3_*.jmx`                       |
| **Prompt CSV**                             | `tests/jmeter_test/prompts_for_jmeter.csv`                                                     | Read by JMeter `CSVDataSet` config element                    |
| **Plot generation**                        | `process_jmeter_results.py`                                                                    | `main()` CLI                                                  |
| **Non-A2A workflow**                       | `env3_openai_agents.py`                                                                        | `run_env3_openai_agents()`                                    |


