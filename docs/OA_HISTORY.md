# Frozen OA history presentation for wording-v1

The OA baseline uses the original OA prompt and rubric, with model alias gpt-6.2-sol and pass threshold 4. Wording-v1 cases are standalone study items. A case can include one earlier visible user turn from the same chat. The rubric's external-memory limitation still applies.

With one prior turn, the OA input is two lines beginning with “Previous user message: ” and “Current user message: ”. Without prior history, it is the current user message alone. All methods that apply a final OA gate use the same full visible context. Only the cue detector and pairwise guard lose earlier turns in the history-withheld arm. Compare that arm's pre-OA decision separately.

The request includes the rendered prompt and one candidate answer. The host keeps arm names, cue labels, A/B mappings and human ratings outside the model request. Both candidates can be scored once and reused in every arm. The renderer and request builder reject altered text or a changed OA rubric. Record the returned model identifier during inference because a provider alias can move. This pins the study inputs and requested settings.
