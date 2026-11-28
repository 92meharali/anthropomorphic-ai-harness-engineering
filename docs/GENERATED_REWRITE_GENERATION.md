# Issue #26 — Task 2: matched generated rewrites

This change depends on the six Task 1 files, not the closed PR #28 implementation. It does not modify Task 1's protocol or add new screening thresholds, prompts, reviewers or outcomes. See `docs/GENERATED_REWRITE_FREEZE.md` and `rubric/generated_rewrite_protocol_v1.json`. No live results are included.

## Preconditions

- For the 33-case controlled follow-up, import the verified Issue #1 originals and saved cue evidence as described in Task 1. Keep the freeze SHA-256 in a separate restricted record before generation. Review and record the Task 2 commit before a live run. The optional fresh-cohort design uses separate original collection and cohort review.
- Work on a clean checkout that contains Task 1 and Task 2. Run `python -m unittest evaluation.test_rewrite_freeze evaluation.test_rewrite_generate -v` and `python -m unittest discover -q`. The harness integration test must run, not skip, in the full checkout.
- Existing OpenAI credential setup (`OPENAI_API_KEY` in the ignored `.env` or environment); the frozen model alias must be accessible. Do not change it after freezing. No API key is written by this runner.
- Keep all generated files in an access-restricted repository `private/` directory; Git ignore alone does not secure filesystem access. Do not upload generated text, evidence, raw calls or later reviewer ballots to GitHub.

## Plan, run and verify (PowerShell)

Replace the placeholder below with the SHA-256 recorded independently when Task 1 was frozen. Do not use an unapproved hash. The `plan` command checks Task 1 hashes and prints the maximum number of calls; it performs no inference.

```powershell
$freeze = 'ACTUAL_APPROVED_FREEZE_SHA256'
python -m evaluation.rewrite_freeze verify --study private/issue26-frozen
python -m evaluation.rewrite_generate plan --study private/issue26-frozen --freeze-sha256 $freeze
```

Set `$budget` to the maximum printed by `plan`. This is 66 for the 33 verified Issue #1 drafts. The optional fresh-cohort design reserves up to three calls per valid draft including screening.

```powershell
$budget = 66
python -m evaluation.rewrite_generate run --study private/issue26-frozen --freeze-sha256 $freeze --out private/issue26-rewrites --live --max-calls $budget
python -m evaluation.rewrite_generate verify --study private/issue26-frozen --freeze-sha256 $freeze --out private/issue26-rewrites
```

An existing output directory is rejected. No retries or replacement drafts. A 401, 403 or 429 stops the run with partial logs, which cannot pass verification or be handed to reviewers. An unexpected interruption can leave an unsealed partial directory; retain it and consult the coordinator rather than restarting selectively. Ordinary failed calls remain in the results; the other arm is still attempted unless a terminal error prevents further calls. A stopped run's summary is partial, not the final denominator. Missing and failed attempts must not be confused in subsequent reporting; stopped runs are excluded from the Task 3 packet until the coordinator resolves them.

## Experimental treatment

The 33-case follow-up uses the saved resolved assessment of each original. Those assessments already passed the full-history evidence checks in Issue #1. The optional fresh-cohort design calls `cue_routing._assessment` once per draft. `rewrite_freeze.flagged_feedback` extracts the checked unsupported cues from a resolved correction assessment. Generation order is assigned by a frozen seed. Both arms call `rewrite_freeze.rewrite_request` with identical settings; the cue-specific arm receives the additional `validated_cue_feedback` field. Retain identical-to-original and identical-between-arms outputs for review. Valid pairs require a nonempty structured response and the same provider-reported generator ID in both arms. Report failed attempts and model variations separately.

## Restricted output contract

| File | Contents |
| --- | --- |
| `manifest.json` | Task 1 seal, Task 2 source hash, preassigned generation orders, call ceiling |
| `calls.jsonl` | Every attempted detector or rewrite request, exact request hash, raw response or failure, request ID and latency |
| `outcomes.jsonl` | One row per screened original; context, original, detector assessment, flagged status, both arm outputs and pair eligibility |
| `summary.json` | Screening classifications, flagged count, eligible pairs, arm failures and unchanged outputs, model IDs, observed usage and latency by stage |
| `status.json` | Completion status and artifact hashes |

Token summaries count only reported usage; absent values are not interpreted as actual zero usage. Task 3 must first run `verify`, then take only `pair_eligible` rows for the blinded packet and retain all other rows in private accounting. Do not expose detector assessments, arm labels, model metadata or raw requests to reviewers. A/B randomization and human ratings belong to Task 3, not this task. Task 4 will compute the already frozen paired primary outcome and failure-inclusive sensitivity analysis, with original-collection failures and screening coverage reported separately.

The `verify` command rebuilds the original freeze, checks the Task 2 source and file hashes, replays exact detector/rewrite requests against stored responses, and checks outcomes and aggregate summary. No API calls occur during replay. Hashes detect changes relative to the recorded seal and manifest; they are not signatures or a substitute for restricted storage and independent records.
