# Harness engineering for the chatbot study

A harness is the software around the model that supplies context, validates outputs and determines what happens next. The model can propose an answer or a judgment. The harness defines the allowed actions, stopping rules and records for checking those actions. Three uses of the term matter here.

| Use | What it controls | Application to this project |
|---|---|---|
| Development harness | How a coding agent navigates, changes and checks a repository | Put study contracts and decisions in versioned files. Turn invariants such as split isolation and stable inputs into deterministic checks. |
| Runtime harness | How model calls, control flow, state and failures produce a system outcome | Our existing controller checks OA, selects a passing draft, requests at most one revision from a failing draft, and holds unresolved cases. |
| Evaluation harness | How a fixed cohort is executed, recorded, scored and compared | The offline wording runner freezes the cases and OA rubric, blinds the A/B order, matches imported scores to the original inputs and aggregates blinded human judgments. |

OpenAI's first-party account describes development harnesses in terms of discoverable repository knowledge, tools and mechanically enforced boundaries. Anthropic's evaluation guide distinguishes the harness under test from the evaluation harness and separates the trace of what the system did from the measured outcome. Anthropic's workflow guide describes predefined workflows and an evaluator-optimizer pattern. These sources motivate the design choices above. The chatbot controller is a predefined workflow with a fixed stopping rule. [OpenAI engineering account](https://openai.com/index/harness-engineering/) · [Anthropic evaluation guide](https://www.anthropic.com/research/demystifying-evals-for-ai-agents) · [Anthropic workflow guide](https://www.anthropic.com/research/building-effective-agents)

## What we can test

**First isolate measurement.** Use PERSONA prompts and matched answers that change a single interpersonal cue. Score HumT and frozen OA independently. Ask human reviewers about preference, cue correction and preservation of useful content. HumT measures human-like tone. Its score does not establish whether a particular cue fits a person's situation. Predefine a lower-HumT baseline, a higher-OA baseline and how ties count. Use a context-independent baseline and matched contexts if the goal is to identify what context contributes. Report rescoring failures and reviewer disagreement. [HumT/DumT paper](https://aclanthology.org/2025.acl-long.1261/) · [Local runbook](WORDING_HARNESS.md)

**Then test a routing policy.** A cue-aware policy could compare a candidate edit with the original, keep supportive wording when it fits, and select an edit only when it improves the cue without losing important content. For example, an acceptable answer may still contain a promise of ongoing availability. A focused edit can remove the promise and preserve ordinary acknowledgement. Use human ratings to test whether this improves the result before giving the policy a role in the chatbot. A high HumT score alone provides no decision threshold.

**Compare systems under common conditions.** Use the same prompts and candidate pairs for OA-only, a HumT-only selection baseline and contextual cue evaluation. Hold the generation and judge settings fixed across comparisons where possible. The causal question about feedback-guided rewriting requires a separate generic rewrite control. Record which candidate was selected, which checks failed, why a case was held, latency and model usage. Judge the selected answers with independent human ratings. Keep every case from one prompt family together when splitting data or estimating uncertainty.

## Implementation and scope

[The prototype](../evaluation/wording_harness.py) operates on files and makes no network calls. It freezes a matched case set, the OA rubric and the mapping between the original and the edit. The existing OA runner can score its generated inputs. The prototype imports HumT scores and human judgments after those steps and reports coverage, agreement, ties, disagreement and content preservation. It checks exact prompt grouping within a cohort. Previous allocation and near-duplicate screening still need to be handled during cohort selection.

The 40 saved controller traces replayed to the same routes using the recorded model outputs. That checks routing and record quality. It adds no new independent evidence about response quality. The next study still needs a pinned HumT scorer, reviewed wording edits and new blinded ratings. Real deployment would need multi-turn evaluation and qualified clinical and religious review for the intended application.
