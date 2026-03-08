# Figure Reproduction Map

This table maps each plot output to its input CSV, the command that produces it, and the expected output path. All commands assume the relevant Docker container is running.

---

## How `process_jmeter_results.py` works

The script reads `tool_evaluations_{N}.csv`, computes per-tool mean and standard deviation for energy, execution time, and utilisation, and writes:

- Bar charts: `EnergyperTool.png`, `RespTimeperTool.png`, `UtilizationperTool.png`, `execution_time.png`, `energy_consumption.png`, `utilization_by_tool.png`
- Summary stats CSVs: `output_energy_stats.csv`, `output_execution_stats.csv`, `output_utilization_stats.csv`

JMeter-level plots (`ResponseTime.png`, `ActiveThreads.png`, `Throughput.png`, `BytesThroughput.png`, `ArrivalTimeline.png`) are generated from JMeter CSV files that live in the same folder.

---

## Non-A2A (Env3) figures

### Scenario 1_1 — 1 user, 1 node

**Command:**

```bash
sudo docker compose --profile env3-only exec env3 \
  python /app/process_jmeter_results.py \
  --csv "/app/3Hour_Radu_nonA2A/1_1/tool_evaluations_1.csv" \
  --users 1 --nodes 1
```


| Figure filename           | Input CSV                                          | Output path                                     |
| ------------------------- | -------------------------------------------------- | ----------------------------------------------- |
| `energy_consumption.png`  | `3Hour_Radu_nonA2A/1_1/tool_evaluations_1.csv`     | `3Hour_Radu_nonA2A/1_1/energy_consumption.png`  |
| `EnergyperTool.png`       | `3Hour_Radu_nonA2A/1_1/tool_evaluations_1.csv`     | `3Hour_Radu_nonA2A/1_1/EnergyperTool.png`       |
| `execution_time.png`      | `3Hour_Radu_nonA2A/1_1/tool_evaluations_1.csv`     | `3Hour_Radu_nonA2A/1_1/execution_time.png`      |
| `RespTimeperTool.png`     | `3Hour_Radu_nonA2A/1_1/tool_evaluations_1.csv`     | `3Hour_Radu_nonA2A/1_1/RespTimeperTool.png`     |
| `utilization_by_tool.png` | `3Hour_Radu_nonA2A/1_1/tool_evaluations_1.csv`     | `3Hour_Radu_nonA2A/1_1/utilization_by_tool.png` |
| `UtilizationperTool.png`  | `3Hour_Radu_nonA2A/1_1/tool_evaluations_1.csv`     | `3Hour_Radu_nonA2A/1_1/UtilizationperTool.png`  |
| `ResponseTime.png`        | `3Hour_Radu_nonA2A/1_1/RespTime.csv`               | `3Hour_Radu_nonA2A/1_1/ResponseTime.png`        |
| `ActiveThreads.png`       | `3Hour_Radu_nonA2A/1_1/ActiveThreadsOT.csv`        | `3Hour_Radu_nonA2A/1_1/ActiveThreads.png`       |
| `Throughput.png`          | `3Hour_Radu_nonA2A/1_1/TransactionsperSec.csv`     | `3Hour_Radu_nonA2A/1_1/Throughput.png`          |
| `BytesThroughput.png`     | `3Hour_Radu_nonA2A/1_1/BytesThroughput.persec.csv` | `3Hour_Radu_nonA2A/1_1/BytesThroughput.png`     |
| `Utilization.png`         | `3Hour_Radu_nonA2A/1_1/UtilizationSSHMon.csv`      | `3Hour_Radu_nonA2A/1_1/Utilization.png`         |


---

### Scenario 1_3 — 1 user, 3 nodes

**Command:**

```bash
sudo docker compose --profile env3-only exec env3 \
  python /app/process_jmeter_results.py \
  --csv "/app/3Hour_Radu_nonA2A/1_3/tool_evaluations_3.csv" \
  --users 1 --nodes 3
```


| Figure filename           | Input CSV                                      | Output path                                     |
| ------------------------- | ---------------------------------------------- | ----------------------------------------------- |
| `energy_consumption.png`  | `3Hour_Radu_nonA2A/1_3/tool_evaluations_3.csv` | `3Hour_Radu_nonA2A/1_3/energy_consumption.png`  |
| `EnergyperTool.png`       | `3Hour_Radu_nonA2A/1_3/tool_evaluations_3.csv` | `3Hour_Radu_nonA2A/1_3/EnergyperTool.png`       |
| `execution_time.png`      | `3Hour_Radu_nonA2A/1_3/tool_evaluations_3.csv` | `3Hour_Radu_nonA2A/1_3/execution_time.png`      |
| `RespTimeperTool.png`     | `3Hour_Radu_nonA2A/1_3/tool_evaluations_3.csv` | `3Hour_Radu_nonA2A/1_3/RespTimeperTool.png`     |
| `utilization_by_tool.png` | `3Hour_Radu_nonA2A/1_3/tool_evaluations_3.csv` | `3Hour_Radu_nonA2A/1_3/utilization_by_tool.png` |
| `UtilizationperTool.png`  | `3Hour_Radu_nonA2A/1_3/tool_evaluations_3.csv` | `3Hour_Radu_nonA2A/1_3/UtilizationperTool.png`  |
| `ResponseTime.png`        | `3Hour_Radu_nonA2A/1_3/RespTime.csv`           | `3Hour_Radu_nonA2A/1_3/ResponseTime.png`        |
| `Utilization.png`         | `3Hour_Radu_nonA2A/1_3/UtilizationSSHMon.csv`  | `3Hour_Radu_nonA2A/1_3/Utilization.png`         |


---

