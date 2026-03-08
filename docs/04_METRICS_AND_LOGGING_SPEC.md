# Metrics and Logging Specification

This document specifies the name, definition, units, exact source location, measurement boundaries, and known limitations.

---

## `tool_evaluations_{N}.csv` schema

Every row corresponds to one tool invocation (one LLM-evaluated span). Multiple rows per request are possible when `nodes > 1` (one row per parallel instance).


| Column                    | Type            | Units      | Description                                                                                                       |
| ------------------------- | --------------- | ---------- | ----------------------------------------------------------------------------------------------------------------- |
| `tool_name`               | string          | —          | Name of the tool: `lookup_sales_data`, `analyzing_data`, `create_visualization`, `a2a_communication`              |
| `id`                      | string          | —          | `run_id` — unique identifier for the full workflow request (UUIDv4)                                               |
| `id_tool`                 | string          | —          | CodeCarbon tracker ID for this specific tool execution instance; used to match `emissions_{run_id}_{id_tool}.csv` |
| `timestamp`               | ISO-8601 string | —          | Start time of tool execution                                                                                      |
| `execution_time`          | float           | seconds    | Duration of the tool execution                                                                                    |
| `score`                   | float           | 0.0–1.0    | LLM-as-judge quality score from Arize Phoenix evaluation                                                          |
| `label`                   | string          | —          | LLM-as-judge label (e.g., `correct`, `incorrect`, `partial`)                                                      |
| `total_energy`            | float           | kWh        | Total energy consumed during tool execution                                                                       |
| `cpu_energy`              | float           | kWh        | CPU energy portion                                                                                                |
| `gpu_energy`              | float           | kWh        | GPU energy portion                                                                                                |
| `ram_energy`              | float           | kWh        | RAM energy portion                                                                                                |
| `emissions_rate`          | float           | kg CO₂/kWh | Carbon intensity of the grid at measurement time (CodeCarbon `emissions_rate`)                                    |
| `cpu_utilization`         | float           | %          | Mean CPU utilisation across all cores during the tool execution window                                            |
| `gpu_utilization`         | float           | %          | Mean GPU utilisation during the tool execution window                                                             |
| `a2a_request_size_bytes`  | int or null     | bytes      | Size of the serialised A2AMessage JSON sent from Env1 to Env2 (`null` for non-A2A tools)                          |
| `a2a_response_size_bytes` | int or null     | bytes      | Size of the serialised A2AResponse JSON received from Env2 (`null` for non-A2A tools)                             |
| `a2a_total_size_bytes`    | int or null     | bytes      | `a2a_request_size_bytes + a2a_response_size_bytes`                                                                |
| `nodes`                   | int             | —          | Number of parallel nodes used in this run (`1`, `3`, or `5`)                                                      |
| `users`                   | int             | —          | Number of concurrent JMeter users (always `1`)                                                                    |


---



---

## How averages and standard deviation are computed

`process_jmeter_results.py` reads `tool_evaluations_{N}.csv` and calls `compute_mean_std_table()`:

1. Filters to the relevant metric columns.
2. Groups rows by `tool_name`.
3. Computes `mean` and `std` per group using `pandas.GroupBy.agg`.
4. Caps the standard deviation at `max_cv * mean` to suppress outlier inflation (default `max_cv = 1.0`).
5. Exports per-scenario stats to `output_execution_stats.csv`, `output_energy_stats.csv`, `output_utilization_stats.csv`.

---

---

## JMeter result files


| File                         | Description                                                                      |
| ---------------------------- | -------------------------------------------------------------------------------- |
| `results{scenario}.csv`      | Raw JMeter request log: timestamp, elapsed, label, responseCode, bytes, latency  |
| `SummaryReport.csv`          | JMeter aggregate summary: count, error %, avg, min, max, throughput              |
| `RespTime.csv`               | Response time over time (for response time graph)                                |
| `ActiveThreadsOT.csv`        | Active thread count over time                                                    |
| `UtilizationSSHMon.csv`      | CPU / memory / network metrics from the SSHMonSampler plugin on the host machine |
| `TransactionsperSec.csv`     | Throughput in transactions per second over time                                  |
| `BytesThroughput.persec.csv` | HTTP bytes received per second over time                                         |


