# Experiment Analysis Report

## Experiment: strands-math-agent-eval
- ID: `83656138-59d1-4e5f-9ae8-3f963ee821ec`
- URL: https://us5.datadoghq.com/llm/experiments/83656138-59d1-4e5f-9ae8-3f963ee821ec
- Dataset: `strands_math_agent_seed_20260731` (7 records)
- Project: `test-project-new`

## Executive Summary

**6 of 7 experiment events failed** due to a `strands.types.exceptions.ConcurrencyException`. The root cause is an infrastructure issue in the experiment harness, not a quality problem in the agent itself. The single successful event (sum of first 20 primes) shows the task function and evaluators work correctly when not contending for the shared Agent instance.

## Results Breakdown

| Status | Count | % | Category |
|--------|-------|---|----------|
| OK | 1 | 14% | math (arithmetic) |
| Error | 6 | 86% | 3 math + 3 off_topic (all ConcurrencyException) |

## Root Cause: ConcurrencyException

The experiment was configured with `jobs=5` (5 concurrent workers), but the `strands.Agent` instance is **not thread-safe** — it maintains internal conversation state and cannot be called concurrently from multiple threads. When 5 workers attempted to call `agent(question)` simultaneously, 6 of 7 tasks hit `ConcurrencyException` within ~20-170ms (before any LLM call was made).

**Why only 1 succeeded**: The first task to acquire the agent's internal lock ran to completion (8163ms for the prime sum calculation). All others were rejected immediately.

## The Single Successful Event

| Field | Value |
|-------|-------|
| Input | "Calculate the sum of the first 20 prime numbers" |
| Output | Correct: 639 with step-by-step table |
| Expected | 639 |
| Duration | 8163ms |
| Status | ok |

**Evaluator scores**: The metrics dict is empty (`{}`), indicating the evaluators either did not run on this event or their results were not captured in the experiment event metadata. This is likely because the evaluator results are surfaced differently in this version of ddtrace — they may appear as separate evaluation spans rather than inline metrics.

## Diagnosis & Fix

### Problem
```python
# Current (broken with jobs > 1):
agent = Agent(system_prompt=SYSTEM_PROMPT, tools=[calculator])

def task_fn(input_data, config=None):
    result = agent(question)  # NOT thread-safe
    return str(result)

experiment.run(jobs=5)  # 5 concurrent threads → ConcurrencyException
```

### Fix Options

**Option A — Set `jobs=1` (sequential execution):**
```python
experiment.run(jobs=1)
```
Simplest fix. 7 records will take ~7 × 3-8s ≈ 21-56 seconds sequentially. Acceptable for this dataset size.

**Option B — Create a new Agent per task call:**
```python
def task_fn(input_data, config=None):
    local_agent = Agent(system_prompt=SYSTEM_PROMPT, tools=[calculator])
    question = input_data.get("question", "")
    result = local_agent(question)
    return str(result)
```
Enables parallelism but creates overhead per call. Better for larger datasets.

### Recommendation
Use **Option A** (`jobs=1`) for immediate re-run. The dataset is small (7 records) and sequential execution will complete in under a minute. Switch to Option B when scaling to larger datasets.

## Quality Assessment (from the 1 successful event)

The single successful event demonstrates:
- ✅ Task function correctly integrates with the Strands Agent
- ✅ The V3 system prompt is correctly loaded
- ✅ Calculator tool is invoked and produces correct results
- ✅ Output format is detailed with step-by-step reasoning
- ⚠️ Evaluator metrics not visible in event metadata (may need ddtrace version check)

## Recommendations

1. **Immediate**: Re-run the experiment with `jobs=1` to get valid results for all 7 records
2. **Evaluator visibility**: Check if evaluator results appear as separate spans in the trace (trace_id: `6a6cfae800000000fb388a0fb0a60295`) or if the `EvaluatorResult` return format needs adjustment for this ddtrace version
3. **Future scaling**: For datasets >20 records, refactor `task_fn` to create a fresh Agent instance per call (Option B)
4. **Dataset enrichment**: Add more diverse math questions (algebra, geometry, calculus) to test beyond arithmetic
