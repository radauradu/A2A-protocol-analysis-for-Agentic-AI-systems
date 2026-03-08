# Overview

## What this project does

This repository implements and benchmarks an A2A protocol for Agentic AI systems. It compares two architectural approaches for a multi-step data-analysis workflow:

- **A2A (Agent-to-Agent)** — a LangGraph-based orchestrator in Environment 1 delegates data visualisation to an OpenAI Agents SDK service in Environment 2 via the A2A protocol (JSON-over-HTTP). This is a cross-framework, cross-process setup.
- **Non-A2A** — the entire workflow, including visualisation, runs inside a single process in Environment 3 which is an implementation of the OpenAI Agents SDK.

The goal is to measure whether introducing the A2A communication layer adds meaningful overhead in energy consumption, response time, and hardware utilisation compared to the monolithic non-A2A design.

---

## Environments


| Environment | Framework                  | Role                                                                                                                                        |
| ----------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **Env1**    | LangGraph (Python)         | Orchestrator: receives user requests, decides tool order, runs SQL and analysis subgraphs in parallel, calls Env2 for visualisation via A2A |
| **Env2**    | OpenAI Agents SDK (Python) | Visualisation service: receives an A2A message from Env1, runs the PlotAgent with `create_visualization`, returns generated chart code      |
| **Env3**    | OpenAI Agents SDK (Python) | Monolithic non-A2A workflow: runs all tools (SQL, analysis, visualisation) in a single process                                              |


In the A2A profile, Env1 and Env2 run as separate Docker containers on the same Docker network. In the non-A2A profile, only Env3 runs.

---

## Scenarios

Each scenario is defined by the number of **parallel tool instances** (nodes):


| Scenario ID | Nodes | Users | Runs | Duration |
| ----------- | ----- | ----- | ---- | -------- |
| `1_1`       | 1     | 1     | 3    | ~3 hours |
| `1_3`       | 3     | 1     | 3    | ~3 hours |
| `1_5`       | 5     | 1     | 3    | ~3 hours |


- **Nodes** = number of parallel LLM calls issued simultaneously within the SQL and analysis subgraphs (controls workload intensity).
- **Users** = JMeter thread count (always 1 in these experiments).
- **Runs** = number of independent 1-hour repetitions per scenario (for statistical averaging).

---

## Metrics collected


| Metric                               | Scope                           | Source                                                                                                                   |
| ------------------------------------ | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Service time per tool                | Per tool invocation             | `tool_evaluations_{N}.csv`, computed in `evaluation_logger.py`                                                           |
| Energy consumption (CPU / GPU / RAM) | Per tool invocation             | CodeCarbon `EmissionsTracker`, logged by `evaluation_logger.py`                                                          |
| CPU utilisation (mean)               | Per tool invocation             | `UsageMonitor` (`psutil`) in `usage_monitor.py`                                                                          |
| GPU utilisation (mean)               | Per tool invocation             | `UsageMonitor` (`nvidia-smi`) in `usage_monitor.py`                                                                      |
| A2A request size (bytes)             | Per `create_visualization` call | `a2a/client.py`, `send_message()`                                                                                        |
| A2A response size (bytes)            | Per `create_visualization` call | `a2a/client.py`, `send_message()`                                                                                        |
| A2A round-trip time (seconds)        | Per `create_visualization` call | `a2a/client.py`, `send_message()`                                                                                        |
| Agent Card registration size         | Once at Env2 startup            | Logged to stdout; ~1,396 bytes for the Plot Agent card (HTTP); SQL and Insight are in-process (0 bytes over the network) |
| JMeter response time                 | Per HTTP request                | JMeter `results{scenario}.csv`                                                                                           |
| Host CPU / GPU / memory utilisation  | Over time                       | JMeter SSHMonSampler → `UtilizationSSHMon.csv`                                                                           |


See `[04_METRICS_AND_LOGGING_SPEC.md](04_METRICS_AND_LOGGING_SPEC.md)` for the full metrics contract table.

---

## Quick start

See `[00_RUN_GUIDE.md](00_RUN_GUIDE.md)` for complete step-by-step instructions to clone, build, run experiments, and generate plots.