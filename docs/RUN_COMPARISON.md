# Fixed-pair comparison runner

Generate or use the existing frozen study from the reviewed development pairs. Use the exact source file used to build that study.

    python3 -m evaluation.run_wording --study private/task5-study-v1 \
      --source data/development_reviewed.jsonl --out private/development-dry-run

This checks the frozen hashes and prepares the OA, pairwise and cue detector request contracts offline. For paid scoring, use a fresh restricted output directory, credentials and explicit flags. For the 20-case study, add --live --max-calls 180. Change the detector and pair model aliases before the freeze if needed. The runner records requested settings and provider-returned model IDs.

The call ceiling allows two OA requests, one direct pairwise judgment, four single-candidate detector requests, and up to two edit guards per case. Both cue arms reuse the OA results for their selected candidate. The masked detector and guard see only the current user message. The raw call log and final decisions are written separately. The runner stops on access and rate-limit failures with partial records archived. A run directory represents one attempt.

## Freeze and verify scoring

Keep the offline dry run's manifest. A live run requires its exact configuration with the freeze-manifest flag:

    python3 -m evaluation.run_wording --study private/task5-study-v1 \
      --source data/development_reviewed.jsonl --out private/development-live \
      --freeze-manifest private/development-dry-run/manifest.json --live --max-calls 180

Changes to the source, study, models, capabilities, prompts or runner code invalidate the freeze. The runner recognizes the exact reviewed development cohort and the approved reserved case allocation. Held-out scoring also requires a local approval JSON supplied with the approval flag. Set configuration_sha256 to the value in the dry-run manifest and supply content_review_record and protocol_signoff_record as references to the actual approvals. This binds the local record to the exact study settings. The record is an attestation by the coordinator.

A completed-run seal records the hashes of the call log, run manifest and pair results. Reporting replays recorded provider outputs through the same request sequence and policy to verify every saved decision. Report using the same runner code as scoring.

## Wording-v1 held-out run

After recording review of the exact workbook and sign-off on the protocol, score the 80 reserved pairs using the private cohort and its dry-run manifest:

    study_root=private/wording-v1-held-out
    python3 -m evaluation.run_wording --study "$study_root/cohort/study" \
      --source "$study_root/cohort/reserved_pairs.jsonl" --out "$study_root/live" \
      --freeze-manifest "$study_root/dry-run/manifest.json" \
      --approval "$study_root/approval.json" --live --max-calls 720

Use the configured API credential or pass a private credential file with `--env-file`. The 720-call limit covers all cases including both optional edit guards. The run uses `gpt-6.2-sol` for OA, cue detection and the pairwise judgments. HumT is scored separately with the pinned local checkpoint.

Keep the run manifest, status seal and complete call log in restricted storage. Check completed pair count, provider output coverage and replay before relying on the run. Wait for the three initial ballots and complete HumT scores before comparing agreement across methods. See [the reporting runbook](COMPARISON_REPORT.md).
