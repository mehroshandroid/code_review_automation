# LLM Context Window Fixes Design Spec

**Status:** Approved
**Date:** 2026-08-04

## Purpose

User asked how to guarantee the whole codebase reaches the LLM when it exceeds
the current 32,000-character `gather_code_context()` budget. Investigation found
two distinct problems, both addressed here:

1. **Ollama's context window is already being silently exceeded today.**
   Ollama defaults every model to `num_ctx: 2048` tokens (~8,000 characters) --
   an intentional hardware-safety default, not a model capability limit --
   and nothing in `ollama_client.py` overrides it. But the pipeline already
   sends up to 32,000 characters of code context plus instructions, well
   past that. The local-LLM path is likely truncating input on every review
   today, independent of "sending more."
2. **`gather_code_context()`'s 32,000-character budget is a single constant
   shared by every provider**, even though Ollama (local hardware) and Azure
   OpenAI (confirmed `gpt-4o-mini`, 128K token context) have very different
   real capacity.

No fixed budget can guarantee full coverage for an arbitrarily large project --
chunking/multi-pass analysis would be needed for that, and was explicitly
decided against this round in favor of a simpler, bounded fix: raise each
provider's budget to match what its model can actually handle.

## 1. Fix Ollama's num_ctx

`ollama_client.py` talks to Ollama's OpenAI-compatible endpoint
(`/v1/chat/completions`), where `num_ctx` is a **top-level** payload field (not
nested under `options`, which only applies to Ollama's native `/api/generate`/
`/api/chat` endpoints).

Add:
```python
DEFAULT_OLLAMA_NUM_CTX = 16384
```
with an `OLLAMA_NUM_CTX` env var override, mirroring the existing
`OLLAMA_MODEL`/`OLLAMA_BASE_URL` override pattern. `_post()` merges
`"num_ctx": <value>` into the payload before sending, so both `score_category`
and `generate_general_remarks` (which both go through `_post`) get it for
free with no changes to either.

16384 (8x today's silent 2048 default) rather than the model's theoretical 32K
ceiling: `num_ctx` memory cost scales with context size, and going further
risks OOM/major slowdowns on local hardware -- working against the 300s
timeout raised in the previous round specifically because local inference is
already slow.

## 2. Provider-specific code-context budgets

`reviews.py` already knows `llm_provider` (a `run_review()` parameter) before
it calls `analyzer.gather_code_context(extract_dir)` -- currently called with
no `max_chars` argument at all, silently using the analyzer's own default of
32,000. Add two constants and pick between them by provider:

```python
CODE_CONTEXT_MAX_CHARS_OLLAMA = 48000
CODE_CONTEXT_MAX_CHARS_AZURE = 120000
```

- **Ollama: 48,000 characters.** With `num_ctx` raised to 16,384 tokens, and
  ~1,000-1,500 tokens reserved for the system message, category
  instructions/checklist text, and the model's JSON response, ~14,800-15,300
  tokens remain for code. At a conservative ~3.3 chars/token for code (code
  tokenizes less efficiently than prose), that's roughly 48,000 characters --
  a real, usable increase over today's 32,000 for the first time, since
  `num_ctx` now actually covers it.
- **Azure: 120,000 characters.** `gpt-4o-mini` has a 128K token context
  window. Reserving headroom for `max_tokens=1500` (response) and
  instructions still leaves well over 100K tokens of slack. Deliberately not
  maxed to the theoretical ~400K-character ceiling: this same context gets
  resent on every one of the ~6-8 category calls per review, and pushing
  further has no real value for typical project sizes.
- Exceeding Azure's real context window is a hard 400 error (unlike Ollama's
  silent truncation), and nothing in the scoring loop's exception handling
  distinguishes it from any other failure -- it would fail the entire review
  (`status: "error"`), not just degrade one category. 120,000 stays safely
  within `gpt-4o-mini`'s confirmed 128K window with real margin, so this risk
  doesn't materialize at this budget.

`gather_code_context()`'s function signature, return type, and truncation
logic (including the .NET priority-tier ordering from the previous round) are
unchanged in every analyzer -- only the `max_chars` value passed in changes.

## Testing

- `ollama_client.py`: `score_category` and `generate_general_remarks` each
  send `num_ctx` as a top-level payload field, defaulting to 16384; an
  `OLLAMA_NUM_CTX` env var override is respected.
- `reviews.py`: `gather_code_context` is called with
  `max_chars=CODE_CONTEXT_MAX_CHARS_OLLAMA` when `llm_provider == "ollama"`,
  and `max_chars=CODE_CONTEXT_MAX_CHARS_AZURE` otherwise -- monkeypatch the
  analyzer's `gather_code_context` to capture the `max_chars` it was called
  with, mirroring the existing pattern already used to test other
  `run_review` wiring in `test_reviews_create.py`.
