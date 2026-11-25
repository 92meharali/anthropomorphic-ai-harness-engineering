# Task 5 — Blinded, randomized annotation packet

**Related issue:** #1 — Build, annotate, and evaluate the cue-aware harness  
**Status:** Packet generated and verified; repository review pending. Tasks 3 and 4 are merged. Human preference annotation (Task 6) has not started.  
**Audience:** Research team and repository reviewers. Distribute only the designated blinded handoff files to annotators.

## 1. Objective and scope

Task 5 prepares the approved development response pairs for independent human evaluation without exposing method labels, source identifiers, cue categories, context-condition labels, or model scores. It preserves the approved candidate text and visible conversational context. It does not collect human ratings, determine a preferred response, score candidates with HumT or OA, or validate the proposed context-aware policy.

The existing `evaluation/wording_harness.py` generates the frozen study. The new `prepare_annotator_handoff.py` validates that study against the approved dataset and development allocation, then exports a readable packet and blank ballot. No API calls are needed for either step.

## 2. Approved input and study size

- Allocation: `data/development_split_v1.json` (Task 3).
- Approved pairs: `data/development_reviewed.jsonl` (Task 4).
- Review history: `docs/TASK4_REVIEW.md` and `data/development_content_review.json`.
- Frozen OA baseline protocol: `rubric/oa_protocol.json`.
- Reviewer instructions: `data/REVIEWER_GUIDE.md`.

| Cue category | Families | Paired cases | Candidate trials |
| --- | ---: | ---: | ---: |
| Memory | 4 | 8 | 16 |
| Relationship and availability | 4 | 4 | 8 |
| Ordinary warmth | 4 | 8 | 16 |
| **Total** | **12** | **20** | **40** |

The approved dataset SHA-256 is:

```text
e7a131c007c97e1de003f08a61f3744dca9f59c2c92ff4e1bc406c3e382faaa3
```

Task 5 introduces no response-text changes or new cases. Memory and warmth families retain identical source candidates across their respective sibling contexts. Availability families each have one context. The remaining 48 families are reserved and are not part of this annotation packet.

## 3. Randomization and blinding

The existing harness uses `random.Random(seed)` with the fixed seed recorded in the internal study manifest to shuffle the 20 cases, then shuffles the two candidate labels within each case. It assigns neutral sequential review IDs (`W0001` through `W0020`) in randomized order. These IDs do not identify cue categories.

Each machine-readable reviewer record contains exactly `review_id`, `prompt`, `A`, `B`, and `pair_sha256`. The prompt preserves the rendered visible history and current request. The pair hash is SHA-256 of the UTF-8 encoding of the record excluding the hash field, serialized with `json.dumps(..., sort_keys=True, ensure_ascii=False)`. It binds the case and A/B positions to the ballot.

The coordinator retains a separate key linking review IDs to the source pair, family and cue category and mapping A/B to `original`/`edited`. These labels and model-scoring inputs are excluded from reviewer materials. The same frozen case order and A/B assignment are used for all three annotators, so the existing analysis harness can compare their judgments directly.

## 4. Reproduction instructions

Run from the repository root using PowerShell. The directories must be fresh: both scripts refuse to overwrite existing output directories. The commands are reproduction instructions, not a request to regenerate an already frozen study.

```powershell
$env:PYTHONUTF8 = "1"
Get-FileHash data/development_reviewed.jsonl -Algorithm SHA256
# For authorized reproduction, use the seed recorded in the retained internal manifest.
$seed = Read-Host "Enter the recorded study seed"
python -m evaluation.wording_harness prepare --pairs data/development_reviewed.jsonl --protocol rubric/oa_protocol.json --study private/task5-study-v1 --seed $seed
python prepare_annotator_handoff.py
```

Confirm the input hash matches Section 2 before preparing a study. UTF-8 mode prevents the Windows default-encoding issue in the existing file helpers. The approved dataset has an LF line-ending rule in `.gitattributes`; preserve it. If either output directory already exists, retain the frozen files. A `WinError 183` on a repeated invocation indicates that the destination already exists, not that the initial successful generation failed.

The harness records byte-level hashes of its generated files in `manifest.json`. Text file line endings may vary across operating systems; compare a study against its own manifest rather than assuming all generated file bytes match another platform. The source dataset hash and canonical per-pair hashes must remain consistent. Preserve the exact bytes of any published annotation artifacts with the Git attributes rule `data/annotation/** -text`. Copy frozen files rather than regenerating them for publication.

