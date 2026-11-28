# Issue #26 Task 3 — Blinded Excel review (v2)

Depends on Tasks 1 and 2. Replaces the earlier text/CSV handoff completely. Reviewers receive and return only native `.xlsx` workbooks. No Excel COM, desktop Excel installation or conversion script is required on the coordinator's machine; the runner uses the pinned Python dependency in `requirements-rewrite-review.txt`. JSON/JSONL files are internal restricted research artifacts, not reviewer forms. No model calls or treatment-effect calculations occur in this stage. The frozen rubric, seed, eligibility rule and primary outcome are unchanged.

## 1. Install and test

PowerShell, from the repository root:

```powershell
$env:PYTHONUTF8 = "1"
python -m pip install -r requirements-rewrite-review.txt
python -m unittest evaluation.test_rewrite_blind -v
python -m unittest discover -q
```

Eleven Task 3 tests cover balanced randomization, literal and long text, native XLSX collection and replay, changed text/rubric, invalid and missing ratings, formulas, incorrect reviewer IDs, hashes, hidden rows, provenance, tampering, empty packets, failure exclusions and no overwrite. Mocked tests are not experimental results. Do not publish private files.

## 2. Prerequisites and packet preparation

Use the actual independently approved freeze SHA-256 from Task 1; do not substitute an invented value or merely trust a hash calculated from an unapproved file. A complete replay-verified Task 2 generation run must exist. If the live study has not been run, follow `GENERATED_REWRITE_FREEZE.md` and `GENERATED_REWRITE_GENERATION.md` first, after coordinator sign-off. Do not replace original cases to increase flagged counts.

```powershell
$freeze = "ACTUAL_APPROVED_FREEZE_SHA256"
python -m evaluation.rewrite_generate verify --study private/issue26-frozen --freeze-sha256 $freeze --out private/issue26-rewrites
python -m evaluation.rewrite_blind prepare --study private/issue26-frozen --run private/issue26-rewrites --freeze-sha256 $freeze --packet private/issue26-review-packet
```

Output includes `packet_sha256`, `screened`, `flagged`, `eligible_pairs`, and reviewer codes. Independently record the actual packet SHA-256 in the coordinator's private record before distributing workbooks. Use a new output directory; existing packet directories are never overwritten. If an earlier packet was distributed, do not silently re-randomize or change it: coordinate a documented migration before starting or continuing review. The older packet format is not compatible with this version.

All and only replay-eligible pairs enter the packet (two valid rewrites with matching nonempty provider-reported generator IDs). Unchanged and identical answers are retained. Case order is shuffled, A/B positions balanced within one, with the frozen seed 20261128. All three reviewers see the same assignments and order; no arm, cue feedback, draft/family ID or model label is added to reviewer materials. Generated text is not edited; if the content itself reveals a method, document that privately and do not silently redact or exclude it. Exact source text is bound in the private case hashes; the workbook uses LF line breaks for display and splits long text across rows without changing wording. Share no mapping or seed with reviewers.

## 3. Reviewer handoff

```text
private/issue26-review-packet/
  manifest.json
  cases.jsonl
  key.jsonl                     # private method mapping
  reviewers/
    Generated_Rewrite_Annotation_R01.xlsx
    Generated_Rewrite_Annotation_R02.xlsx
    Generated_Rewrite_Annotation_R03.xlsx
```

Send only the single designated workbook to each reviewer through a restricted channel. Preserve the generated blank originals. Each workbook contains a Review sheet with instructions, context, original draft, anonymous A/B answers, and eight blue rating cells per case; a Rubric sheet contains the complete frozen evaluation rubric. Reviewers should read the rubric, rate A and B separately, select Yes/No/Uncertain for the three binary fields and 1–5/Uncertain for OA. Use Uncertain only where the rubric allows; leave no blanks. Do not change text, worksheet layout, IDs or hashes. Worksheet protection helps avoid accidental edits; it is not security. Workbooks include dropdown validation; the importer independently validates every cell. Open and save as `.xlsx`, not another format. Return the completed workbook without discussing judgments or viewing other ballots.

