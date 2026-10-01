# 06 — AI architecture

## Agents (modules, not one giant prompt)
| Stage | Module | Deterministic fallback |
|---|---|---|
| CV → profile | `parsing/cv_parser.py` + `AIService.structured("cv_parse")` | rule-based section parser |
| Job post → schema | `parsing/job_parser.py` + `AIService.structured("job_parse")` | rule-based extractor, multi-post splitter |
| Matching | `matching/engine.py` | fully deterministic (no LLM) |
| CV tailoring | `generation/cv_builder.py` | deterministic selection/ordering; optional LLM returns *selections by entity id* |
| Cover letter / email | `generation/letters.py` | template-based, 5 tones, en/bn |
| Quality control | `qc.py` | deterministic, independent of the generator |

## AIService (`services/ai/service.py`)
* provider interface + adapters: OpenAI, OpenAI-compatible (local/vLLM/Ollama), Anthropic, Gemini
* cheap/strong model routing per task (`AI_CHEAP_MODEL` for extraction, `AI_STRONG_MODEL` for writing)
* content-hash cache (`ai_cache`) — identical input is never paid for twice
* bounded retries, per-request input/output caps, JSON-schema validation of every response
* on failure/invalid output → heuristic fallback (configurable) and the item is marked `requires_review` rather than silently wrong
* `ai_request_logs` store metadata only (task, provider, model, tokens, latency, success, cache hit) — never prompt/response content
* usage and estimated cost recorded per user for quotas and admin dashboards

## Safety
1. **Prompt injection**: untrusted text is wrapped in `<untrusted_*>` tags, system rules forbid following embedded instructions, outputs must validate against Pydantic schemas, LLM output never triggers actions (no tools), and generated text has links/emails stripped unless they come from the profile.
2. **Grounding**: `ground_extraction` removes extracted entities that do not appear in the source CV text. `rewrite_is_safe` rejects rewrites that introduce new skills or numbers. The tailored CV is built from profile entities by id.
3. **QC agent** re-checks the final documents against the profile and job: name/contact, every skill/employer/degree/date/project/certification, company-name mismatch, placeholders, page limit, ATS text round-trip, recipient address, subject, attachments, duplicate application. Blocking failures make approval impossible until fixed.

## Matching formula
Seven dimensions with default weights — skills 30, experience 20, education 10, responsibilities 15, technology 10, role 10, location 5. A dimension for which the job post gives no information is **excluded and the remaining weights are renormalised** (the UI says so). Related skills (same family) earn 0.5 partial credit. Classification thresholds default to strong ≥ 90, potential ≥ 75, weak ≥ 60, else not suitable. Weights and thresholds are per-user settings; every match stores the weights/thresholds used, per-dimension reasons, evidence, strengths, gaps and concerns. A score is an estimate of fit, never a prediction of an employer's decision.
