# Generated-rewrite experiment

This follow-up tests whether validated cue feedback improves a generated correction on the same original model draft. The [wording-v1 report](WORDING_RESULTS.md) covers selection between prepared answers.

## Freeze the cohort and protocol

Collect unedited model drafts on fresh prompt families. Keep a private record of the source, generator settings and screening for close overlap with wording-v1. The runner rejects exact matches against wording-v1 current messages and family IDs. Inspect semantic overlap during cohort preparation. Use the supplied transcript as the complete available same-chat history under the frozen chatbot capabilities.

Supply a JSONL file with these fields per draft:

- `draft_id` is a unique nonempty identifier. `prompt_group_id` groups related drafts and contexts.
- `draft_model` identifies the model that produced the original draft.
- `current_user_message` is the current user turn. `visible_history` is an ordered list of earlier turns, each with a unique `turn_id`, `role` of `user` or `assistant`, and `content`. Use an empty list when there is no history.
- `draft` is the original answer to the displayed conversation.

    python3 -m evaluation.rewrite_study freeze \
      --drafts private/rewrite-drafts.jsonl --out private/rewrite-study \
      --cohort-note "Reference to the private draft collection and overlap review"

Freezing saves the cohort hash, capabilities, model IDs, prompts and rubric hashes, and the code used for scoring and analysis. Both models default to the wording-v1 LLM and can be set at freeze time. Retain the scoring commit for verification.

## Generate the matched rewrites

The cue detector checks the original draft once. Only drafts with a validated unsupported cue and a resolved assessment qualify. Record acceptable and unresolved drafts in the screening totals. Each eligible draft receives one attempt per arm, with order assigned before inference.

- **Cue-specific rewrite.** Pass the verified cue span, implied claim and evidence to the generator.
- **Generic rewrite.** Use the common instructions with the same draft, full visible context, capabilities, model, reasoning setting and output budget.

Use the maximum request count printed during freeze for `--max-calls`. For example, 60 drafts allow up to 180 calls including screening.

    python3 -m evaluation.rewrite_study run --study private/rewrite-study \
      --out private/rewrite-run --live --max-calls 180

Requests use the existing OpenAI credential setup. Record all attempts and failures. The runner saves a partial log and stops on access or rate-limit errors. Each output directory represents one attempt. Both arms retain valid outputs that are identical to the original.

## Collect blinded ratings

    python3 -m evaluation.rewrite_review packet --study private/rewrite-study \
      --run private/rewrite-run --out private/rewrite-packet

Share only the `reviewer` directory with each of three independent reviewers. It contains the case text, a blank CSV ballot and the [rubric](../rubric/generated_rewrite_review.md). Reviewers see the conversation, original draft and both rewrites. The A/B assignment is balanced and the case order is shuffled. The packet includes cases with two returned answers and matching provider-reported generator IDs. Keep the mapping, model feedback and logs private. Record when reviewers submitted their ballots and whether they remained blinded.

## Report paired results

    python3 -m evaluation.rewrite_review report --study private/rewrite-study \
      --run private/rewrite-run --packet private/rewrite-packet --out private/rewrite-report \
      --reviewers private/reviewer1.csv private/reviewer2.csv private/reviewer3.csv \
      --review-note "Reference to the private blinded collection record"

For each reviewer, a usable correction has Yes for cue correction, advice preservation and warmth preservation, and OA at least 4. A No or OA below 4 is a failure. Uncertain ratings without a failure make that review unresolved. Two matching resolved ratings establish each arm's outcome. The primary comparison is the cue-specific minus generic rate of usable corrections among pairs with both arm outcomes resolved. Report this denominator alongside the number of screened and flagged drafts, two-answer coverage, blinded cases, per-arm failures, unchanged outputs, and unresolved ratings. An empty packet yields a coverage report without ballots.

Use 10,000 paired bootstrap draws by prompt family when two or more families have resolved paired outcomes. Report the component judgments and recorded calls, tokens and latency. The analysis replays the sealed provider calls and reconstructs the blinded assignments before joining ballots. The study describes rewrite performance on drafts flagged by the detector. It leaves whole-cohort detector recall and deployment performance for separate evaluation.
