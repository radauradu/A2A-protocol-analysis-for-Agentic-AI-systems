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

## Note

- The `--users` and `--nodes` flags affect only the metadata written to the stats CSVs, not the figure content.