Keep identity-to-code mapping, submission records and independent/blinded attestations in restricted coordinator storage. Git ignore is not access control; configure suitable permissions. Do not give reviewers the key, packet manifest, provider traces, repository seed or other reviewers' files. No spreadsheet contains a hidden method mapping. Workbooks have no formulas, macros or external links. Native Excel saves may alter ZIP metadata or formatting; returned files are checked semantically for exact non-rating content, layout, correct reviewer, allowed ratings and complete coverage, not byte-equality to a blank workbook. Extra sheets/rows, formulas, hidden rows/columns and changed rubric or text are rejected.

## 4. Verify the packet, collect returned Excel workbooks

Record the packet seal independently. The original blank workbooks are checked against exact sealed bytes and reconstructed content (Excel ZIP timestamps need not reproduce across runs).

```powershell
$packet = "ACTUAL_RECORDED_PACKET_SHA256"
python -m evaluation.rewrite_blind verify-packet --study private/issue26-frozen --run private/issue26-rewrites --freeze-sha256 $freeze --packet private/issue26-review-packet --packet-sha256 $packet
New-Item -ItemType Directory -Force private/issue26-submissions
```

Save returned workbooks as `private/issue26-submissions/R01.xlsx`, `R02.xlsx`, `R03.xlsx`. Keep blank originals untouched. Create `private/issue26-submissions/provenance.json` using real private record references and truthful attestations. Example only:

```json
{
  "record_reference": "actual coordinator record reference",
  "reviewers": {
    "R01": {"submission_reference": "actual R01 submission record", "independent": true, "blinded": true},
    "R02": {"submission_reference": "actual R02 submission record", "independent": true, "blinded": true},
    "R03": {"submission_reference": "actual R03 submission record", "independent": true, "blinded": true}
  }
}
```

```powershell
python -m evaluation.rewrite_blind collect --study private/issue26-frozen --run private/issue26-rewrites --freeze-sha256 $freeze --packet private/issue26-review-packet --packet-sha256 $packet --collection private/issue26-review-collected --ballots private/issue26-submissions/R01.xlsx private/issue26-submissions/R02.xlsx private/issue26-submissions/R03.xlsx --provenance private/issue26-submissions/provenance.json
```

The collector validates native Excel files directly, without exporting or importing CSV. The output includes `collection_sha256`, `reviewers`, `cases`, `reviewer_case_ratings` (3 times eligible pairs) and `state`. Record the actual collection seal independently. If there is an invalid or missing rating, ask that reviewer to correct their own workbook without exposing other ratings. A failed validation does not create a completed collection. If independence or blinding is unconfirmed, do not falsely attest; consult the coordinator and document the deviation. The code checks attestation structure, not actual human conduct.

```powershell
$collection = "ACTUAL_RECORDED_COLLECTION_SHA256"
python -m evaluation.rewrite_blind verify --study private/issue26-frozen --run private/issue26-rewrites --freeze-sha256 $freeze --packet private/issue26-review-packet --packet-sha256 $packet --collection private/issue26-review-collected --collection-sha256 $collection
```

The collection contains `manifest.json`, original returned `ballots/R01.xlsx` etc., `ratings.jsonl` and `provenance.json`. The normalized rows preserve the prior Task 3 interface (`reviewer_id`, `review_id`, `case_sha256`, `A`, `B`, each with the four frozen rubric fields). Yes/No map to true/false, OA to integer and Uncertain to null. Task 4 can call `verify_collection` and join the private key on review ID and case hash. The verification replays Task 2 and checks the original workbooks, submitted workbook bytes and normalized judgments. Do not compute or disclose arm-level results yet.

If eligible pairs = 0, no reviewer workbooks are generated. Record a real no-review provenance reference with `reviewers: {}`, omit `--ballots`, and expect `no_eligible_pairs`, zero ratings. The primary effect is not estimable. A stopped Task 2 run cannot produce a review packet at all.
