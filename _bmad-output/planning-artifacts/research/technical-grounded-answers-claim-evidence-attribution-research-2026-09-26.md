---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments: []
workflowType: 'research'
lastStep: 1
research_type: 'technical'
research_topic: 'Grounded answers and claim-evidence attribution for GenAI agents'
research_goals: 'Redesign ShiftMind grounding contract and make verification smarter; cover all claim kinds (numeric, entity, status, relational), not just numbers; compare deterministic, model-based and hybrid verification options to choose from; survey how other GenAI systems represent claims and evidence in an answer, and include the tentative inline-markup idea (<claim evidence="id">...</claim>) as one candidate among them, not as the assumed direction'
user_name: 'Minh'
date: '2026-09-26'
web_research_enabled: true
source_verification: true
---

# Research Report: technical

**Date:** 2026-09-26
**Author:** Minh
**Research Type:** technical

---

## Research Overview

This research asks how ShiftMind should ground its assistant's answers once the current
"no untraceable numerals in prose" rule is replaced by something more flexible and broader — a
contract covering every kind of claim (quantities, record facts, statuses, relations), verifying both
the cited evidence ID **and** the content it supports (decision D1). It surveys how production GenAI
systems represent answer–evidence links (Anthropic, OpenAI, Gemini, Cohere, Agentforce), which
verification technologies exist (deterministic, NLI models, decision models such as TypeSafe Jev,
LLM judges, managed grounding APIs), and how each fits ShiftMind's constraints: output-tool answers,
an OpenRouter-hosted model, AR11's trust boundary, and keyless CI.

The central finding is that ShiftMind's evidence is structured records, so most claims can be checked
deterministically — an advantage vendor citation features, built for documents, do not exploit.
Vendor-native citations do not fit (provider-specific; incompatible with structured output on
Anthropic), and no model-based checker recomputes a count. The recommended design is a phased hybrid
(**G′**): application-rendered numbers (`{{r1}}`), inline attribute-checked claims
(`<claim ev='w3' field='…' value='…'>…</claim>`), a calibrated decision model for wording, and
failure policies that degrade one claim instead of the whole turn.

Method: current web sources (vendor documentation, peer-reviewed and preprint papers, independent
evaluations) cross-checked against ShiftMind's code. See **Research Synthesis › Executive Summary**
for the full summary and recommendation.

---

<!-- Content will be appended sequentially through research workflow steps -->

## Technical Research Scope Confirmation

**Research Topic:** Grounded answers and claim-evidence attribution for GenAI agents
**Research Goals:** Redesign ShiftMind's grounding contract and make verification smarter; cover all claim kinds (numeric, entity, status, relational); compare deterministic, model-based and hybrid verification options; survey how other GenAI systems represent claims and evidence, with the tentative inline-markup idea (`<claim evidence="id">…</claim>`) as one candidate among them.

**Technical Research Scope:**

- Architecture Analysis - answer/evidence representations (inline markers, span offsets, cited content blocks, claim lists, application-rendered values, inline tags) and where verification sits
- Implementation Approaches - emission formats, deterministic matching, NLI/entailment, LLM-as-judge, decomposition-based verification
- Technology Stack - vendor grounding APIs and guardrail frameworks
- Integration Patterns - mapping onto `gate.py`, AR11 trust boundary, evidence refs, keyless CI stub, streaming
- Performance Considerations - latency, cost, retry rate, false positive/negative profiles

**Research Methodology:**

- Current web data with rigorous source verification
- Multi-source validation for critical technical claims
- Confidence level framework for uncertain information
- Comprehensive technical coverage with architecture-specific insights

**Scope Confirmed:** 2026-09-26

### Decisions Recorded During Research

- **D1 (2026-09-26, Minh): verify both the evidence ID and the content it wraps.** A citation whose ID
  resolves but whose record does not support the stated content must fail. ID existence alone is
  insufficient (citation laundering / mis-attribution — see Integration Patterns › Security).
- **D2 (2026-09-27, Minh): verification comes from tags, not from heuristics on untagged text.**
  Untagged prose is connective text and is treated the same whether it holds a number, a name, or
  neither — a lexical numeral rule guards one kind of fact while invented names pass, so it is not
  kept. Every fact the planner should trust goes in `<claim>` or `{{r}}`. Untagged prose is
  unchecked in phase 2 (option a) and gets a **flag-only** semantic scan against the turn's evidence
  once the tier-1 checker exists (option b); it never blocks a turn. **FR7 and NFR12 are reworded** (corrected
  2026-09-27 — AR11, which requires locators and calculators, is unaffected): "unsupported numbers
  must fail grounding" / "100% of numerical claims must pass" now apply to numbers *presented as
  verified* (`{{r}}` and tagged claims); untagged text is presented as unverified. Accepted risk: a model ignoring instructions can show a plain-text number
  or name that some planners read as fact until the flag-only scan ships.
- **D3 (2026-09-27, Minh): phase 0 (ordered-list-marker fix to the numeral rule) is dropped.** Under
  D2 the numeral rule is removed in phase 2, so a patch to it would be deleted code.

## Technology Stack Analysis

> Adapted to the topic: the template's language/database/cloud sections do not apply to a
> grounding-contract question, so this section maps the *grounding technology landscape* instead —
> answer/evidence representations, vendor grounding APIs, verification models, and guardrail
> frameworks — and ends with what each means for ShiftMind's current stack
> (`pydantic-ai-slim[anthropic,google,openrouter]==2.27.0`, output-tool answers, OpenRouter-hosted
> live model, keyless CI double).

### Answer/Evidence Representations in Use Today

Six distinct shapes are in production use. They differ in **who writes the link between text and
evidence** (the model, or the application) and **at what granularity**.

| # | Shape | Who emits the link | Granularity | Production examples |
|---|---|---|---|---|
| R1 | **Cited content blocks** — answer is a list of text blocks, each carrying a `citations[]` list | Model (API-parsed) | Block ≈ sentence/claim | Anthropic Citations (`char_location`, `page_location`, `content_block_location`, `search_result_location`) |
| R2 | **Span-offset metadata** — plain answer text + a side structure mapping `[startIndex,endIndex)` to evidence indices | Model or post-hoc service | Arbitrary span | Gemini `groundingSupports` → `groundingChunkIndices`; OpenAI `output_text.annotations` (`url_citation`/`file_citation` with `start_index`/`end_index`); Cohere `citations` with `start`/`end`/`document_ids` |
| R3 | **Inline citation markers** — reserved tokens in the text, parsed and stripped by the app | Model | Block (recommended) or line | OpenAI Citation Formatting guide: `cite<source_id><locator>` |
| R4 | **Separate claim list** — answer text plus an extracted list of atomic claims, each verified against evidence | Post-hoc extractor (LLM) | Atomic claim | RAGAS faithfulness, Claimify, FActScore-style pipelines, Vertex check-grounding `claims[]` |
| R5 | **Application-rendered values** — the model never emits the data value; it references an action/result and the platform renders it | Application | Value / component | Salesforce Agentforce `render:` directive; "LLM never calculates a statistic" data-analyst agents |
| R6 | **Inline XML claim tags** — `<claim evidence="id">…</claim>` wrapping the asserted span | Model (prompted, app-parsed) | Claim span | No first-party vendor API found; closest are Anthropic's prompt-level `<quote>`/scratchpad guidance and R3's reserved-token markers |

