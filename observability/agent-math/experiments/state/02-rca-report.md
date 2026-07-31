# Root Cause Analysis Report — strands-math-agent

## Classification Overview

- 20 traces classified, 3 failures (15% failure rate)
- 2 failure modes: Guardrail bypass (2 traces), Verbose refusal (1 trace)

## Failure Taxonomy

| ID | Failure Mode | Root Cause | Severity | Traces |
|---|---|---|---|---|
| FM-1 | Guardrail bypass — answers non-math questions | System prompt missing or lacks refusal instruction | CRITICAL | 6a6cf60900000000fb0f270218ad70d8, 6a6cf5780000000081de0e9b1537c798 |
| FM-2 | Verbose/inconsistent refusal format | System prompt lacks refusal template/format constraint | MEDIUM | 6a6cf63b000000005fa544bb628e3988 |

## Root Causes

### RC-1: Missing system prompt (CRITICAL)

Trace 6a6cf5780000000081de0e9b1537c798 had NO system message — only a bare user message. Without any system prompt, the model has no guardrail instructions and behaves as a general-purpose assistant.

### RC-2: Weak system prompt without refusal instruction (HIGH)

Trace 6a6cf60900000000fb0f270218ad70d8 used a minimal system prompt:
"You are an assistant that calulate math problems."

This prompt:
- Has a typo ("calulate")
- Only states role, does NOT include explicit refusal instruction
- Does NOT provide expected refusal wording
- Does NOT forbid answering off-topic questions

### RC-3: Weak system prompt without refusal format constraint (MEDIUM)

Trace 6a6cf63b000000005fa544bb628e3988 used:
"You are an assistant that calulate math problems. Don't answer any type of question out of math problems."

This includes refusal intent but:
- Does NOT provide expected refusal template
- Does NOT constrain response format
- Result: correct refusal, but verbose (356 chars, 86 tokens vs expected 56 chars)

## Unified Theory

All failures trace to system prompt inconsistency across code paths. The application has multiple prompt versions in production:

| Version | Content | Behavior |
|---|---|---|
| V3 (working) | Full prompt with explicit refusal template + anti-jailbreak | Reliable terse decline |
| V2 (partial) | Short prompt + "Don't answer" clause | Declines but verbose |
| V1 (minimal) | "You are an assistant that calulate math problems." | No guardrail |
| V0 (missing) | No system prompt | No guardrail |

## Evaluator Targets

Based on this RCA, evaluators should measure:
1. **Guardrail compliance**: Does the agent refuse non-math questions?
2. **Refusal format compliance**: When declining, does the agent use the expected terse format?
3. **Math correctness**: When answering math questions, is the answer correct?

## Recommendations

1. Consolidate to single system prompt (V3) across all code paths
2. Add startup assertion verifying system prompt contains refusal template
3. Build evaluators targeting the three dimensions above
