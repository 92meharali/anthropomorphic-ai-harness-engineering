# Wording-v1 held-out results

The wording-v1 study compared six methods on 80 fixed answer pairs from 48 reserved prompt families. The cohort contains 32 memory, 16 availability and 32 warmth cases. Three submitted workbooks matched the frozen case text and contained all 240 case ratings. The study coordinator confirmed that the workbooks contained the original independent judgments and that reviewers submitted them before seeing model predictions or one another's ratings.

The [study protocol](HELD_OUT_PROTOCOL.md) was frozen before API scoring. The 611 saved calls passed replay verification. All comparisons below use the same cases and the same A/B candidates. Cue-based edits select an existing alternate answer.

## Preference agreement

A majority of two or more reviewers established a preference for all 80 cases. The table counts exact matches before the final OA gate. A method hold contributes to the total denominator and reduces coverage. A prediction of a tie is counted as an explicit decision.

| Method | Exact matches / 80 | Agreement | Cases with a decision | Ties | Holds |
|---|---:|---:|---:|---:|---:|
| Keep the original | 47 | 58.8% | 80 | 0 | 0 |
| Lower HumT | 43 | 53.8% | 80 | 0 | 0 |
| Frozen OA | 33 | 41.3% | 80 | 45 | 0 |
| Direct pairwise LLM judge | 64 | 80.0% | 80 | 0 | 0 |
| Full cue harness | 80 | 100.0% | 80 | 0 | 0 |
| Cue harness with earlier turns withheld | 46 | 57.5% | 47 | 0 | 33 |

The full harness exceeded frozen OA by **58.8 percentage points**, with a 95% interval of **48.1 to 68.3 points** from 10,000 paired prompt-family bootstrap draws. The direct judge comparison was **20.0 points** in favor of the harness, with a descriptive interval of **12.2 to 28.2 points**. These intervals reflect the submitted reference and the sampled families.

Frozen OA matched 33 of its 35 A/B selections. The 45 tied OA scores explain most of its lower overall agreement on wording preference. When earlier turns were withheld, the harness held all 32 memory cases. Across the 47 cases on which it chose an answer, it matched 46 preferences.

The [HumT baseline](HUMT.md) scored all 160 answers locally with the pinned GPT-2 checkpoint. The weights came from a public mirror and matched the official checksum. The lower-HumT policy matched 4/16 availability, 16/32 memory and 23/32 warmth cases. HumT reads the answer text alone, so its preference between the same two answers stays fixed across different conversations.

## Cue correction and the OA gate

| Outcome | Full harness | Direct pairwise judge | Lower HumT |
|---|---:|---:|---:|
| Selected an alternate on originals flagged for correction | 33/33 | 33/33 | 11/33 |
| Selected an alternate on originals accepted for wording | 0/47 | 16/47 | 15/47 |
| Kept the warm original when reviewers preferred it | 31/31 | 18/31 | 23/31 |
| Selected an answer that reviewers flagged for correction | 0/80 | 0/80 | 22/80 |
| Selected answers sent to review by the final OA gate | 5/80 | 5/80 | 23/80 |

The direct judge's 16 extra edits were on 13 warmth cases and three memory cases. The full harness selected an alternate on 33 cases and kept the original on 47. The separate OA gate passed 75 of its selections and sent five to review.

Reviewers were unanimous on preference for 75 of 80 cases. Average raw pairwise preference agreement was 95.8%, with Cohen's kappa from 0.899 to 0.925 across the three reviewer pairs. All three reviewers gave the same correction judgment and marked content preserved on every pair. On these submitted ballots, the preference majority always chose the alternate when the original needed correction and chose the original otherwise. This alignment matters when interpreting both the 100% agreement and the extent to which preference provides a separate outcome.

## Inference and limits

The API run recorded 611 calls, 1,211,379 input tokens, 76,606 output tokens and 1,884.7 seconds of summed request latency. The shared OA gate used 160 calls. The direct judge used 80 calls. The full harness used 193 cue and edit-guard calls, and the history-withheld harness used 178. HumT used local CPU inference. Billing cost remains unverified.

The result applies to these authored answer pairs and the wording decisions they test. Performance on naturally generated drafts and users' perceptions of the chatbot's human-like qualities remain open questions. [Issue #26](https://github.com/92meharali/anthropomorphic-ai-harness-engineering/issues/26) tracks the separate comparison of cue-specific and generic generated rewrites.
