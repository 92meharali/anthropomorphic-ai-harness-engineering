# Offline wording study harness

This runner prepares a fixed batch of matched response pairs, creates a blinded A/B packet, and compares saved HumT and frozen OA scores against human preferences. It uses the existing OA request builder. Preparation and analysis run locally.

## Prepare the study

Create a private JSONL file with one row per matched pair:

```json
{"pair_id":"example-1","prompt_group_id":"example-group-1","cue":"availability","prompt":"Could you explain how to start this exercise?","original":"Start with the worked example and compare the first step.","edited":"You can always count on me to be here. Start with the worked example and compare the first step."}
```

Keep the practical advice, facts and safety guidance stable when changing a cue. Track source allocations when choosing unused PERSONA prompts. Assign related contexts and variants to the same prompt group. The harness checks for conflicting group assignments on identical normalized prompts. Detecting related scenarios and verifying that edits preserve content still require review.

From the repository root:

```sh
python3 -m evaluation.wording_harness prepare \
  --pairs private/wording-pairs.jsonl \
  --protocol rubric/oa_protocol.json \
  --study private/wording-study
```

The study directory contains a manifest with file hashes. Give reviewers only `review_packet.jsonl` and the review instructions below. Keep `pair_key.jsonl`, predictions and scoring runs with the research coordinator. Use separate copies for each reviewer.

## Score the candidates

Use `oa_inputs.jsonl` with the existing OA runner and the study's copied rubric. Its OA request contains the user prompt and candidate response. The manifest expects `gpt-6.2-sol`; set `OPENAI_MODEL=gpt-6.2-sol` explicitly when running the scorer. For a batch of up to 30 pairs:

```sh
OPENAI_MODEL=gpt-6.2-sol python3 -m evaluation.run \
  --provider openai --input private/wording-study/oa_inputs.jsonl \
  --protocol private/wording-study/protocol.json \
  --run-dir private/wording-study/oa-run --dry-run
```

Remove `--dry-run` for a live scoring run, and use a new run directory for the live results. The existing OA runner has a 60-response limit. For a larger study, score explicit shards with the same configuration, then combine the non-overlapping results before analysis.

Run the published HumT scorer separately. First verify the implementation and score direction on a small development fixture. Save the scorer version, model and settings with the run. Export one row per response with `item_id`, `response_sha256` (SHA-256 of the exact response encoded as UTF-8), and a finite numeric `humt` or `null`. Missing scores and abstentions are recorded as unresolved. This harness imports HumT scores and does not compute them.

## Collect and compare judgments

Ask each of three reviewers which version's wording fits the situation, whether either response has wording that warrants correction, and whether the edit preserves the practical content. Allow a tie or inability to judge. Have reviewers make their initial judgments independently.

Record one row per pair in each reviewer file. Copy the pair hash from the packet to bind the judgment to the case and A/B order.

```json
{"review_id":"W0001","pair_sha256":"<copy from packet>","preference":"A","cue_needs_correction":"B","content_preserved":true}
```

Preference accepts `A`, `B`, `tie` or `cannot_judge`. Cue correction accepts `A`, `B`, `both`, `neither` or `cannot_judge`. For content preservation, use `true`, `false` or `null` when uncertain.

```sh
python3 -m evaluation.wording_harness analyze \
  --study private/wording-study \
  --oa private/wording-study/oa-run/results.jsonl \
  --humt private/wording-study/humt.jsonl \
  --reviewers private/reviewer1.jsonl private/reviewer2.jsonl private/reviewer3.jsonl \
  --output private/wording-study/report.json
```

The report gives both baselines the same comparison set. Two of three matching ballots determine the reference, including explicit ties. The simple HumT baseline chooses the lower score, and OA chooses the higher score. Equal scores predict a tie. Lower HumT is a baseline policy for comparison and carries no automatic penalty or revision rule. Both policies are candidates for evaluation. The report also shows the content-preserved subset and results by cue. It retains per-pair ballots and scores for error review. Use prompt groups as the resampling unit if estimating uncertainty. The prototype returns descriptive counts.

## Verification

Run `python3 -m unittest evaluation.test_wording_harness` from the repository root. The regression test uses invented scores to check blinding, tied OA scores, incomplete scorer coverage and tamper detection.
