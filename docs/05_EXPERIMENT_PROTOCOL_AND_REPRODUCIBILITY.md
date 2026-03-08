# Experiment Protocol and Reproducibility

## Overview

All experiments follow a fixed protocol: one simulated user issuing requests at a random exponential inter-arrival time, three scenario variants (by number of parallel nodes), and three independent repetitions per scenario. The same prompts, the same service configuration, and the same measurement setup are used for both A2A and non-A2A implementations.

---

## Assumptions and parameters


| Parameter                               | Value                                      | Configured in                                                           |
| --------------------------------------- | ------------------------------------------ | ----------------------------------------------------------------------- |
| Virtual users (JMeter threads)          | 1                                          | JMeter `.jmx` ThreadGroup                                               |
| Inter-arrival distribution              | Exponential                                | Groovy timer inside each `.jmx`                                         |
| Mean inter-arrival time                 | 30 seconds                                 | Groovy timer parameter                                                  |
| Experiment duration                     | ~3 hours                                   | JMeter `LoopController` / `ScheduledThreadGroup`                        |
| Parallel nodes (scenario parameter)     | 1, 3, or 5                                 | JMeter user-defined variable `nodes`, forwarded as HTTP query parameter |
| Number of independent runs per scenario | 3                                          | Manually repeated                                                       |
| LLM model                               | Llama 3.2 (3B)                             | Ollama; `OLLAMA_BASE_URL` env var                                       |
| LLM temperature                         | 0.1                                        | Set in `functionalities.py` and `env3_openai_agents.py`                 |
| Prompt source                           | `tests/jmeter_test/prompts_for_jmeter.csv` | JMeter `CSVDataSet` config element                                      |


---

## Prompts

The file `tests/jmeter_test/prompts_for_jmeter.csv` contains 12 natural-language queries about company sales data. JMeter reads them sequentially (cycling when exhausted) and sends each as the `prompt` field of the HTTP request body.

```
tests/jmeter_test/prompts_for_jmeter.csv
```



---

## JMX file to scenario mapping


| JMX file                                | Implementation  | Scenario        | Target host flag     |
| --------------------------------------- | --------------- | --------------- | -------------------- |
| `tests/jmeter_test/ReqVM3_a2a_1_1.jmx`  | A2A (Env1+Env2) | 1 user, 1 node  | `-Jtarget.host=env1` |
| `tests/jmeter_test/ReqVM3_a2a_1_3.jmx`  | A2A (Env1+Env2) | 1 user, 3 nodes | `-Jtarget.host=env1` |
| `tests/jmeter_test/ReqVM3_a2a_1_5.jmx`  | A2A (Env1+Env2) | 1 user, 5 nodes | `-Jtarget.host=env1` |
| `tests/jmeter_test/ReqVM3_env3_1_1.jmx` | Non-A2A (Env3)  | 1 user, 1 node  | `-Jtarget.host=env3` |
| `tests/jmeter_test/ReqVM3_env3_1_3.jmx` | Non-A2A (Env3)  | 1 user, 3 nodes | `-Jtarget.host=env3` |
| `tests/jmeter_test/ReqVM3_env3_1_5.jmx` | Non-A2A (Env3)  | 1 user, 5 nodes | `-Jtarget.host=env3` |


Each `.jmx` embeds:

- `CSVDataSet` reading `prompts_for_jmeter.csv`
- A Groovy `ConstantThroughputTimer` or `BeanShell` timer for the exponential delay
- `SSHMonSampler` configuration using the `-Jssh.*` properties passed at runtime
- HTTP sampler targeting `http://{target.host}:8000/env1-then-env2-a2a` (A2A) or `/env3-openai-agents` (non-A2A) with `nodes` as a query parameter

---

## Output locations

### A2A


| Scenario | Tool evaluations CSV                    | JMeter raw CSV                  |
| -------- | --------------------------------------- | ------------------------------- |
| 1_1      | `3Hour_Radu/1_1/tool_evaluations_1.csv` | `3Hour_Radu/1_1/results1_1.csv` |
| 1_3      | `3Hour_Radu/1_3/tool_evaluations_3.csv` | `3Hour_Radu/1_3/results1_3.csv` |
| 1_5      | `3Hour_Radu/1_5/tool_evaluations_5.csv` | `3Hour_Radu/1_5/results1_5.csv` |


### Non-A2A


| Scenario | Tool evaluations CSV                           | JMeter raw CSV                         |
| -------- | ---------------------------------------------- | -------------------------------------- |
| 1_1      | `3Hour_Radu_nonA2A/1_1/tool_evaluations_1.csv` | `3Hour_Radu_nonA2A/1_1/results1_1.csv` |
| 1_3      | `3Hour_Radu_nonA2A/1_3/tool_evaluations_3.csv` | `3Hour_Radu_nonA2A/1_3/results1_3.csv` |
| 1_5      | `3Hour_Radu_nonA2A/1_5/tool_evaluations_5.csv` | `3Hour_Radu_nonA2A/1_5/results1_5.csv` |


---

---

---

## Exact commands

See `[00_RUN_GUIDE.md](00_RUN_GUIDE.md)` for the complete, copy-paste-ready run commands for all six scenario × implementation combinations.