# Cross-Framework AI Agent Orchestration System

A thesis project comparing two approaches for multi-step AI agent workflows:

- **A2A (Agent-to-Agent):** LangGraph orchestrator (Env1) communicates with an OpenAI Agents SDK visualisation service (Env2) via the A2A protocol (JSON-over-HTTP).
- **Non-A2A:** Monolithic OpenAI Agents SDK workflow (Env3) running all tools in a single process.

Experiments measure energy consumption, response time, hardware utilisation, and A2A communication overhead across three workload scenarios (1, 3, and 5 parallel nodes) with one simulated user over 3-hour runs.

---

## Documentation


| Document                                                                                            | Description                                                                      |
| --------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| [00_RUN_GUIDE.md](docs/00_RUN_GUIDE.md)                                                             | **Start here.** Clone, build, run all experiments, generate plots                |
| [01_OVERVIEW.md](docs/01_OVERVIEW.md)                                                               | Project overview: Env1/Env2/Env3 responsibilities, scenario definitions, metrics |
| [02_REPO_STRUCTURE.md](docs/02_REPO_STRUCTURE.md)                                                   | File-level repository map and "Where is X implemented?" index                    |
| [03_COMPONENTS_AND_DATAFLOW.md](docs/03_COMPONENTS_AND_DATAFLOW.md)                                 | Runtime dataflow, call chains, startup paths for all environments                |
| [04_METRICS_AND_LOGGING_SPEC.md](docs/04_METRICS_AND_LOGGING_SPEC.md)                               | Metrics contract: every CSV column defined with source, units, boundaries        |
| [05_EXPERIMENT_PROTOCOL_AND_REPRODUCIBILITY.md](docs/05_EXPERIMENT_PROTOCOL_AND_REPRODUCIBILITY.md) | Experiment assumptions, JMX mapping                                              |
| [06_FIGURE_REPRODUCTION_MAP.md](docs/06_FIGURE_REPRODUCTION_MAP.md)                                 | Map from each thesis figure to its input CSV and reproduction command            |


---

## Quick start

```bash
git clone --branch main --single-branch \
  https://github.com/radauradu/Cross-Framework-AI-Agent-Orchestration-System.git
cd Cross-Framework-AI-Agent-Orchestration-System

# A2A (Env1 + Env2)
sudo docker compose --profile two-env build env1 env2
sudo docker compose --profile two-env up -d

# Non-A2A (Env3 only)
sudo docker compose --profile env3-only build env3
sudo docker compose --profile env3-only up -d
```

See [docs/00_RUN_GUIDE.md](docs/00_RUN_GUIDE.md) for full experiment commands.

---

## Requirements

- Docker Engine >= 24.x with the Compose plugin (`docker compose`)
- NVIDIA GPU with Docker NVIDIA runtime (for GPU energy and utilisation metrics)
- SSH access to the host machine (for JMeter SSHMonSampler host monitoring)

