# Run Guide

Complete instructions to clone, build, run all experiment scenarios, and generate thesis plots.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Clone and Setup](#2-clone-and-setup)
3. [Docker Profiles Explained](#3-docker-profiles-explained)
4. [Rebuilding After Code Changes](#4-rebuilding-after-code-changes)
5. [Run Non-A2A Experiments (Env3 only)](#5-run-non-a2a-experiments-env3-only)
6. [Run A2A Experiments (Env1 + Env2)](#6-run-a2a-experiments-env1--env2)
7. [Where Results Are Saved](#7-where-results-are-saved)
8. [Generate Plots (Post-processing)](#8-generate-plots-post-processing)
9. [Stopping and Cleaning Up](#9-stopping-and-cleaning-up)

---

## 1. Prerequisites


| Requirement            | Notes                                                                              |
| ---------------------- | ---------------------------------------------------------------------------------- |
| Git                    | Any recent version                                                                 |
| Docker Engine          | >= 24.x                                                                            |
| Docker Compose plugin  | `docker compose`                                                                   |
| NVIDIA Docker runtime  | Required for GPU passthrough to containers (already configured on the test server) |
| Network access to host | SSH access to `10.79.23.173:22` for JMeter SSHMonSampler metrics                   |


---

## 2. Clone and Setup

```bash
git clone --branch main --single-branch \
  https://github.com/radauradu/Cross-Framework-AI-Agent-Orchestration-System.git

cd Cross-Framework-AI-Agent-Orchestration-System
```

The next commands assume you are in the repository root.

---

## 3. Docker Profiles Explained

The `docker-compose.yml` defines three compose profiles. Only the services under the requested profile are started.


| Profile     | Services started                              | Use for                                           |
| ----------- | --------------------------------------------- | ------------------------------------------------- |
| `env3-only` | `phoenix`, `ollama`, `env3`, `jmeter`         | Non-A2A experiments (Env3 OpenAI Agents SDK only) |
| `two-env`   | `phoenix`, `ollama`, `env1`, `env2`, `jmeter` | A2A experiments                                   |
| `default`   | `phoenix`, `ollama`                           | Standalone observability stack only               |


Service port assignments:


| Service           | Port  |
| ----------------- | ----- |
| `env3` / `env1`   | 8000  |
| `env2`            | 8001  |
| `phoenix` (Arize) | 6006  |
| `ollama`          | 11434 |


---

## 4. Rebuilding After Code Changes

Every time you change Python source files, you must rebuild the affected service image before running experiments.

```bash
# Non-A2A: rebuild env3
sudo docker compose --profile env3-only build env3

# A2A: rebuild env1 and env2
sudo docker compose --profile two-env build env1 env2
```

---

## 5. Run Non-A2A Experiments (Env3 only)

### 5.1 Start the stack

```bash
sudo docker compose --profile env3-only build env3
sudo docker compose --profile env3-only up -d
```

### 5.2 SSH monitoring parameters

The JMeter `SSHMonSampler` plugin collects CPU, memory, and GPU metrics from the host machine over SSH during the test. Replace the placeholders below with actual values before running.


| Parameter    | Flag             | Description                                   |
| ------------ | ---------------- | --------------------------------------------- |
| Host IP      | `-Jssh.host`     | IP address of the host machine running Docker |
| SSH port     | `-Jssh.port`     | Usually `22`                                  |
| SSH username | `-Jssh.user`     | Username on the host machine                  |
| SSH password | `-Jssh.password` | Password for the SSH user                     |


> **Security note — safer alternative using environment variables:**  
> Passing the SSH password directly on the command line is insecure. Use an environment variable instead:
>
> ```bash
> export SSH_PASS="your_password_here"
> # Then replace -Jssh.password=********** with -Jssh.password=$SSH_PASS
> ```
>
> The original commands below use the inline form for reference; substitute `$SSH_PASS` in production.

### 5.3 Scenario 1_1 — 1 user, 1 node

```bash
sudo docker compose --profile env3-only run --rm \
  --entrypoint sh jmeter -c \
  "cp /plugins/*.jar /opt/apache-jmeter-5.5/lib/ext/ 2>/dev/null || true && \
   exec jmeter -n \
     -t /tests/ReqVM3_env3_1_1.jmx \
     -Jtarget.host=env3 \
     -Jresults.dir=/results_non_a2a/1_1 \
     -Jcsv.path=/tests/prompts_for_jmeter.csv \
     -Jssh.host=10.79.23.173 \
     -Jssh.port=22 \
     -Jssh.user=YOUR_SSH_USER \
     -Jssh.password=YOUR_SSH_PASSWORD \
     -l /results_non_a2a/1_1/results1_1.csv"
```

### 5.4 Scenario 1_3 — 1 user, 3 nodes

```bash
sudo docker compose --profile env3-only run --rm \
  --entrypoint sh jmeter -c \
  "cp /plugins/*.jar /opt/apache-jmeter-5.5/lib/ext/ 2>/dev/null || true && \
   exec jmeter -n \
     -t /tests/ReqVM3_env3_1_3.jmx \
     -Jtarget.host=env3 \
     -Jresults.dir=/results_non_a2a/1_3 \
     -Jcsv.path=/tests/prompts_for_jmeter.csv \
     -Jssh.host=10.79.23.173 \
     -Jssh.port=22 \
     -Jssh.user=YOUR_SSH_USER \
     -Jssh.password=YOUR_SSH_PASSWORD \
     -l /results_non_a2a/1_3/results1_3.csv"
```

### 5.5 Scenario 1_5 — 1 user, 5 nodes

```bash
sudo docker compose --profile env3-only run --rm \
  --entrypoint sh jmeter -c \
  "cp /plugins/*.jar /opt/apache-jmeter-5.5/lib/ext/ 2>/dev/null || true && \
   exec jmeter -n \
     -t /tests/ReqVM3_env3_1_5.jmx \
     -Jtarget.host=env3 \
     -Jresults.dir=/results_non_a2a/1_5 \
     -Jcsv.path=/tests/prompts_for_jmeter.csv \
     -Jssh.host=10.79.23.173 \
     -Jssh.port=22 \
     -Jssh.user=YOUR_SSH_USER \
     -Jssh.password=YOUR_SSH_PASSWORD \
     -l /results_non_a2a/1_5/results1_5.csv"
```

---

## 6. Run A2A Experiments (Env1 + Env2)

### 6.1 Start the stack

```bash
sudo docker compose --profile two-env build env1 env2
sudo docker compose --profile two-env up -d
```

### 6.2 Scenario 1_1 — 1 user, 1 node

```bash
sudo docker compose --profile two-env run --rm \
  --entrypoint sh jmeter -c \
  "cp /plugins/*.jar /opt/apache-jmeter-5.5/lib/ext/ 2>/dev/null || true && \
   exec jmeter -n \
     -t /tests/ReqVM3_a2a_1_1.jmx \
     -Jtarget.host=env1 \
     -Jresults.dir=/results_a2a/1_1 \
     -Jcsv.path=/tests/prompts_for_jmeter.csv \
     -Jssh.host=10.79.23.173 \
     -Jssh.port=22 \
     -Jssh.user=YOUR_SSH_USER \
     -Jssh.password=YOUR_SSH_PASSWORD \
     -l /results_a2a/1_1/results1_1.csv"
```

### 6.3 Scenario 1_3 — 1 user, 3 nodes

```bash
sudo docker compose --profile two-env run --rm \
  --entrypoint sh jmeter -c \
  "cp /plugins/*.jar /opt/apache-jmeter-5.5/lib/ext/ 2>/dev/null || true && \
   exec jmeter -n \
     -t /tests/ReqVM3_a2a_1_3.jmx \
     -Jtarget.host=env1 \
     -Jresults.dir=/results_a2a/1_3 \
     -Jcsv.path=/tests/prompts_for_jmeter.csv \
     -Jssh.host=10.79.23.173 \
     -Jssh.port=22 \
     -Jssh.user=YOUR_SSH_USER \
     -Jssh.password=YOUR_SSH_PASSWORD \
     -l /results_a2a/1_3/results1_3.csv"
```

### 6.4 Scenario 1_5 — 1 user, 5 nodes

```bash
sudo docker compose --profile two-env run --rm \
  --entrypoint sh jmeter -c \
  "cp /plugins/*.jar /opt/apache-jmeter-5.5/lib/ext/ 2>/dev/null || true && \
   exec jmeter -n \
     -t /tests/ReqVM3_a2a_1_5.jmx \
     -Jtarget.host=env1 \
     -Jresults.dir=/results_a2a/1_5 \
     -Jcsv.path=/tests/prompts_for_jmeter.csv \
     -Jssh.host=10.79.23.173 \
     -Jssh.port=22 \
     -Jssh.user=YOUR_SSH_USER \
     -Jssh.password=YOUR_SSH_PASSWORD \
     -l /results_a2a/1_5/results1_5.csv"
```

---

## 7. Where Results Are Saved

Results are written to host-mounted volumes.

### Non-A2A (Env3)


| Scenario | Output directory on host | Key file                 |
| -------- | ------------------------ | ------------------------ |
| 1_1      | `3Hour_Radu_nonA2A/1_1/` | `tool_evaluations_1.csv` |
| 1_3      | `3Hour_Radu_nonA2A/1_3/` | `tool_evaluations_3.csv` |
| 1_5      | `3Hour_Radu_nonA2A/1_5/` | `tool_evaluations_5.csv` |


JMeter result CSV: `3Hour_Radu_nonA2A/{scenario}/results{scenario}.csv`

### A2A (Env1 + Env2)


| Scenario | Output directory on host | Key file                 |
| -------- | ------------------------ | ------------------------ |
| 1_1      | `3Hour_Radu/1_1/`        | `tool_evaluations_1.csv` |
| 1_3      | `3Hour_Radu/1_3/`        | `tool_evaluations_3.csv` |
| 1_5      | `3Hour_Radu/1_5/`        | `tool_evaluations_5.csv` |


JMeter result CSV: `3Hour_Radu/{scenario}/results{scenario}.csv`

### Folder contents after a completed run

Each scenario subfolder contains:


| File                         | Description                                                     |
| ---------------------------- | --------------------------------------------------------------- |
| `tool_evaluations_{N}.csv`   | Per-tool metrics (energy, utilization, service time, A2A bytes) |
| `results{scenario}.csv`      | Raw JMeter request log                                          |
| `ResultsTable.csv`           | JMeter summary table                                            |
| `RespTime.csv`               | Response time over time                                         |
| `ActiveThreadsOT.csv`        | Active thread count over time                                   |
| `UtilizationSSHMon.csv`      | CPU/GPU/memory from SSH monitor                                 |
| `TransactionsperSec.csv`     | Throughput over time                                            |
| `BytesThroughput.persec.csv` | Bytes per second                                                |
| `SummaryReport.csv`          | JMeter summary statistics                                       |
| `*.png`                      | Auto-generated plots from post-processing                       |


---

## 8. Generate Plots (Post-processing)

Run `process_jmeter_results.py` inside the running container to read `tool_evaluations_{N}.csv` and produce per-tool charts (energy consumption, hardware utilization, service time).

### 8.1 Non-A2A plots

```bash
# Scenario 1_1
sudo docker compose --profile env3-only exec env3 python /app/process_jmeter_results.py \
  --csv "/app/3Hour_Radu_nonA2A/1_1/tool_evaluations_1.csv" \
  --users 1 \
  --nodes 1

# Scenario 1_3
sudo docker compose --profile env3-only exec env3 python /app/process_jmeter_results.py \
  --csv "/app/3Hour_Radu_nonA2A/1_3/tool_evaluations_3.csv" \
  --users 1 \
  --nodes 3

# Scenario 1_5
sudo docker compose --profile env3-only exec env3 python /app/process_jmeter_results.py \
  --csv "/app/3Hour_Radu_nonA2A/1_5/tool_evaluations_5.csv" \
  --users 1 \
  --nodes 5
```

Output images are written to the same folder as the input CSV (e.g., `3Hour_Radu_nonA2A/1_1/`).

### 8.2 A2A plots

```bash
# Scenario 1_1
sudo docker compose --profile two-env exec env1 \
  python /app/process_jmeter_results.py \
  --csv "/app/3Hour_Radu/1_1/tool_evaluations_1.csv" \
  --users 1 \
  --nodes 1

# Scenario 1_3
sudo docker compose --profile two-env exec env1 \
  python /app/process_jmeter_results.py \
  --csv "/app/3Hour_Radu/1_3/tool_evaluations_3.csv" \
  --users 1 \
  --nodes 3

# Scenario 1_5
sudo docker compose --profile two-env exec env1 \
  python /app/process_jmeter_results.py \
  --csv "/app/3Hour_Radu/1_5/tool_evaluations_5.csv" \
  --users 1 \
  --nodes 5
```

Output images are written to the same folder as the input CSV (e.g., `3Hour_Radu/1_1/`).

---

## 9. Stopping and Cleaning Up

```bash
# Stop and remove containers (keep volumes/images)
sudo docker compose --profile two-env down
sudo docker compose --profile env3-only down


# Remove built images (forces full rebuild next time)
sudo docker compose --profile two-env down --rmi local
```

> **Before re-running the same scenario**, ensure the output directory is empty or archived, otherwise new results will be appended to existing `tool_evaluations_{N}.csv` files and counts will be off.

