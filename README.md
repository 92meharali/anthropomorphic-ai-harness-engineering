# Anthropomorphic AI Harness Engineering

This project tests whether a chatbot can correct misleading human-like wording while preserving useful warmth and advice. The proposed harness identifies an exact phrase, checks what it implies against the conversation and trusted system capabilities, and decides whether to keep it, edit it, or hold the answer for review. Our frozen Overall Appropriateness (OA) evaluator checks the whole answer separately.

For example, “You mentioned earlier that writing things down helps” fits when the user said that earlier. When the full available history contains no such mention, the harness can remove the reference and keep the practical suggestion. The main study also tests wording that implies ongoing personal availability. Ordinary warmth is a control for unnecessary edits.

## Current status

- **Available:** the OA runner and protocol, single-revision OA controller, and cue-aware harness with evidence checks, keep/edit/hold routing and a separate OA gate.
- **Held-out comparison:** the full harness matched the reviewer majority on 80/80 fixed pairs. The direct pairwise judge matched 64/80, lower HumT matched 43/80 and frozen OA matched 33/80. See the [six-method report](docs/WORDING_RESULTS.md) for results and study limits.

| Completed pilot | Result |
|---|---|
| Frozen OA on 120 challenge responses | 116/120 (96.7%) agreement with the initial human pass/revise decisions |
| Offline OA controller on 40 drafts | Human-rated passes rose from 35/40 to 40/40. Five drafts were revised. |

The 58 human-revise responses in the 120-case test were constructed. The controller results cover five rewrites. See [pilot results and limits](docs/OA_RESULTS.md) for the earlier model comparison and study details.

## Data and annotation

The [wording dataset](data/wording_pairs_v1.jsonl) contains **60 distinct prompt families, 100 paired cases across contexts, and 200 candidate trials**. The prompts and responses are newly authored adaptations of unused PERSONA scenarios. [Dataset handoff](data/README.md) explains how to prepare a blinded review packet, dry-run the full batch, and import human ratings.

Use the [three synthetic examples](examples/wording_pairs.jsonl) below for a quick smoke check. [Issue #1](https://github.com/92meharali/anthropomorphic-ai-harness-engineering/issues/1) tracks the completed fixed-pair study.

## Run the offline example

Python 3.10+ works with the standard library. The example uses three synthetic pairs, so it needs neither private research data nor credentials.

    python3 -m unittest discover -q
    python3 -m evaluation.wording_harness prepare \
      --pairs examples/wording_pairs.jsonl \
      --protocol rubric/oa_protocol.json \
      --study outputs/wording-demo
    OPENAI_MODEL=gpt-6.2-sol python3 -m evaluation.run \
      --input outputs/wording-demo/oa_inputs.jsonl \
      --protocol outputs/wording-demo/protocol.json \
      --run-dir outputs/wording-demo/oa-dry-run \
      --dry-run

The first command checks the local software. Preparation writes a blinded A/B packet and a private answer key. The scoring dry run builds six OA requests locally. Use a fresh study directory when repeating preparation.

## Research docs

- [Study design, architecture and execution plan](docs/CUE_HARNESS_STUDY.md)
- [Harness engineering and related work](docs/HARNESS_ENGINEERING.md)
- [Wording study runbook](docs/WORDING_HARNESS.md)
- [Held-out wording results](docs/WORDING_RESULTS.md)

Keep study inputs, generated packets, annotation submissions, scoring logs and API keys in ignored local directories. The historical workspace preserves earlier pilot scripts and artifacts.

## Proposed architecture

![Proposed cue-aware harness workflow. The system identifies a cue, checks the evidence, and keeps, edits, or holds the answer before whole-answer OA scoring.]<img width="1726" height="2160" alt="mermaid-diagram (1)" src="https://github.com/user-attachments/assets/a8de52b8-1ab8-46f9-bd87-65f649e12442" />


[Editable Mermaid source](docs/architecture/cue-aware-harness.mmd). In the fixed-pair study, an edit meant selecting a prepared alternative. [Issue #26](https://github.com/92meharali/anthropomorphic-ai-harness-engineering/issues/26) tracks the generated-rewrite experiment.


