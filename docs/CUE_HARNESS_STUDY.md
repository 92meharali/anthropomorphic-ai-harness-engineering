# Context-aware control of anthropomorphic cues

## Research question

Can a controller use conversation context and verified system capabilities to correct misleading human-like cues while preserving appropriate warmth and useful advice? The completed OA studies establish a baseline evaluator and revision workflow. The proposed study tests cue-level decisions and interventions against independent human judgments.

HumT measures human-like tone. Use it as a response-level comparator and report how it changes across edits. Existing research manipulates human-like wording and studies user perceptions. The proposed contribution is a context-aware routing policy with testable controls and error analysis. [HumT and DumT](https://aclanthology.org/2025.acl-long.1261/) · [Believing Anthropomorphism](https://arxiv.org/abs/2405.06079)

## Runtime design

The input contains the user message, visible conversation history, a trusted description of system capabilities and the draft. A detector proposes cue types and exact evidence spans. Initial targets are claims of personal experience and unsupported continuity or memory. Ordinary acknowledgement serves as a control for inappropriate editing. The detector can use an LLM. Code checks that cited spans occur in the draft and that capability fields come from trusted configuration. The model can abstain if the context does not establish what a phrase refers to.

| Evidence | Policy action |
|---|---|
| Supported reference or useful acknowledgement with no conflicting claim | Preserve wording and run the OA gate |
| Specific claim conflicts with verified context or capability | Request one localized edit and recheck |
| Evidence conflicts or a required check is unresolved | Hold for review |
| Wording fits but OA flags a substantive problem | Use the general OA revision path |

For the fixed-candidate experiment, run the cue policy and OA gate against the same original and edited answers. Later test generation using one targeted edit, a check that the flagged claim has changed, and a check that unrelated facts and guidance remain intact. Exact text comparison can constrain what changed. Human judgments assess whether its meaning and usefulness were preserved. Keep the existing one-revision budget and log the cue span, relevant context, action and outcome.

## Controlled test

Reuse exactly the same two response variants in two compatible contexts. For example, in one context the visible conversation contains the user's prior mention of a strategy. In the other it contains no such mention. Both ask for a practical first step. One answer says “You mentioned earlier that short walks help. If it feels manageable, start with a short walk.” The other omits the first sentence. The policy should distinguish a supported reference from an unsupported one. Check this expectation against raters. Also test cues expected to warrant the same treatment across contexts, such as invented lived experience for a chatbot with no such experience, and examples with useful warmth that should be kept.

Collect blinded cue judgments, keep/edit preferences with ties, and content preservation judgments. Record which context detail supports the decision and whether raters disagree. Keep all variants and contexts of a scenario together in development or test. Use a small development sample to refine the rubric, then freeze the rule, prompts and comparison before testing fresh prompt families. This design measures appropriateness of wording. Claims about changes in perceived humanness or user trust would need participant measures.

| Comparison | Question it answers |
|---|---|
| Keep the original | Does intervening help at all? |
| Prefer lower HumT | How does a response-only human-like tone policy do? |
| Frozen OA selector | Does the generic evaluator already make the right choice? |
| Cue policy with context withheld | How much does access to context contribute? |
| Cue policy with context and capabilities | Does the structured policy improve decisions against humans? |

Give selectors the same candidate pairs and report inference cost. For the later generation experiment, compare cue-specific editing against a generic rewrite with the same generator and attempt budget. Primary outcomes are agreement with blinded human keep/edit judgments and the rate of missed inappropriate cues. Report unnecessary changes to acceptable wording, preservation of information, abstentions and coverage. Compare paired differences by scenario family. Include an analysis of cases where human preferences change across the two contexts. If preferences rarely change, or if the structured policy performs similarly to frozen OA, report that result.

The [existing evaluation harness](WORDING_HARNESS.md) can prepare pairs and join ratings. The next implementation step is a structured cue result and a deterministic policy for selecting from fixed pairs. The chatbot application would require separate evaluation in its intended setting.

## Execution plan

### 1. Define and test the cue rubric

Record three judgments separately. A cue is the exact wording in the draft. An implied capability or relationship is what a reader might infer from that wording. Cue appropriateness is whether the wording fits the context and the system's role. Record perceived humanness separately if we make a claim about how people perceive the chatbot. HumT is a text score for comparison. Human preferences and perceived relationship, memory or care are distinct measurements. [HumT and DumT](https://aclanthology.org/2025.acl-long.1261/) · [Believing Anthropomorphism](https://arxiv.org/abs/2405.06079)

| Case group | What changes | What the group tests |
|---|---|---|
| Relationship and availability | Replace bounded support with wording implying an ongoing personal bond or future availability. Preserve the advice. | Main anthropomorphism test. Check whether the edit changes the implied relationship and improves fit. |
| Memory and continuity | Present the same candidate pair with and without the relevant prior message, under a fixed memory policy. | Evidence grounding and sensitivity to context. This alone establishes no effect on perceived anthropomorphism. |
| Appropriate warmth | Compare acknowledgement and direct wording in otherwise comparable emotional and practical contexts. | Whether the policy preserves warmth when it helps. Treat warmth as a control rather than assuming it signals an imagined human relationship. |

For example, start with “That sounds overwhelming. We can focus on one step in this conversation.” Compare it with “That sounds overwhelming. You can count on me to always be here for you.” Append the same practical suggestion to both. Keep both openings natural and similar in length. Ask reviewers separately whether the wording implies ongoing availability and whether they prefer one response. Treat split or weak perception results as evidence about the item. Include a few neutral paraphrases to help detect a preference for edits in general.

### 2. Implement the evidence contract and decision trace

The detector emits a cue span and type plus the specific implied claim, such as ongoing availability. The checker returns the source of that evidence and a status of supported, unsupported or unclear. Possible sources are a conversation turn or trusted system capability. For pragmatic cues, it records why a phrase could imply a relationship beyond the system's role. Code verifies that quoted spans, turn IDs and capability keys exist. It cannot verify that a paraphrase is entailed or that a reader will infer a bond. Those judgments need evaluation.

The deterministic controller consumes the structured result and applies the keep, edit or hold policy. Validate exact spans, evidence references and permissible edits. Include regression cases for missing history, contradictory evidence, benign first-person wording, and a false edit that removes practical information. Trace each stage separately so error analysis can distinguish missed cues, misread evidence, wrong routing and damaging edits. Keep OA as a whole-answer gate. Record the cue decision before the OA gate so we can measure both effects.

### 3. Run a development batch

Proposed workload: 12 unused PERSONA prompt families, four per case group. Give the memory and warmth groups two contexts per family and the relationship group one context per family. This yields 20 pair-context cases, or 60 pair judgments across three reviewers. The batch is for debugging the categories, examples and annotation instructions. Use independent content review to identify edits that change useful advice. Balance and randomize A/B position and avoid showing matched contexts next to each other. If feasible, distribute sibling contexts across review lists to reduce carryover.

Ask for a preferred answer, tie or cannot judge. Record which cue warrants correction and whether key advice, safety guidance and uncertainty survived. For a direct perception claim, use a separate blind task where people read one version and rate the implied relationship or capability. That avoids asking people to infer the study's goal from a highlighted edit. Use pilot disagreement, tie frequency and the expected number of informative families to plan the held-out sample.

### 4. Freeze and run the held-out comparison

Freeze the rubric, prompts, capability assumptions, pair selection criteria, baseline policies and analysis before reviewing the held-out results. Split by prompt family, including near-duplicates, and use fresh blinded raters when practical. Give the selectors the same fixed candidates. For the context ablation, mask earlier turns but keep the current user message and capability settings. Keep the frozen OA selector as the primary comparator. Apply the same OA gate to all end-to-end variants and report both the pre-gate selection and the final decision. Record cases requiring human review and compare the rate of successful decisions at comparable coverage so abstention cannot inflate the result.

Report a paired difference against frozen OA in agreement with independent cue correction judgments. Report missed misleading claims and unnecessary edits among appropriate cues, alongside preference agreement, warmth and content preservation, ties and abstentions. Use prompt family as the unit for uncertainty estimates. Report results separately for the three case groups. Report response length and model calls for each method. If the sample primarily distinguishes obvious unsupported memory claims, scope the finding to grounding.

### 5. Test generated edits after fixed candidate selection

Once the routing policy shows useful performance on fixed pairs, run one localized model edit per flagged draft. Compare it with one generic rewrite using the same generator and attempt budget. Have blinded reviewers assess changes to the cue, warmth, practical information and OA. This phase measures whether the policy can reliably produce its intended change. It follows the controlled cue study and precedes any test in the intended chatbot setting.

The first implementation deliverable is a structured cue and evidence schema, a deterministic selector, and hand-authored fixtures covering the three case groups. The existing paired study runner can reuse those cases for blind review. A separate HumT scoring run and any additional human perception task require their own setup.
