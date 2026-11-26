# Held-out comparison protocol

Status: proposed freeze checklist. Confirm these settings before any held-out model scores or human judgments are opened. Use the 20 development pairs for debugging and eligibility checks.

## Cohort and sample size

The development set uses 12 families. Reserve all remaining 48 families from wording-v1 for the first held-out comparison. They contain 80 pair-contexts: 32 memory, 16 availability, and 32 warmth. Three ballots per case would yield 240 judgments. The family is the independent sampling unit. This is the available fixed cohort, rather than a claim of power for a particular effect. Use the development results to report ties, expected matched disagreements, uncertainty and the smallest effect worth detecting. Add a separately allocated cohort if the resulting precision is insufficient.

    python3 -m evaluation.held_out --out private/wording-v1-reserved

Independently review the prepared texts for content preservation before distribution. If a correction is needed, preserve the original, record the edit and freeze the resulting text before scoring. Keep related contexts within one split. The preparation command rejects source or allocation changes and prevents neighboring sibling cases. Annotators receive the approved blinded packet and guide, with no access to scores, pair mappings or method labels. Collect initial judgments independently and document provenance.

If reviewers request answer edits, prepare the approved cases in a new directory with `--reviewed private/reviewed_reserve.jsonl`. Use the resulting `reserved_pairs.jsonl` as the runner's source. Answer edits must be identical across sibling contexts.

For an Excel handoff, run the following with Node.js and the Codex workspace's `@oai/artifact-tool` module available:

    node scripts/render_annotation.mjs private/wording-v1-reserved/study/review_packet.jsonl private/review.xlsx
    python3 -m evaluation.annotation_xlsx --packet private/wording-v1-reserved/study/review_packet.jsonl --workbook private/review.xlsx --verify-blank

Give each reviewer a separate copy of the approved workbook. For each completed copy, run the same Python command with `--out private/R01.jsonl` in place of `--verify-blank`, using a separate output file per reviewer. The importer checks every case and allows ties and abstentions. The coordinator records who completed each copy and how blinding was maintained in the private study log.

## Conditions

Use the same prepared candidates in all arms:

1. Keep the original.
2. Prefer lower HumT.
3. Prefer higher frozen whole-answer OA.
4. Direct pairwise judge with the shared human rubric.
5. Full cue harness with visible history.
6. Cue harness with earlier turns withheld.

In the history ablation, hide earlier turns from both the cue detector and its edit guard, keep system capabilities and the current message, and mark visible history incomplete. For end-to-end measures, use the same full-context OA gate for every selected candidate. Report each arm's selection before the gate separately. Track the extra edit-guard call, model variants and settings, token usage and latency.

## Outcomes and reporting

Primary comparison: the full harness versus frozen OA on agreement with the human preference reference. Two matching votes establish A, B or an explicit tie. Human abstentions and cases without a majority remain unresolved. Report agreement over the same cases with eligible references, counting a method hold as unresolved and reporting coverage. Also report agreement on comparable decisions with the denominator shown. Treat the direct pairwise judge comparison as a check on the added value of routing and evidence, and account for extra inference calls.

Report missed corrections and unnecessary edits against the separate human correction question, the cue and final OA dispositions, and the content-preservation votes for selected edits. Report warmth retention for warmth cases where a version can be selected and separately for cases in which reviewers prefer the warm wording. Give per-cue counts, ties, holds and inter-reviewer agreement. Use a paired prompt-family bootstrap with 10,000 draws and seed 20261126 for the primary difference. Use careful interpretation when uncertainty is wide or evidence is drawn from very few families.

Record hashes for the exact cohort, blinded packet, rubric, prompts, capability settings and scorer configuration before the run. Confirm the reserve has not been used to tune the methods. Keep raw model logs and ballots in restricted storage. Publish aggregate outcomes.

Create the approved run's dry-run manifest and record its configuration hash in the private content review and protocol sign-off. Pass that manifest and the approval record to the live runner using the scoring instructions. Import the completed blinded ballots before comparing methods.

## Generated-edit follow-up

After the fixed-candidate comparison, and only if it supports continuing, compare one cue-targeted edit with one generic rewrite on the same flagged drafts. Match the generator and attempt budget. Preserve the original as reference, blind the versions and score useful advice, warmth, correction and final OA. This is a separate experiment.