The handoff utility checks the approved source hash, selected pair IDs, cue counts, family grouping, sibling candidate consistency, manifest file hashes, seeded ordering, A/B mapping, pair hashes, reviewer field whitelist and exact OA input alignment before exporting.

## 5. Output files and access restrictions

The preparation scripts generate the complete frozen study and blinded handoff locally. The research coordinator retains the experimental mapping and internal study records separately. Only the designated blinded materials and protocol are eligible for repository publication; the complete study is available to authorized research colleagues through an internal handoff.

### Internal study (`private/task5-study-v1/`)

| File | Purpose | Repository publication |
| --- | --- | --- |
| `manifest.json` | Frozen seed, source and output hashes, baseline configuration and pair count. | Internal only |
| `review_packet.jsonl` | Canonical blinded cases for validation and later analysis. | Eligible after annotation |
| `pair_key.jsonl` | Source identifiers and A/B-to-version mapping. | Internal only |
| `oa_inputs.jsonl` | 40 candidate scoring inputs for subsequent frozen OA evaluation. | Internal only |
| `protocol.json` | Copy of the frozen OA baseline protocol. | Eligible |

### Annotator handoff (`private/task5-annotator-handoff/`)

| File | Purpose | Repository publication |
| --- | --- | --- |
| `REVIEWER_GUIDE.md` | Short instructions and study capability assumptions. | Eligible |
| `review_packet.md` | Human-readable rendering of all 20 blinded cases. | Eligible after annotation |
| `ballot.csv` | Blank answer sheet with the 20 review IDs and pair hashes. | Eligible after annotation |

Give each annotator only a separate copy of the three handoff files. Do not distribute the internal study directory, Task 4 review, source dataset, this document, model scores, randomization details or the GitHub repository to annotators. The canonical JSONL packet is blinded but need not be distributed because the Markdown version is provided.

The methodology, utility, reviewer guide and frozen OA protocol can be version-controlled for research transparency. To protect the frozen assignments during collection, defer public release of the case-specific packets and blank ballot until independent judgments have been submitted. Retain the mapping, internal manifest, OA inputs, completed ballots, personal reviewer records and raw scoring logs outside public version control. Directory names alone do not enforce access restrictions; use a restricted research-team channel for internal sharing.

## 6. Annotation rubric and response format

Annotators judge each case independently using the displayed conversation. For this simulated chatbot, assistance is available within the current chat; it cannot see earlier sessions, initiate a check-in or guarantee future availability. Ordinary emotional acknowledgement can fit a conversation. Annotators should not assume that either more or less human-like wording is automatically preferable.

| Judgment | Question | Allowed ballot values |
| --- | --- | --- |
| `preference` | Which answer's wording fits this situation better? | `A`, `B`, `tie`, `cannot_judge` |
| `cue_needs_correction` | Which answer contains an unsupported claim, unavailable capability or relationship, or other wording that needs meaningful correction? | `A`, `B`, `both`, `neither`, `cannot_judge` |
| `content_preserved` | Do both answers preserve the same practical advice, important facts and relevant caveats? | `true`, `false`, `null` (uncertain) |

A tie means both wordings fit about equally well; it is different from inability to judge. Preference and need for correction are separate judgments: an answer can be less preferred without requiring correction. These are not direct ratings of perceived humanness, relationship or attachment.

The CSV columns are `review_id,pair_sha256,preference,cue_needs_correction,content_preserved`. IDs and hashes must remain unchanged; treat them as text if using a spreadsheet. All three judgment fields start blank. A blank field is not an abstention: use the explicit allowed value when uncertain.

## 7. Verification outcome

The local preparation and handoff commands completed successfully. The coordinator's local terminal reported that the source, allocation, frozen file hashes, candidate inputs, mappings, pair hashes and blinded fields passed validation. A second run correctly refused to overwrite the existing directories.

Independent inspection of the six supplied study/handoff files established the following:

| Check | Outcome |
| --- | --- |
| Source SHA-256 and exact Task 3 pair allocation | Pass |
| 20 unique cases and all 40 approved candidate texts | Pass |
| Seeded case order and all A/B assignments | Pass |
| Uploaded packet and key byte hashes against manifest | Pass |
| All 20 canonical pair hashes | Pass |
| Reviewer record fields restricted to whitelist | Pass |
| OA input hash reconstructed from 40 mapped candidates using Windows CRLF line endings | Pass |
| Markdown packet, copied guide and CSV reproduced byte-for-byte from supplied packet and guide | Pass |
| CSV has 20 matching review IDs/hashes and no prefilled judgments | Pass |

