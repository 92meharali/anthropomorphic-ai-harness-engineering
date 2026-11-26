# Comparing against human judgments

After a complete run and independent collection, generate aggregate results:

    python3 -m evaluation.wording_report --study private/study \
      --run private/run --humt private/humt/humt.jsonl \
      --reviewers private/R01.jsonl private/R02.jsonl private/R03.jsonl \
      --out private/report

The report binds the study, predictions, HumT response hashes and ballots to their review IDs. It compares six methods before applying the same OA gate. Counts separate human eligibility, comparable predictions and matches. A hold or unresolved output does not earn a match. The correction and preservation counts use their own human reference questions. Their denominators are included. Warmth counts use the warmth cases and identify whether the selection retained the version with acknowledgement.

The paired bootstrap resamples whole prompt families for the difference in agreement between full harness and frozen OA. Inspect the number of families supporting the difference and report coverage. Call statistics distinguish shared OA requests and arm-specific calls. Convert observed token totals to cost with the prices appropriate to the run and provider-returned model. Keep raw logs and ballots in restricted storage and report aggregate results with their scope.
