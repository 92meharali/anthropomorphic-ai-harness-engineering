# HumT comparison baseline

HumT measures human-like tone. The study scores the candidate text alone and prefers the lower score as a comparison policy. Equal scores predict a tie. The current plan does not use HumT as a required safety or appropriateness test.

This implementation follows the mechanics of the [released scoring script](https://github.com/myracheng/humtdumt/blob/cd677776eff1cc47eadb1d9d4b4be6454a9d52ca/compute_humt_sociot.py): compare He/She against It with quoted text truncated to 300 characters, take the mean negative group loss over 100 dropout passes, and subtract the inanimate group score from the human group score. It retains the released script's scalar batch-loss calculation. This version adds seeded CPU evaluation with the [pinned GPT-2 snapshot](https://huggingface.co/openai-community/gpt2/tree/607a30d783dfa663caf39e06633721c8d4cfcd7e), exact response hashes and run metadata. The seed is derived from the full response so ordering and duplicate contexts do not change the score for an identical answer.

    python3 -m evaluation.humt --smoke

The offline smoke uses artificial group losses to test score direction and response matching. For real scores, use a Python 3.12 environment:

    python3.12 -m venv .venv
    .venv/bin/python -m pip install -r requirements-humt.txt
    .venv/bin/python -m evaluation.humt --input private/study/oa_inputs.jsonl --out-dir private/humt-run --download

The initial download fetches the pinned checkpoint. Future runs can omit the download flag once the snapshot is cached. Model inputs stay local. Evaluate a small development shard first and compare against the released implementation before freezing the held-out scoring protocol. A higher score indicates a larger human versus inanimate contrast, and this direction check by itself establishes no validity on our cases.
