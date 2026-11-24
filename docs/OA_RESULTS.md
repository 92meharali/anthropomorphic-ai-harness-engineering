# Completed OA pilots

Overall Appropriateness (OA) scores the full answer in context on a 1–5 scale. Human reference decisions use the median score. OA 4 or 5 passes.

| Cohort | Result | Interpretation |
|---|---|---|
| Initial 60 PERSONA responses | Decision Model exact OA agreement 44/60 (73.3%); frozen LLM 28/60 (46.7%). | Every human median was 4 or 5. |
| 30-case challenge | Against historical ratings, the Decision Model passed 10/10 below threshold and the frozen LLM passed 4/10. Against a new median from three reviewers, the frozen LLM matched 30/30 pass/revise decisions. | The two comparisons use different references on the same cases. |
| Fresh 120-response challenge | Frozen LLM agreement with the initial human median was 116/120 (96.7%), with 0/58 false approvals and 4/62 false rejections. Exact OA agreement was 84/120 (70%). | All 58 cases the initial median marked for revision were constructed variants. |
| Separate 40-draft controller pilot | Human-rated passes increased from 35/40 to 40/40. All five rewrites moved from a median OA of 3 to 5. | This measures the full controller on five revision attempts. The value of specific feedback still needs a generic rewrite control. |

The original OA protocol in this repository uses standalone interactions. The planned paired study includes visible history. Document how that history is presented to the OA baseline, check compatibility with the protocol, and freeze the settings before the held-out run.

The earlier results concern whole-response appropriateness. The upcoming study tests whether a cue-aware policy improves decisions about human-like wording.
