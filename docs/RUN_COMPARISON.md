# Fixed-pair comparison runner

Generate or use the existing frozen study from the reviewed development pairs. Use the exact source file used to build that study.

    python3 -m evaluation.run_wording --study private/task5-study-v1 \
      --source data/development_reviewed.jsonl --out private/development-dry-run

This checks the frozen hashes and prepares the OA, pairwise and cue detector request contracts offline. For paid scoring, use a fresh restricted output directory, credentials and explicit flags. For the 20-case study, add --live --max-calls 180. Change the detector and pair model aliases before the freeze if needed. The runner records requested settings and provider-returned model IDs.

The call ceiling allows two OA requests, one direct pairwise judgment, four single-candidate detector requests, and up to two edit guards per case. Both cue arms reuse the OA results for their selected candidate. The masked detector and guard see only the current user message. The raw call log and final decisions are written separately. The runner stops on access and rate-limit failures with partial records archived. A run directory represents one attempt.
