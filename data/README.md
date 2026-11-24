# Wording study data, version 1

This is a set of newly authored, unannotated study cases adapted from **60 unused PERSONA mental-health prompt groups**. The published records contain the adaptations and source group identifiers. The original prompts, original answers and prior ratings stay in the research archive. See the [manifest](wording_pairs_v1.manifest.json) for source revision, selection, assumptions and the dataset hash.

| Cue group | Distinct prompt families | Contexts per family | Paired cases |
|---|---:|---:|---:|
| Memory | 20 | 2 | 40 |
| Relationship and availability | 20 | 1 | 20 |
| Ordinary warmth | 20 | 2 | 40 |
| **Total** | **60** | | **100** |

Each paired case includes two candidate answers, for **200 scoring trials** across 120 distinct answer texts. The memory and warmth groups reuse identical candidates across their two contexts. Availability pairs replace the relationship phrase while keeping the acknowledgement and practical advice the same. Neither candidate has an assigned human label.

## Input fields

- `pair_id` identifies the A/B case under one context. `prompt_group_id` groups all contexts from the same scenario. Assign whole groups to splits.
- `cue` and `context_condition` are coordinator metadata. Keep them out of the reviewer and model inputs.
- `current_user_message` and `visible_history` give the future cue harness structured context. Use the trusted system capabilities in the manifest for this cohort.
- `prompt` is the rendered context for the current OA runner. `original` and `edited` are the source answers before A/B blinding. In this dataset they are both authored candidates, and the labels describe the wording edit.

The manifest assumes the supplied history is complete for each case. The simulated chatbot has no access to past sessions and cannot guarantee future availability or initiate a check-in. The initial study compares methods within these assumptions.

## Prepare and verify the full batch

Run these commands from the repo root. Use a fresh directory if repeating preparation.

```sh
python3 -m evaluation.wording_harness prepare \
  --pairs data/wording_pairs_v1.jsonl \
  --protocol rubric/oa_protocol.json \
  --study outputs/wording-v1
OPENAI_MODEL=gpt-6.2-sol python3 -m evaluation.run \
  --input outputs/wording-v1/oa_inputs.jsonl \
  --protocol outputs/wording-v1/protocol.json \
  --run-dir outputs/wording-v1/oa-dry-run \
  --limit 200 --dry-run
```

Expect 100 rows in `review_packet.jsonl`, 200 in `oa_inputs.jsonl`, and 200 requests in the dry run. Pass `--limit 200` explicitly for this batch. The dry run uses no API. A later live run uses credentials and a new run directory. Run HumT separately and import its scores using the [runbook](../docs/WORDING_HARNESS.md).

The existing OA rubric is preserved as the baseline. Earlier turns appear as text within each displayed study prompt. The cue detector and keep/edit/hold policy are tracked in [Issue #1](https://github.com/92meharali/anthropomorphic-ai-harness-engineering/issues/1).

## Annotation handoff

First have a content reviewer check that the pairs keep the same advice, facts, and relevant caveats. If you change any text, rebuild the study before collecting judgments. Share only the generated **review packet** and the [reviewer instructions](REVIEWER_GUIDE.md) with annotators. The repo source contains the A/B key ingredients, so use a separate blinded handoff.

The planned first pass uses 12 families, four per cue group. Select those groups before examining scores and include all their contexts. If using the full 60 for development, use another disjoint set for held-out evaluation. Record review answers under the supplied IDs and hashes. The analysis command in the runbook expects three reviewer files covering the frozen packet.