### Scenario 1_5 — 1 user, 5 nodes

**Command:**

```bash
sudo docker compose --profile env3-only exec env3 \
  python /app/process_jmeter_results.py \
  --csv "/app/3Hour_Radu_nonA2A/1_5/tool_evaluations_5.csv" \
  --users 1 --nodes 5
```

Output path: `3Hour_Radu_nonA2A/1_5/` (same filenames as above).

---

## A2A (Env1 + Env2) figures

### Scenario 1_1 — 1 user, 1 node

**Command:**

```bash
sudo docker compose --profile two-env exec env1 \
  python /app/process_jmeter_results.py \
  --csv "/app/3Hour_Radu/1_1/tool_evaluations_1.csv" \
  --users 1 --nodes 1
```


| Figure filename           | Input CSV                               | Output path                              |
| ------------------------- | --------------------------------------- | ---------------------------------------- |
| `energy_consumption.png`  | `3Hour_Radu/1_1/tool_evaluations_1.csv` | `3Hour_Radu/1_1/energy_consumption.png`  |
| `EnergyperTool.png`       | `3Hour_Radu/1_1/tool_evaluations_1.csv` | `3Hour_Radu/1_1/EnergyperTool.png`       |
| `execution_time.png`      | `3Hour_Radu/1_1/tool_evaluations_1.csv` | `3Hour_Radu/1_1/execution_time.png`      |
| `RespTimeperTool.png`     | `3Hour_Radu/1_1/tool_evaluations_1.csv` | `3Hour_Radu/1_1/RespTimeperTool.png`     |
| `utilization_by_tool.png` | `3Hour_Radu/1_1/tool_evaluations_1.csv` | `3Hour_Radu/1_1/utilization_by_tool.png` |
| `UtilizationperTool.png`  | `3Hour_Radu/1_1/tool_evaluations_1.csv` | `3Hour_Radu/1_1/UtilizationperTool.png`  |
| `ResponseTime.png`        | `3Hour_Radu/1_1/RespTime.csv`           | `3Hour_Radu/1_1/ResponseTime.png`        |
| `Utilization.png`         | `3Hour_Radu/1_1/UtilizationSSHMon.csv`  | `3Hour_Radu/1_1/Utilization.png`         |


---

### Scenario 1_3 — 1 user, 3 nodes

**Command:**

```bash
sudo docker compose --profile two-env exec env1 \
  python /app/process_jmeter_results.py \
  --csv "/app/3Hour_Radu/1_3/tool_evaluations_3.csv" \
  --users 1 --nodes 3
```

Output path: `3Hour_Radu/1_3/` (same filenames).

---

### Scenario 1_5 — 1 user, 5 nodes

**Command:**

```bash
sudo docker compose --profile two-env exec env1 \
  python /app/process_jmeter_results.py \
  --csv "/app/3Hour_Radu/1_5/tool_evaluations_5.csv" \
  --users 1 --nodes 5
```

Output path: `3Hour_Radu/1_5/` (same filenames).

---

---

## A2A Network Analysis figures 

These three figures are generated by `plot_a2a_network.py` (repo root), **not** by `process_jmeter_results.py`. They read only the `a2a_communication` rows from the three A2A tool-evaluation CSVs.


| Figure | Title                                              | Output file                                     |
| ------ | -------------------------------------------------- | ----------------------------------------------- |
| 4.37   | A2A Message Size Distribution by Scenario (1 user) | `3Hour_Radu/A2A_MessageSize_ByScenario.png`     |
| 4.38   | A2A Byte Exchange by Metric and Scenario (1 user)  | `3Hour_Radu/A2A_ByteExchange_ByMetric.png`      |
| 4.39   | A2A Network Overhead by Scenario (1 user)          | `3Hour_Radu/A2A_NetworkOverhead_ByScenario.png` |


**Input CSVs:**


| Nodes | Input file                              |
| ----- | --------------------------------------- |
| 1     | `3Hour_Radu/1_1/tool_evaluations_1.csv` |
| 3     | `3Hour_Radu/1_3/tool_evaluations_3.csv` |
| 5     | `3Hour_Radu/1_5/tool_evaluations_5.csv` |


**Metrics extracted per scenario** (from `a2a_communication` rows only):

- `a2a_request_size_bytes` — mean ± std 
- `a2a_response_size_bytes` — mean ± std 
- `a2a_total_size_bytes` — mean ± std 
- `execution_time` — mean ± std 

**Run inside the env1 container (after the 3-hour A2A experiments):**

```bash
sudo docker compose --profile two-env exec env1 \
  python /app/plot_a2a_network.py \
  --csv1 /app/3Hour_Radu/1_1/tool_evaluations_1.csv \
  --csv3 /app/3Hour_Radu/1_3/tool_evaluations_3.csv \
  --csv5 /app/3Hour_Radu/1_5/tool_evaluations_5.csv \
  --outdir /app/3Hour_Radu \
  --users 1
```

**Run directly on the host (from the repo root):**

```bash
python plot_a2a_network.py \
  --csv1 3Hour_Radu/1_1/tool_evaluations_1.csv \
  --csv3 3Hour_Radu/1_3/tool_evaluations_3.csv \
  --csv5 3Hour_Radu/1_5/tool_evaluations_5.csv \
  --outdir 3Hour_Radu \
  --users 1
```

All three PNG files are written to `--outdir` (default: `3Hour_Radu/`).

---

## Note

- The `--users` and `--nodes` flags in `process_jmeter_results.py` affect only the metadata written to the stats CSVs, not the figure content.
- `plot_a2a_network.py` skips any scenario whose CSV is missing or contains no `a2a_communication` rows, printing a warning rather than crashing.