_Key observation:_ every vendor API that ships citations (R1, R2) returns **evidence the application
supplied**, and the vendor guarantees the cited text is extracted, not generated — Anthropic states
`cited_text` "is extracted from the document rather than generated, so it is guaranteed to point at
real source text". None of them verifies that the claim is *entailed* by the cited text; that is a
separate product (see Verification Models). **R6 is essentially R3 with a closing tag** — the
open/close pair is what lets it delimit *which* words the evidence supports, which R3's point marker
cannot.
_Confidence: high for R1–R3 (first-party docs); high for R4 (docs + papers); medium for R5 (one
vendor engineering blog + practitioner write-ups); R6 "no vendor API" is an absence-of-evidence
finding — medium._
_Sources: https://platform.claude.com/docs/en/build-with-claude/citations ·
https://ai.google.dev/gemini-api/docs/generate-content/google-search ·
https://developers.openai.com/api/reference/typescript/resources/responses ·
https://docs.cohere.com/docs/rag-citations ·
https://developers.openai.com/api/docs/guides/citation-formatting ·
https://engineering.salesforce.com/how-agentforce-achieves-100-deterministic-rendering-for-ai-agent-ux/_

### Vendor Grounding APIs (Generation-Side)

- **Anthropic Citations** — GA on all active models. Documents (`text`, PDF, `custom_content`) or
  `search_result` blocks returned *from custom tools* can be cited; the response is split into text
  blocks, each with citations; streamed as `citations_delta`. `cited_text` costs no output tokens.
  **Hard limitation:** "Citations and structured outputs are incompatible … the API returns a 400
  error", because citations interleave with text. Citations attach to *text* blocks, so an answer
  delivered as output-tool JSON arguments (ShiftMind's `answer` tool) would carry none — _inference,
  medium confidence_. PydanticAI has an open request for tool-result citation support (issue #2128);
  the Agent SDK drops `search_result` blocks from custom tools (issue #574).
- **OpenAI** — `output_text.annotations` with character offsets for its own file/web search tools;
  for *custom* sources, the published Citation Formatting guide prescribes model-emitted reserved-token
  markers (R3), app-side regex parsing, stable source IDs matching `[A-Za-z0-9_-]+`, block-level
  granularity by default, and "Never invent source IDs … that were not returned by the tool". Invalid
  markers are skipped by the reference parser.
- **Gemini** — `groundingMetadata.groundingSupports` (segment offsets → chunk indices), available for
  Google Search / Vertex Search / Elasticsearch / custom-search grounding, i.e. tied to Google's
  retrieval tools rather than arbitrary tool results.
- **Cohere** — document `id`s supplied by the caller become citation `document_ids`; `citation_options.mode`
  `accurate` (post-hoc alignment after the full answer, default) vs `fast` (inline, lower latency);
  also supported for tool-use results.

_Pattern:_ all four put the **evidence ID space under application control** (caller-supplied IDs or
tool results) and have the model only *reference* it. That is the same principle as ShiftMind's
`result_id`; what differs is granularity and that they cover *all* text, not just numbers.
_Sources: https://platform.claude.com/docs/en/build-with-claude/search-results ·
https://github.com/pydantic/pydantic-ai/issues/2128 ·
https://github.com/anthropics/claude-agent-sdk-python/issues/574 ·
https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1beta1/GroundingMetadata ·
https://docs.cohere.com/docs/tool-use-citations_

### Verification Services and Models (Checking-Side)

| Checker | Type | Output | Cost/latency signal | Source |
|---|---|---|---|---|
| Vertex **check grounding** | Managed API | `supportScore` 0–1 ≈ fraction of grounded claims; per-claim citations; `citationThreshold` | "latency less than 500ms" | Google docs |
| Azure **groundedness detection** | Managed API | Ungrounded segments; *reasoning* mode explains; *correction* returns rewritten text | Preview; domain = Generic/Medical | Microsoft Learn |
| Bedrock **contextual grounding check** | Managed guardrail | Grounding + relevance scores vs threshold (e.g. 0.7) → block | Per-call guardrail | AWS docs |
| Bedrock **Automated Reasoning checks** | Formal logic over a policy | Valid/invalid with proof | Needs a formalised policy | AWS blog |
| **MiniCheck** / Bespoke-MiniCheck-7B | Open model (claim, doc) → supported? | Binary + prob. | "GPT-4-level … 400x lower cost"; runnable in Ollama | EMNLP 2024 |
| **HHEM-2.1-Open** (Vectara) | Open FLAN-T5 classifier | Consistency score | <600 MB RAM, ~1.5 s / 2k tokens on CPU | HF model card |
| **LettuceDetect** | Open ModernBERT token classifier | *Token-level* unsupported spans | 30–60 ex/s on A100; MIT | arXiv 2502.17125 |
| **Lynx** (Patronus) / **Granite Guardian** | Open 8B–70B judge models | Score + reasoning | GPU-class | Patronus, arXiv 2412.07724 |
| **LLM-as-judge** (NeMo self-check, RAGAS) | Prompted general LLM | Yes/no or per-statement verdicts | One+ extra LLM call | NVIDIA, RAGAS |

_Observation:_ every one of these is **natural-language entailment** (does text T follow from
evidence E?). None checks *arithmetic* or *counting* — a claim "12 workers are qualified" is judged
by whether the evidence text *says* 12, not by recomputing it. For derived quantities, the
deterministic calculator route (ShiftMind's `result_id`, the "LLM never calculates a statistic"
pattern) has no model-based substitute. _Confidence: high._
_Sources: https://docs.cloud.google.com/generative-ai-app-builder/docs/check-grounding ·
https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/groundedness ·
https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html ·
https://arxiv.org/abs/2404.10774 · https://huggingface.co/bespokelabs/Bespoke-MiniCheck-7B ·
https://huggingface.co/vectara/hallucination_evaluation_model · https://arxiv.org/abs/2502.17125 ·
https://www.patronus.ai/blog/lynx-state-of-the-art-open-source-hallucination-detection-model ·
https://arxiv.org/pdf/2412.07724_

### Guardrail and Agent Frameworks

- **PydanticAI** (ShiftMind's runtime, pinned 2.27.0): `output_validator` + `ModelRetry` is the
  in-loop corrective mechanism ShiftMind already uses. The separate `pydantic_ai_harness` package adds
  `OutputGuardrail` with verdicts `allow` / `block` / `replace(value)` / `retry(instruction)` —
  notably **`replace`**, which allows a guard to *rewrite* an answer (e.g. strip or render claims)
  instead of forcing a model retry. Harness is 0.x — _medium confidence on stability_.
- **Guardrails AI Hub** — provenance validators (embedding-distance `provenance_embeddings`,
  model-based `grounded_ai_hallucination`), composable with `on_fail` policies.
- **NeMo Guardrails** — output rails: self-check fact-checking (LLM entailment), AlignScore
  (RoBERTa consistency), self-consistency hallucination rail (sample N, check agreement).
- **Evaluation-only tooling** — RAGAS faithfulness (LLM decompose → verify, score =
  supported/total), ALCE citation recall/precision (NLI-judged, 85.1% / 77.6% agreement with humans),
  Claimify (selection → disambiguation → decomposition; 99% of extracted claims entailed by source).
  These are offline-eval patterns, useful for ShiftMind's live-eval suite rather than the request path.
_Sources: https://pydantic.dev/docs/ai/harness/guardrails/ · https://guardrailsai.com/hub ·
https://github.com/guardrails-ai/provenance_embeddings ·
https://docs.nvidia.com/nemo/guardrails/configure-guardrails/guardrail-catalog/fact-checking ·
https://github.com/vibrantlabsai/ragas/blob/main/docs/concepts/metrics/available_metrics/faithfulness.md ·
https://arxiv.org/pdf/2305.14627 · https://arxiv.org/abs/2502.10855_

### Technology Adoption Trends

- **Evidence IDs owned by the application** is now the consensus: caller-supplied `id`s (Cohere,
  Anthropic `search_result`), tool-returned source IDs (OpenAI guide). The model *references*, never
  *mints*, an ID.
- **Coverage is widening from "numbers" to "every sentence"**: vendor citations and check-grounding
  APIs score all claims, not only numerals. ShiftMind's numeral-only prose rule is narrower than the
  field — it leaves "Worker X is qualified for Y" ungated.
- **Small specialised checkers displaced LLM-judges on the hot path** (MiniCheck, HHEM, LettuceDetect):
  CPU-runnable or cheap-GPU, sub-second to ~1.5 s, with LLM-judges retained for evaluation.
- **Deterministic rendering for regulated or data-bearing UI** (Agentforce, data-analyst agents):
  the value shown to the user bypasses the LLM entirely.
- **Split in vendor formats**: structured JSON (tool/output schemas) and native citations do not mix on
  Anthropic; OpenAI's custom-source guidance is *in-text markers* rather than schema fields. Any design
  that needs both structured output **and** span-level attribution must carry attribution *inside* the
  structure (segments/tags) rather than rely on a vendor citation feature.
_Confidence: medium-high — trend statements synthesise the sources above._

### What This Means for ShiftMind (Stack Fit)

| Constraint in ShiftMind | Implication |
|---|---|
| Answers are **output-tool JSON** (`GroundedAnswerV1`) and the live model is reached via **OpenRouter** | Vendor-native citations (R1/R2) are provider-specific and, on Anthropic, incompatible with structured output → **not a fit** as the primary mechanism; also violates the "no vendor lock-in" seam. Attribution must be *in the schema or in the text*. |
| `result_id` from calculation tools, AR11 trust boundary | Already the R5 principle for numbers. The open question is how to extend it to non-numeric claims and relax the token-matching rule. |
| **Keyless CI** with deterministic double | Any model-based checker (R4, NLI) needs a deterministic stub in CI; a CPU checker (HHEM/MiniCheck-class) could run in live-eval only. |
| Tool results are **structured records** (workers, tasks, qualifications), not documents | Evidence is naturally *record-addressable* (`EvidenceRefV1` already is). Structured-record claims can be checked **deterministically** (field lookup), which NL entailment models are not designed for — a structural advantage the vendor landscape does not have. |

## Integration Patterns Analysis

> Adapted to the topic: "integration" here means how a grounding mechanism plugs into an **agent
> turn** — where it hooks, how evidence identifiers travel from tool result to UI, what the model
> emits, what happens on failure, and how it can be attacked. The template's microservice/messaging
> sections do not apply.

### Where Grounding Hooks Into an Agent Turn

Four hook points recur across the systems surveyed. Every design is some combination of them.

| Hook | Mechanism | Strength | Weakness | ShiftMind today |
|---|---|---|---|---|
| **H1 Generation-time** | Output schema / grammar / constrained decoding restricts *what can be emitted* | Malformed output impossible | Cannot judge *truth*; strict formats degrade reasoning 10–15% on reasoning tasks when serialisation is premature | `GroundedAnswerV1` output tool (segments: prose \| claim) |
| **H2 In-loop validator** | Check the candidate answer; on failure, return feedback and let the model retry | Model fixes its own slip with context | Each retry = a full model call; most gain is in the first retry (N=2 adds ~1.3% utility at 1.45× latency) | `_reject_numeric_prose`, `_reject_uncited_claim`, … raise `ModelRetry` |
| **H3 Post-hoc gate** | After the run, verify and then **block**, **replace/strip**, **flag**, or **revise** | Authoritative; single place for policy | Block = the whole answer is lost for one bad span | `ground_answer` — fail-closed, raises on numeric prose |
| **H4 Render-time** | UI shows verification state per claim (supported / failed / unverified) and links evidence | User sees *what* is grounded | Only as good as H1–H3 | `ClaimSegment` chip: value + unit + evidence links; failed claims show "Claim unavailable" |

_Key pattern:_ vendors split **H3 policy** into non-blocking outcomes — Azure returns *ungrounded
segments* plus a **corrected text**; Cohere's `accurate` mode aligns citations *after* the full
answer; RARR **revises** only the unsupported claim while "preserving the original output as much as
possible". ShiftMind uses only **block** at H3 and only **retry** at H2, which is why a single false
positive (the list-marker case) costs every retry and then the whole turn.
_Sources: https://arxiv.org/pdf/2408.02442 · https://arxiv.org/html/2607.14167v1 ·
https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/groundedness ·
https://docs.cohere.com/docs/rag-citations · https://arxiv.org/abs/2210.08726_

### Evidence Identifier Flow (Tool Result → Model → Gate → UI)

The pattern every vendor converges on is an **application-owned evidence registry per turn**:

```
tool executes ──► app mints IDs for each citable unit ──► model sees content + IDs
      ▲                                                        │ references IDs only
      │                                                        ▼
  UI renders ◄── gate resolves each ID in the registry ◄── answer with IDs
  value/evidence      (unknown ID = failure, never guessed)
```

Design properties from the OpenAI Citation Formatting guide, which is the most explicit public
specification: IDs are **stable** ("the same source should keep the same ID across runs"),
**inspectable** by a human, **right-sized** (block-level default), matched by a strict pattern
(`[A-Za-z0-9_-]+`), and "Never invent source IDs … that were not returned by the tool".

**ShiftMind mapping.**
- Only *calculation* tools mint a citable ID today (`result_id`, a 64-character hash). Inspect tools
  return records (workers, tasks, qualifications, locks) that carry `record_id`s and resolve to
  `EvidenceRefV1(group, record_id, field)` — already field-addressable — but **prose cannot cite
  them**, so "Worker W-12 is qualified for Forklift C01" is ungated.
- The runtime has a dedicated retry rule, `result_id_mistyped`, because live models transcribed the
  64-character hash as 63 and 68 characters. Short, turn-scoped handles (`r1`, `w3`, `t12`) mapped to
  the long ID in the registry remove that failure class — this is what "right-sized, inspectable"
  means in practice. _Confidence: high (observed in ShiftMind's own runtime comments)._
_Source: https://developers.openai.com/api/docs/guides/citation-formatting_

### Emission Formats — What the Model Writes

| Format | Example | Fits structured output? | Model reliability | Streaming | Notes |
|---|---|---|---|---|---|
| **F1 Segment array** (current) | `[{"kind":"prose",…},{"kind":"claim",…}]` | Native | High for shape; awkward for prose flow — sentences are split around every claim | Buffered | A claim segment renders *no text of its own*, so the sentence around it must avoid the number |
| **F2 Inline tags in a string field** (R6, your idea) | `"text": "<claim ev='w3'>Ana</claim> can cover Forklift C01"` | Yes — tags live inside one JSON string | XML-style tags are well followed by Claude-family models (Anthropic guidance); attribute quotes need JSON escaping — prefer single quotes or a bare `ev=w3` | Tag boundaries are detectable mid-stream | One field keeps prose natural and removes most "split the sentence" contortions |
| **F3 Reserved-token markers** (R3) | `…can cover Forklift C01citew3` | Yes | Vendor-tuned for OpenAI models; "custom or unfamiliar formats increase cognitive load" | Buffer to close marker | **Point** citation — marks *where*, not *which words*; OpenAI warns not to place markers inside bold/italic/code |
| **F4 Plain text + post-hoc alignment** (R4) | model writes prose; a second pass extracts claims and links evidence | N/A | Moves the burden to an extractor (LLM or NLI) | Post-answer | Cohere `accurate` mode, RAGAS, Claimify; adds a model call per turn |
| **F5 Value references** (R5) | `"text": "Required minutes: {{r1}}"` → app renders `1,240 minutes` | Yes | Very high: the model copies a handle, never a number | Placeholder is atomic | Generalises today's claim segment into an inline placeholder; the rendered value cannot be wrong |

_Observations._
1. F2 and F5 **compose**: `{{r1}}` renders a *value*; `<claim ev="w3">…</claim>` attributes a
   *statement*. Together they cover "numbers the app renders" and "facts the model states".
2. "Let Me Speak Freely" shows the reasoning cost comes from **premature serialisation**, and
   performance recovers when unconstrained reasoning precedes structured submission. A single free-text
   field with light inline markup is closer to free-form than F1's many small segments. _Medium
   confidence — the study measures JSON/XML/YAML answer formats, not inline markup specifically._
3. Constrained decoding (XGrammar, Outlines) could restrict `ev=` to the IDs issued this turn, but
   hosted models behind OpenRouter do not expose custom grammars; the portable equivalent is a
   **per-turn `enum`/`Literal` in the output schema**, or simply H2/H3 registry checks. _Medium
   confidence._
_Sources: https://arxiv.org/pdf/2408.02442 · https://arxiv.org/pdf/2411.15100 ·
https://github.com/mlc-ai/xgrammar ·
https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/use-xml-tags ·
https://dev.to/gabrielanhaia/json-or-xml-tags-for-llm-output-the-format-that-holds-under-pressure-3ki8 ·
https://github.com/ocherry341/llm-xml-parser_

### Failure Policies — What Happens When a Check Fails

| Policy | Behaviour | Used by | Fit for |
|---|---|---|---|
| **Retry** | Feed the violation back, regenerate the whole answer | PydanticAI `ModelRetry`, guardrails `retry(instruction)` | Model slips it can fix (mistyped ID, missing claim) — cap at 1 retry per rule |
| **Replace / strip** | Remove or neutralise the unsupported span; keep the rest | `pydantic_ai_harness` `replace(value)`, Azure *correction* | Unverifiable decoration (a stray numeral, an unsupported adjective) |
| **Flag** | Keep the span, render it as *unverified* | Vertex `supportScore` + per-claim citations; ShiftMind's own `failed` claim chip | Claims the planner should see but not trust |
| **Revise** | A second model edits only the unsupported claim against evidence | RARR, Azure correction | Rich prose where rewording preserves value |
| **Block** | Reject the answer | Bedrock grounding threshold, ShiftMind `ground_answer` | Only the trust-boundary invariant (a *number* shown unverified) |

Measured trade-off from the self-repair literature: feedback-driven repair converged on 86.6% of
fixable cases without utility loss, while **block-and-retry converged on only 49.1%**, and retries
beyond the first add latency faster than they add quality. _Confidence: medium — two 2026 preprints._
_Sources: https://pydantic.dev/docs/ai/harness/guardrails/ · https://arxiv.org/html/2607.14167v1 ·
https://arxiv.org/html/2607.16215v1 ·
https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/correction-capability-helps-revise-ungrounded-content-and-hallucinations/4253281_

### Security and Trust-Boundary Patterns

- **Citation laundering** (CiteShade, Sept 2026): an attacker controlling one source induces a wrong
  answer *attributed to a trusted source that does not support it*. Mitigation: verify
  **support**, not just **existence**, of the cited evidence — an ID that resolves is necessary, not
  sufficient. ShiftMind's `_ground_claim` already checks metric+arguments match; a prose-claim design
  needs an equivalent *content* check.
- **Tag/marker injection through data**: if tool results or planner text can contain `<claim …>` or
  reserved markers, the model may echo them. Mitigation: the registry is authoritative (the model
  cannot mint IDs); escape or strip tag syntax from tool payloads before they reach the model; parse
  only the model's answer field.
- **Prompt injection via retrieved content** (OWASP LLM01:2025): evidence text is data, never
  instructions — already ShiftMind's rule for rows read back from the database.
_Sources: https://arxiv.org/html/2609.15660v1 ·
https://genai.owasp.org/llmrisk/llm01-prompt-injection/ ·
https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html_

### Testing and CI Integration

- Deterministic parts (registry, tag parser, ID resolution, record-field checks, value rendering) run
  in the keyless CI unchanged.
- Model-based checkers (NLI, LLM-judge) enter behind a **port** with a deterministic double in CI
  (same pattern as `LLMProvider`/`AgentRuntime`), and run for real only in the live-eval suite and
  production.
- Offline quality metrics for the live-eval suite: ALCE-style **citation recall** (is each claim
  supported by its cited evidence?) and **citation precision** (is every cited ID needed?), plus
  RAGAS-style faithfulness over the uncited remainder.
_Sources: https://arxiv.org/pdf/2305.14627 ·
https://github.com/vibrantlabsai/ragas/blob/main/docs/concepts/metrics/available_metrics/faithfulness.md_

## Architectural Patterns and Design

> Running example for every option: *"Ana is qualified for Forklift C01, and 12 workers are available
> on Monday."* — one **record fact** (qualification) and one **derived quantity** (a count).
> Requirement D1 applies throughout: verify the evidence ID **and** the content it wraps.

### System Architecture Patterns — The Options

**A. Patched numeral rule (baseline).** Keep today's token-matching rule for prose, fix its false
positives (ordered-list markers, `06:00` vs `06:00:00`). Numbers only; "Ana is qualified…" stays
unchecked. Satisfies D1 only for calculator claims.

**B. Claim-locked rendering (application verbalises claims).** The model emits typed claims only —
`<claim ev='w3' type='qualified' task='Forklift C01'/>` and `{{r1}}` — and the application renders
the claim sentence from a template and the value from the calculator result. The model writes only
connective prose. "Provenance Before Prose" (2026) reports 98.5–100% reproducibility vs 61.1–79.5%
for templates whose slots the LLM still fills, and zero direction inversions. Content check holds
**by construction**; cost is one template per claim type and stiffer prose.

**C. Model-worded claims with typed attributes (deterministic content check).**
`<claim ev='w3' field='qualifications' value='Forklift C01'>Ana is qualified for Forklift C01</claim>`.
The gate checks (1) `w3` issued this turn, (2) record `w3`'s `qualifications` contains `Forklift C01`,
(3) the `value` appears in the wrapped text. Residual gap: wording that contradicts the attributes
("Ana is **not** qualified…") passes a lexical check.

**D. Free-text claims + NLI checker.** `<claim ev='w3'>Ana can cover the Grid P line</claim>`; the
gate verbalises record `w3` and asks HHEM/MiniCheck-class models whether it supports the text.
Flexible wording, catches negation; probabilistic; ~0.1–1.5 s per claim on CPU; **cannot verify
counts** (entailment, not computation).

**E. Free-text claims + LLM-as-judge.** Same as D with a general LLM, all claims batched per turn.
Most nuanced; one extra network call per turn, nondeterministic, highest cost.

**E′. Free-text claims + decision model (TypeSafe Jev).** Same shape as E but the judge is a
non-generative "System One" decision model: `state` = verbalised record(s) + claim text, typed
question = supported? (bool) or supported / contradicted / not-mentioned (choice). Reported:
deterministic ("the same state and question return the same verdict"), calibrated (on faithfulness
checks, probability > 0.8 ⇒ acceptable 98% of the time), 99.1% on 114 answer-verification cases and
100% on the negation suite of an independent 1,352-case run, median ~170–410 ms, ~$0.00002 per
judgment, all questions of one output type answered in parallel in **one request per turn**.
Documented weaknesses: arithmetic, counting, date math; "applying general rules while overlooking
source exceptions". Limits: 32k tokens for state + longest question, 64k total. _Confidence: medium —
product at 1.13, evidence from vendor, platform blogs and one independent evaluation._

**F. Post-hoc claim extraction (no tags).** Free prose; a Claimify-style extractor decomposes and a
checker verifies. Least model burden, highest system cost (two extra passes); the ACL 2026 survey
notes post-hoc attribution produces less accurate citations.

**G′. Hybrid cascade (cheapest check first).**

| Tier | Check | Catches |
|---|---|---|
| 0 Deterministic | registry ID check; `{{r}}` renders every number; typed-attribute and time-window checks against `EvidenceRefV1` fields | wrong ID, wrong number, wrong field value |
| 1 Decision model (Jev) — or local NLI | one batched call per turn, one question per free-text claim, probability thresholds | wording that contradicts the record (negation, wrong relation) |
| 2 LLM judge | only claims in tier 1's uncertain band, or live-eval only | nuanced cases; written rationale for debugging |
| Policy | allow · strip/flag · one retry · **never block the turn**; untagged prose flag-only (D2) | |

This matches the production cascade pattern (deterministic → encoder/classifier → LLM judge on the
ambiguous remainder, with ALLOW / REDACT_CLAIMS / RETRY / ABSTAIN / ESCALATE actions).

#### Options Matrix

| | Wrong ID | Wrong content — record claims | Wrong content — free wording / negation | Wrong number | Deterministic | Added latency | Keyless CI | Flexibility | Main weakness |
|---|---|---|---|---|---|---|---|---|---|
| **A** | – | ❌ | ❌ | ✅ token match | ✅ | 0 | ✅ | Low | Numbers only; false positives |
| **B** | ✅ | ✅ by construction | n/a | ✅ rendered | ✅ | 0 | ✅ | Low–Med | Template per claim type |
| **C** | ✅ | ✅ | ❌ | ✅ with `{{r}}` | ✅ | 0 | ✅ | Med–High | Wording can contradict attributes |
| **D** NLI | ✅ | ✅ prob. | ✅ prob. | ❌ | ❌ | +0.1–1.5 s/claim | double | High | Accuracy; model to host |
| **E** LLM judge | ✅ | ✅ prob. | ✅ best | ❌ | ❌ | +1 call/turn (~1–3 s) | double | Highest | Cost, nondeterminism |
| **E′** Jev | ✅ | ✅ prob., calibrated | ✅ | ❌ can't count | ✅ same input → same verdict | +1 call/turn (~0.2–0.6 s) | double (replayable) | High | External dependency; new product |
| **F** Post-hoc | n/a | ✅ prob. | ✅ prob. | ❌ | ❌ | +2 calls/turn | double | Highest | Least accurate attribution |
| **G′** Hybrid | ✅ | ✅ deterministic | ✅ tier 1 | ✅ rendered | Tier 0 yes, tier 1 yes (Jev) | 0 for most claims; tier 1 per turn | ✅ | High | Most moving parts |

Invariants across every option: (1) **derived quantities go through a calculator** — no checker
surveyed recomputes a count; (2) **untagged prose needs a policy** — resolved by D2: no lexical
rule; unchecked in phase 2, then a flag-only tier-1 pass over untagged sentences against the turn's
evidence.
_Sources: https://arxiv.org/html/2608.25336 · https://arxiv.org/abs/2506.14580 ·
https://github.com/UtsavOpal/ragwarden · https://arxiv.org/html/2608.05823 ·
https://arxiv.org/abs/2508.15396 · https://openrouter.ai/blog/tutorials/jev-vs-llm-as-a-judge/ ·
https://github.com/pabloirracional/jev-evaluation · https://mlflow.org/blog/jev-llm-judge_

### Design Principles and Best Practices

1. **Separate *what is claimed* from *how it is phrased*.** Claim-locked reporting and
   GenerationPrograms both make the claim/plan an explicit, checkable artefact and let text
   realisation follow. Typed attributes (C) or type-locked claims (B) are that artefact.
2. **Check with the cheapest sound method for each claim kind.** Record facts → field lookup;
   quantities → calculator; free wording → entailment/decision model. Using entailment for what a
   lookup can decide adds error and cost.
3. **Fail narrowly.** A failed claim degrades *that claim* (strip or flag), not the answer. Under D2
   nothing blocks the turn: a number or fact is either verified inside a tag, or shown as plain
   (later flagged) text — never presented as verified when it was not (FR7/NFR12 as reworded).
4. **The application owns identifiers and rendering.** Model references handles; application mints,
   resolves and renders — the vendor consensus and ShiftMind's existing `result_id` rule.
5. **Policies monotone toward caution.** Claim-locked reporting only allows "monotone strength
   downgrades — flagged claims can only become more cautious, never stronger"; the same holds for
   strip/flag decisions.
_Sources: https://arxiv.org/html/2608.25336 · https://arxiv.org/abs/2506.14580 ·
https://developers.openai.com/api/docs/guides/citation-formatting_

### Scalability and Performance Patterns

- **Batch per turn, not per claim**: Jev answers all questions of one output type in one request; LLM
  judges can take all claims in one prompt; NLI encoders batch natively.
- **Keep checker state small**: pass only the cited records, not the conversation — Jev's docs state
  extraneous context lowers accuracy, and its 32k per-question state limit is hit by whole histories.
- **Cache verdicts** on `(claim text, evidence digest)`; `EvidenceRefV1` already carries a
  `checksum_digest`, so a verdict is reusable for as long as the scenario version is unchanged.
- **Escalate only the uncertain band**: calibrated probabilities make tier 2 rare.
_Sources: https://pydantic.dev/docs/ai/models/typesafe/ · https://github.com/pydantic/genai-prices/pull/720_

### Integration and Communication Patterns

Checkers sit behind an **application port** (e.g. a `ClaimSupportChecker` protocol) so the gate
stays framework-free (AD-19) and each tier is swappable: deterministic implementation in-process;
Jev via OpenRouter's Decisions API or PydanticAI's `TypeSafeModel`; local NLI; LLM judge. The
pinned `pydantic-ai-slim==2.27.0` ships no TypeSafe model module (verified in the installed
package), so Jev needs either a pydantic-ai upgrade (which `pydantic-evals` pins in lockstep) or a
direct HTTP adapter behind the port. See Integration Patterns for hook points and failure policies.

### Security Architecture Patterns

- D1's content check is the defence against **citation laundering** (a resolving ID attached to an
  unsupported statement).
- The model never mints identifiers; tag syntax is escaped from tool payloads before the model sees
  them; only the answer field is parsed.
- A networked checker is a **new data egress** (scenario records leave to the checker vendor). It
  needs the same review as the LLM provider, and its outage must degrade to *unverified*, never to
  *supported*.
_Sources: https://arxiv.org/html/2609.15660v1 · https://genai.owasp.org/llmrisk/llm01-prompt-injection/_

### Data Architecture Patterns

- **Per-turn evidence registry**: short handle (`w3`, `r1`) → `EvidenceRefV1` (group, record_id,
  field, version, digest) or calculation result. Handles are minted by tool adapters as results are
  returned.
- **Verbalisation for model checkers**: a deterministic record → text function per evidence group
  (worker, task, qualification, lock, demand interval), so tier-1 input is reproducible.
- **Per-claim verdicts persisted** in the grounded response (tier, verdict, probability, failure
  reason) so the UI can render supported / flagged / stripped states and audits can replay them.

### Deployment and Operations Architecture

| Checker | Where it runs | Fit for ShiftMind's Docker / App Runner (CPU) deploy |
|---|---|---|
| Deterministic tier | In-process | ✅ |
| HHEM-2.1-Open | In-process, CPU, < 600 MB RAM | ✅ but ~1.5 s / 2k tokens |
| Bespoke-MiniCheck-7B | GPU or Ollama sidecar | ⚠️ needs GPU for acceptable latency |
| Jev | External API (OpenRouter / TypeSafe) | ✅ no hosting; adds a vendor dependency and egress |
| LLM judge | External API via existing provider | ✅ reuses OpenRouter; highest cost |
| Vertex check-grounding / Azure groundedness / Bedrock | Managed cloud | ⚠️ cloud-specific lock-in |

Operationally: record every tier-1/2 verdict in telemetry (without content, per AD-12/AD-15); track
flag and strip rates per claim kind in the live-eval suite; alarm on checker error rate, since an
outage silently turns verified claims into unverified ones.
_Sources: https://huggingface.co/vectara/hallucination_evaluation_model ·
https://ollama.com/library/bespoke-minicheck · https://openrouter.ai/typesafe/jev-1.13 ·
https://docs.cloud.google.com/generative-ai-app-builder/docs/check-grounding_

## Implementation Approaches and Technology Adoption

### Technology Adoption Strategies

**Phased, each phase an independently shippable PR; model-based checks enter in shadow mode.**
Shadow mode is the established rollout for guardrails: "the new policy logs what it would have done
while the production controller still acts", thresholds are calibrated on real traffic, then the
check is promoted to enforcement.

| Phase | Ships | Visible change | Check type |
|---|---|---|---|
| ~~0 Stop the bleeding~~ | Dropped (D3): the numeral rule is removed in phase 2 | — | — |
| 1 Evidence registry + short handles | Tool adapters mint turn-scoped handles (`w3`, `t12`, `r1`) for every citable record and result; registry maps handle → `EvidenceRefV1` or calculation result | None; removes the `result_id_mistyped` failure class | Deterministic |
| 2 Inline markup contract + tier 0 | New answer shape: one `text` field carrying `<claim ev='w3' field='…' value='…'>…</claim>` and `{{r1}}`; tolerant parser; tag syntax escaped from tool payloads; ID + field/value + value-in-text checks; `numeric_prose_violation` removed from both call sites and untagged prose left unchecked (D2); policy strip/flag · one retry · never block the turn; UI renders tagged spans with verdict state and untagged text as plain | Record facts verified; prose no longer contorted around claim segments; numbered lists and times no longer retried | Deterministic |
| 3 Tier-1 checker, shadow first | `ClaimSupportChecker` port + deterministic double; Jev adapter via direct `httpx` to OpenRouter (same pattern as `evals/live_conversations/judge.py`, avoids a pydantic-ai upgrade); optional local HHEM adapter | Shadow: verdicts logged and compared with the live judge → enforce as **flag** → later **strip** | Probabilistic, calibrated |
| 4 Untagged prose scan | Flag-only tier-1 pass over untagged sentences against the turn's evidence (D2 option b) | Invented numbers and names in plain text shown flagged; never blocks | Probabilistic |

Phases 0–2 carry the core value and are fully deterministic; phase 3 is optional depth.
_Sources: https://futureagi.com/glossary/shadow-deployment/ ·
https://www.solytics-partners.com/resources/blogs/llm-guardrails ·
https://codeant.ai/blogs/llm-shadow-traffic-ab-testing_

### Development Workflows and Tooling

- Keep the rule single-sourced in `application/grounding/**` (framework-free, AD-19); the adapter in
  `backend/agent/**` only wires validators, exactly as `numeric_prose_violation` is wired today.
- The parser is a small hand-written tokenizer over one attribute syntax, not a general XML parser:
  malformed or unknown tags degrade to plain untagged prose and are **never** treated as supported.
- Checker adapters follow the existing provider pattern: a Protocol in `application/ports`, concrete
  adapters under `adapters/`, selection by configuration, deterministic double for CI.

### Testing and Quality Assurance

- **Golden cases per claim kind** (extending `evals/golden/**`): supported; unknown handle; wrong
  field value; negation ("not qualified"); a numeral outside `{{r}}`; malformed tag; tag text injected
  through a fixture field (build on `injection-fixture-field.json`, `injection-tool-output.json`).
- **Recorded checker verdicts as CI fixtures** — Jev's determinism makes replay faithful.
- **Live-eval metrics**: tag compliance split into *omission* vs *malformed* (reported as 48% and 28%
  of citation failures in one study — measure them separately); citation precision/recall
  (ALCE-style); strip and flag rates per claim kind; retries per rule; turns lost to grounding;
  tier-1 vs LLM-judge agreement.
_Sources: https://arxiv.org/pdf/2512.12117 · https://arxiv.org/pdf/2305.14627 ·
https://ai.pydantic.dev/evals/evaluators/overview/_

### Deployment and Operations Practices

- Tier 0 is in-process — no deployment change.
- Tier 1 via external API: timeout budget, circuit breaker, **outage ⇒ unverified** (never supported);
  verdict counts and latencies exported as telemetry without content (AD-12/AD-15).
- Configuration switches per tier: `off | shadow | flag | strip`, so enforcement can be rolled back
  without a deploy.

### Team Organization and Skills

Solo portfolio project — no team structure. Skill areas exercised: structured-output contract
design, deterministic verification, calibrated classifier integration, evaluation design. Matches
the AI-engineering positioning of the project.

### Cost Optimization and Resource Management

- Tier 1 with Jev: ≈ $0.00002 per judgment, one batched call per turn — negligible.
- **Largest saving is fewer retries**: every `ModelRetry` is a full main-model call; today a single
  false positive can consume the whole `retries_limit` and then the turn.
- Tier 2 LLM judge capped to the uncertain band or live-eval only.
- Latency budget: tier 0 ≈ 0; tier 1 ≈ 0.2–0.6 s per turn.

### Risk Assessment and Mitigation

| Risk | Mitigation |
|---|---|
| Tag adherence differs by model (omission / malformed) | Measure per model in live-eval; malformed ⇒ untagged, never supported |
| Jev is new (1.13) and external | Shadow phase first; outage ⇒ unverified; HHEM adapter as local fallback |
| Over-stripping degrades answers | Start at *flag*; track strip rate per claim kind |
| Persisted V1 responses must still render | V2 is a new `schema_version`; V1 stays readable; no rewrite of stored history |
| Model words a claim that contradicts its attributes | Tier 1 exists for exactly this; until then, tier 0 flags attribute/text mismatch |
| Scope creep | Phases 0–2 are the core; phase 3 optional |

## Technical Research Recommendations

### Implementation Roadmap

1 → 2 (deterministic core; numeral rule removed per D2) → 3 (tier-1 checker, shadow → flag → strip)
→ 4 (flag-only scan of untagged prose). Phase 0 dropped (D3).

### Technology Stack Recommendations

- No new dependencies for phases 0–2.
- Phase 3: Jev (`typesafe/jev-1.13`) via OpenRouter's Decisions API behind a port; HHEM-2.1-Open as
  a local alternative; existing live LLM judge as the calibration reference.

### Skill Development Requirements

Classifier calibration and threshold selection; evaluation of attribution quality (citation
precision/recall).

### Success Metrics and KPIs

| KPI | Target |
|---|---|
| False-positive retries (list markers and similar) | 0 |
| Turns lost to a grounding failure | tracked, downward trend |
| Share of factual sentences tagged (live-eval) | rising |
| Tier-1 vs LLM-judge agreement in shadow | ≥ 95% before enforcement |
| Added p95 latency per turn | ≤ 700 ms |

---

# Research Synthesis — From Fluent to Verifiable: Claim-Level Grounding for ShiftMind

## Executive Summary

ShiftMind's grounding rule works by elimination: a prose segment may carry no numeral unless that
exact token appears in trusted text, and any derived quantity must be a calculator claim citing a
`result_id`. It protects numbers, but it is brittle and narrow. Ordered-list markers and time formats
trip it; whether an answer passes depends on which tokens happen to sit in context; every false
positive costs a full main-model retry and, after `retries_limit`, the whole turn; and it says
nothing about non-numeric facts such as "Ana is qualified for Forklift C01".

The field has moved to **claim-level attribution**: the application owns evidence identifiers, the
model only references them, and each claim is verified on its own — what recent work on research
agents calls moving "from fluent to verifiable". Vendor citation features (Anthropic, OpenAI, Gemini,
Cohere) embody the ID principle but cannot carry ShiftMind's design: they are provider-specific,
bound to their own retrieval tools, and on Anthropic incompatible with structured output. No
verification model surveyed — NLI, decision model or LLM judge — recomputes a count. ShiftMind's
distinctive advantage is that its evidence is **structured records**, so most claims can be checked
deterministically against fields it already resolves (`EvidenceRefV1.group/record_id/field`).

**Key Technical Findings**

- Six answer–evidence representations are in use (cited blocks, span offsets, inline markers, claim
  lists, application-rendered values, inline tags); inline tags + value placeholders fit ShiftMind's
  structured-output answers best.
- ID existence is not support: citation laundering attaches real IDs to false statements, so the
  content check (D1) is mandatory.
- Claim-locked rendering (numbers bypass the LLM) reaches 98.5–100% reproducibility in 2026 work.
- A calibrated, deterministic decision model (TypeSafe Jev) makes a per-turn wording check cheap
  (~$0.00002/judgment, ~0.2–0.6 s), but cannot count and misses source exceptions.
- Retry-and-block converges far worse than narrow repair (49.1% vs 86.6% in one 2026 study); retries
  beyond the first add latency faster than quality.

**Technical Recommendations**

1. Adopt **G′**: application-rendered numbers (`{{r1}}`), inline attribute-checked claims
   (`<claim ev='w3' field='…' value='…'>…</claim>`), a tier-1 wording check, narrow failure policy.
2. Introduce a **per-turn evidence registry with short handles** before changing the answer format.
3. Keep phases 0–2 **fully deterministic**; add the model-based tier behind a port, in shadow mode.
4. Degrade **one claim, not the turn**: strip/flag, one retry, never block; untagged prose is plain
   text, later flag-scanned (D2).
5. Measure tag compliance (omission vs malformed), citation precision/recall and checker agreement in
   the live-eval suite before each enforcement step.

## Table of Contents

1. Research Overview (top of document)
2. Technical Research Scope Confirmation — incl. *Decisions Recorded During Research* (D1)
3. Technology Stack Analysis — representations R1–R6, vendor APIs, verification models, frameworks, stack fit
4. Integration Patterns Analysis — hook points H1–H4, evidence-ID flow, emission formats F1–F5, failure policies, security, CI
5. Architectural Patterns and Design — options A–G′, options matrix, principles, performance, data, deployment
6. Implementation Approaches and Technology Adoption — phases 0–4, testing, operations, cost, risks
7. Technical Research Recommendations — roadmap, stack, KPIs
8. Research Synthesis (this section) — recommendation rationale, outlook, methodology, sources

## Recommendation and Rationale

| Option | Verdict | Reason |
|---|---|---|
| A Patched numeral rule | Rejected (D2, D3) | Guards numbers only while invented names pass; removed in phase 2 |
| B Claim-locked for everything | Use **for numbers only** | Strongest guarantee, but a template per claim type is too rigid for general facts |
| C Typed attributes | **Core of the design** | Deterministic content check for record facts; keeps model wording |
| D/E/E′ Model checkers alone | Use as **tier 1/2**, not alone | Cannot count; add cost to every claim |
| F Post-hoc extraction | Reject | Highest cost, least accurate attribution |
| **G′ Hybrid** | **Recommended** | Each claim kind checked by the cheapest sound method; C's only gap (wording contradicting attributes) is exactly what tier 1 covers |

The design preserves ShiftMind's existing invariants: the application owns identifiers and numbers
(AR11), the rule stays single-sourced and framework-free (AD-19), external checkers sit behind a port
with a deterministic CI double, and telemetry excludes content (AD-12/AD-15).

## Implementation Roadmap and Risk Summary

1 (registry + short handles) → 2 (inline markup, tier 0, numeral rule removed, failure policy,
UI verdict states — the core value) → 3 (tier-1 checker: shadow → flag → strip; optional depth) →
4 (flag-only scan of untagged prose). Phase 0 dropped (D3). Principal risks — tag adherence per model, a new
external checker, over-stripping, V1/V2 persisted-response compatibility — and their mitigations are
in *Implementation Approaches › Risk Assessment and Mitigation*.

## Future Technical Outlook

- **Near term**: vendor span-level citations may become compatible with structured output; revisit
  R1 if Anthropic lifts the documented incompatibility.
- **Decision models** (System-One class) are new; independent benchmarks are sparse — expect rapid
  change in accuracy claims and pricing.
- **Program-/plan-based attribution** (GenerationPrograms, claim ledgers) points toward answers whose
  claim set is an explicit, auditable artefact — the direction G′ already takes.
- Open questions for ShiftMind: Jev accuracy on its own records; tag adherence of the live model;
  whether untagged prose still needs a numeral rule once `{{r}}` is standard.

## Methodology and Source Verification

- **Scope**: answer–evidence representations, verification technologies, integration, architecture,
  implementation; constrained to ShiftMind's stack and invariants.
- **Sources**: first-party vendor documentation (Anthropic, OpenAI, Google, Cohere, Microsoft, AWS,
  Pydantic, OpenRouter, TypeSafe integrations), peer-reviewed papers (ALCE, MiniCheck, RARR, RAGAS,
  ProgramFC, ACL 2026 attribution survey), 2026 preprints (Provenance Before Prose, CiteShade,
  self-repair studies), independent evaluations (Jev 1,352-case run, MLflow), and ShiftMind's own
  code (`gate.py`, `runtime.py`, contracts, eval suite).
- **Confidence**: high for vendor API behaviour and established papers; **medium** for 2026 preprints,
  trend statements, and all Jev figures (new product; vendor, platform and one independent source).
- **Limitations**: no hands-on measurement on ShiftMind data yet — phases 2–3 are designed to produce
  it; searches were US-indexed and English-only.

### Consolidated Key Sources

- Anthropic Citations — https://platform.claude.com/docs/en/build-with-claude/citations
- Anthropic search results — https://platform.claude.com/docs/en/build-with-claude/search-results
- OpenAI Citation Formatting — https://developers.openai.com/api/docs/guides/citation-formatting
- Gemini grounding — https://ai.google.dev/gemini-api/docs/generate-content/google-search
- Cohere RAG citations — https://docs.cohere.com/docs/rag-citations
- Vertex check grounding — https://docs.cloud.google.com/generative-ai-app-builder/docs/check-grounding
- Azure groundedness — https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/groundedness
- Bedrock contextual grounding — https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html
- Agentforce deterministic rendering — https://engineering.salesforce.com/how-agentforce-achieves-100-deterministic-rendering-for-ai-agent-ux/
- Provenance Before Prose — https://arxiv.org/html/2608.25336
- GenerationPrograms — https://arxiv.org/abs/2506.14580
- MiniCheck — https://arxiv.org/abs/2404.10774 · HHEM — https://huggingface.co/vectara/hallucination_evaluation_model · LettuceDetect — https://arxiv.org/abs/2502.17125
- Jev — https://openrouter.ai/blog/tutorials/jev-vs-llm-as-a-judge/ · https://github.com/pabloirracional/jev-evaluation · https://mlflow.org/blog/jev-llm-judge · https://pydantic.dev/docs/ai/models/typesafe/
- ALCE — https://arxiv.org/pdf/2305.14627 · RARR — https://arxiv.org/abs/2210.08726 · RAGAS — https://github.com/vibrantlabsai/ragas/blob/main/docs/concepts/metrics/available_metrics/faithfulness.md
- Attribution survey (ACL 2026) — https://arxiv.org/abs/2508.15396
- CiteShade — https://arxiv.org/html/2609.15660v1
- Let Me Speak Freely — https://arxiv.org/pdf/2408.02442
- Self-repair vs block-and-retry — https://arxiv.org/html/2607.14167v1 · https://arxiv.org/html/2607.16215v1
- Pydantic harness guardrails — https://pydantic.dev/docs/ai/harness/guardrails/
- From Fluent to Verifiable — https://arxiv.org/pdf/2602.13855

## Technical Research Conclusion

The flexible grounding ShiftMind needs is **not a looser rule — it is a finer-grained one**: verify
each claim with the cheapest sound method for its kind (render numbers, look up record facts, judge
wording), and let a failure cost one claim rather than the turn. The deterministic core (phases 0–2)
delivers most of the value with no new dependencies; the calibrated wording check (phase 3) closes
the remaining gap once measured on ShiftMind's own data.

**Next steps**: turn phase 1 (registry + short handles) and phase 2 (inline markup, tier 0, numeral
rule removal, FR7/NFR12 rewording) into specs via `bmad-quick-dev` or stories; plan the phase-3 shadow
experiment in the live-eval suite.

---

**Technical Research Completion Date:** 2026-09-26
**Source Verification:** All technical facts cited with current sources
**Technical Confidence Level:** High for vendor/standard behaviour; medium for 2026 preprints and Jev figures