The actual `oa_inputs.jsonl` and `protocol.json` files were not supplied for independent byte inspection. Their local hash validation was reported as successful; the OA input hash was independently reconstructed, but the protocol file itself was not independently checked in this inspection. No human ratings or model results were used in preparation or verification.

## 8. Task 6 handoff and collection plan

1. Confirm repository review/merge, internal separation of the study materials and any applicable research ethics or consent requirements before collecting judgments.
2. Select three independent human annotators who have not seen the answer key, source labels or Task 4 correction rationale. Prefer annotators other than the content reviewer and coordinator.
3. Assign neutral annotator identifiers (for example R01, R02 and R03). Send each the same three handoff files in separate copies. Instruct them not to consult the repository, other annotators or AI tools for judgments, and to record their own first assessments.
4. Receive one completed ballot per annotator, each covering all 20 cases. Store the original submissions privately and unchanged before any discussion or adjudication. Record any reported exposure to coordinator materials before analysis.
5. Validate the 20 IDs, pair hashes and all allowed values in each submission. Convert valid CSV judgments to the JSONL schema expected by `evaluation.wording_harness analyze`, mapping the content-preservation strings to JSON booleans or null. Preserve explicit ties and cannot-judge responses. Ballot import/conversion is Task 6 work, not implemented by the Task 5 export script.

Expected collection: **3 annotators × 20 pairs = 60 pair judgments**, comprising 180 individual question responses if all ballots are complete. These are planned counts, not observed results. The later analysis harness expects three independent reviewer JSONL files covering the frozen packet. OA and HumT scoring are separate from annotation; do not expose scores to annotators. Task 7 will examine disagreement while retaining the original judgments.

## 9. Methodological limitations

- Independent random assignment produced an unequal distribution of original response positions across A and B. The exact allocation is retained in the internal study record. This is not an error, but it may interact with positional bias. Retain the frozen development packet; do not selectively rerandomize. Consider prespecified balancing or counterbalancing for the held-out study.
- All three annotators receive the same ordering. Repeated scenarios across sibling contexts may be recognized, so observations are not fully independent at the pair level. Retain family identifiers privately for later family-level analysis.
- Method-label blinding does not hide the visible linguistic differences. Blinding depends on controlled distribution and annotator compliance; it is not a guarantee of complete concealment. Annotators must not consult the source dataset or study implementation during collection.
- Memory and warmth allow cue-by-context comparisons; single-context availability families do not. Practical contexts lack explicit distress, rather than proving emotional neutrality. Memory also varies grounding and personalization. These Task 4 limitations still apply.
- The development set is small and is intended for refinement, not confirmatory generalization. These judgments evaluate wording preference, correction need and content preservation; they do not establish perceived humanness or validate a computational measure. Claims about perceived relationship or humanness would require a separate suitable blinded task as specified in Issue #1.

## 10. Repository submission

The Task 5 preparation PR should include:

- `prepare_annotator_handoff.py` — verification and export utility at the repository root.
- `docs/Prepare and annotate the development set mds/TASK5_ANNOTATION.md` — this methodology and handoff record.
- `data/annotation/annotator/REVIEWER_GUIDE.md` — the generated reviewer instructions.
- `data/annotation/coordinator/protocol.json` — the frozen OA baseline protocol; this is not an answer key.
- `.gitattributes` — preserve the byte-level integrity of annotation artifacts with `data/annotation/** -text`.

After independent annotation has concluded, the following frozen blinded artifacts may be added for reproducibility, subject to the research team's publication approval:

- `data/annotation/coordinator/review_packet.jsonl`
- `data/annotation/annotator/review_packet.md`
- `data/annotation/annotator/ballot.csv` (blank template only)

Do not commit `pair_key.jsonl`, `manifest.json`, `oa_inputs.jsonl`, completed individual ballots, personal reviewer information or raw model logs to the public repository. Keep the full internal study under `private/task5-study-v1/` and the original handoff under `private/task5-annotator-handoff/`. The existing `data/REVIEWER_GUIDE.md` and `evaluation/wording_harness.py` are reused unchanged.

Task 5's technical deliverables are ready for repository review. Mark the issue's Task 5 checkbox complete after review/merge; leave Task 6 and Task 7 unchecked until their respective work is done.
