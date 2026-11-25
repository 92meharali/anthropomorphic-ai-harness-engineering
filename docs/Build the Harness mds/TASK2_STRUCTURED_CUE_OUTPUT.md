# Build the Harness — Task 2: Structured Cue Output

**Roadmap:** Issue #1. **Status:** Development implementation; offline contract tests passed in an isolated working directory. Integration tests and PR approval remain pending. No live model evaluation is claimed.

## Objective

Translate the approved Task 1 development rubric (`rubric/cue_rubric_v1.md`) into a structured detector interface. Each candidate is assessed independently. The result records exact wording, cue category, implied claim, evidence status, references and a reason. It does not choose an answer or produce an OA or HumT score.

## Inputs and trust boundary

`evaluation.cue_output.state` takes the structured reviewed dataset record, a single candidate response supplied by the caller, and trusted capability values loaded by the host from `data/wording_pairs_v1.manifest.json`. Only the current message, visible turns (IDs, roles, content), candidate response, capabilities and the trusted role rule are sent to the detector. Pair IDs, condition labels, target cue labels, original/edited identifiers, alternate text, flattened prompt, human judgments and model scores are excluded. The caller must not pass labels inside the candidate text. The manifest must be trusted local configuration; the caller must not construct capabilities from user text or detector output.

For the history-withheld condition, `withhold_history=True` removes visible history and sets `visible_history_complete=false` on a copy. The current message, candidate and other capabilities are unchanged. An empty but complete history differs from missing history. The older example format containing only a flattened prompt is intentionally rejected; do not infer structured history from that format. This interface does not alter the OA baseline's presentation (Task 6).

## Output contract

The JSON schema is `rubric/cue_output_schema_v1.json`; `request_body` uses it as a strict OpenAI Responses API output format and includes the approved rubric. The model is supplied by the caller; no model or inference settings are frozen here. `parse_structured` additionally enforces structural and cross-field constraints that the JSON schema does not express.

| Field | Meaning |
| --- | --- |
| `status` | `ok` or `cannot_judge` (whole-assessment abstention) |
| `reason` | Nonempty assessment explanation |
| `cues` | Array of cue objects; `ok` plus `[]` means no detected target cue |
| `cue_type` | `memory`, `availability`, or `warmth` |
| `span` | Smallest exact contiguous wording expressing the claim |
| `occurrence` | Zero-based index of exact substring matches in reading order, counting overlapping matches; resolves repeated wording without model-generated offsets |
| `implied_claim` | Specific implied assertion, or contextual acknowledgement for warmth |
| `evidence_status` | `supported`, `unsupported`, `unclear` |
| `evidence` | Array of source/reference/quote objects; may be empty for unclear only |
| cue `reason` | Nonempty explanation of the evidence judgment |

Each evidence object includes a source, reference and quote. History references an actual `turn_id`; current-user evidence references `current_user_message`. Both require a nonempty exact quotation. Capability references use existing manifest keys and role references use `role.no_genuine_personal_relationship`; both have `quote=null` because the trusted value is resolved from host configuration. Complete-history absence is represented by the `visible_history_complete` capability and an explanation, not a fabricated turn. Separate claims may share a span. No-target-cue cases (A1/W4) use `ok` with an empty cue array, not a new category. Specific uncertainty uses `unclear`, not whole-assessment abstention.

Synthetic supported-memory output:

```json
{
  "status": "ok",
  "reason": "The candidate references an earlier disclosure.",
  "cues": [{
    "cue_type": "memory",
    "span": "You mentioned earlier that making a list helps.",
    "occurrence": 0,
    "implied_claim": "The user previously said making a list helps.",
    "evidence_status": "supported",
    "evidence": [{"source": "history", "reference": "u1", "quote": "Making a list helps."}],
    "reason": "The visible user turn supports this reference."
  }]
}
```

For an absent disclosure under known-complete history, the detector should instead report `unsupported` and cite `visible_history_complete`. If relevant prior turns are masked and no other verified basis resolves the claim, it should report `unclear`. These are rubric expectations, not observed detector performance.

## Offline use

From the repository root, after Task 1 has been merged:

```powershell
python -m unittest evaluation.test_cue_output -v
python -m unittest discover -v
```

To inspect a request without calling an API:

```powershell
@'
import json
from evaluation.cue_output import load_capabilities, request_body
record = {"current_user_message": "What is one small step?", "visible_history": [
    {"turn_id": "u1", "role": "user", "content": "Making a list helps."}]}
request = request_body("example-model", record, "You mentioned earlier that making a list helps.", load_capabilities())
print(json.dumps(request, ensure_ascii=False, indent=2))
'@ | python -
```

The model string above is a placeholder for offline inspection, not a validated API model. `parse_openai` returns explicit refusal/incomplete/failed statuses with `cues=None`, and raises on malformed completed payloads; caller must treat transport or parser errors as unresolved, never as an empty successful result. Nine new contract tests passed in isolation using the approved rubric copy. Existing five repository tests have not been rerun with this change here; run the full suite locally. No API calls or held-out cases were used.

## Task boundary and handoff

Task 2 checks output shape, enum values, evidence object structure, nonempty strings, occurrence type, and no-cue/abstention distinctions. It does **not** check the existence or semantic entailment of cited evidence, actual occurrence offsets, or whether the candidate really contains the claimed cue. Task 3 must validate spans and references against the exact request state, handle errors conservatively, implement keep/edit/hold with unresolved checks taking precedence, verify candidate suitability/content preservation before edit, and record cue routing separately from OA. Task 4 will add full regression fixtures. Do not treat a structurally valid model judgment as verified evidence. No OA protocol, dataset, annotations, source manifest, or Task 1 rubric is modified.

New files: `evaluation/cue_output.py`, `evaluation/test_cue_output.py`, `rubric/cue_output_schema_v1.json`, and this document.
