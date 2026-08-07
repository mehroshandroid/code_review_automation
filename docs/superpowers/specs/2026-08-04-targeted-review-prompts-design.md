# Targeted Review Prompts Design Spec

**Status:** Approved
**Date:** 2026-08-04

## Purpose

A real .NET project (Moove) was scored 1 by the LLM on clause 2.4 ("Authentication
and authorization correctly enforced") but scored 0 by a human reviewer, whose
remark was: "Anonymous endpoints were found, and JWT Audience and Issuer
validation is not properly configured." Two root causes:

1. **The prompt is generic.** `category_instructions()` hands the LLM only the
   template's one-line clause text with no domain-specific checklist of what
   "correctly enforced" actually means to check for.
2. **The relevant code may never reach the LLM.** `gather_code_context()` sorts
   source files alphabetically and fills a fixed 32,000-character budget with no
   prioritization. For a real multi-project .NET solution, `Program.cs`/
   `Startup.cs` (where JWT config lives) and `*Controller.cs` files (where
   `[Authorize]`/`[AllowAnonymous]` usage lives) can sort late enough to be
   truncated out entirely.

This round fixes both, scoped to `.NET` clause 2.4 as the first concrete case of a
pattern that can extend to other clause/platform combinations later.

## 1. `.NET` code-context prioritization

`dotnet_analyzer.gather_code_context()` currently does:
```python
source_files = sorted(project_dir.rglob("*.cs"), key=lambda f: str(f.relative_to(project_dir)))
```

Change the ordering to a priority-tiered sort instead of pure alphabetical:
1. `Program.cs` / `Startup.cs` (by filename, anywhere in the tree)
2. Any file matching `*Controller.cs`
3. Everything else, alphabetically (existing behavior, unchanged)

Within each tier, files stay sorted alphabetically for determinism. The function's
signature, return type, and the rest of its truncation logic (fixed `max_chars`
budget, per-file `--- path ---` header) are unchanged -- only which files get
picked first when the budget runs out changes.

Scoped to `.NET` only. Android's and iOS's `gather_code_context()` keep their
current pure-alphabetical order -- their entrypoint/auth conventions are
different enough (and there's no concrete real-world miss driving specific
patterns for them yet) that guessing at priority patterns for them now would be
speculative.

## 2. Clause-specific checklist injection

Add a lookup in `llm_prompts.py`:
```python
CLAUSE_CHECKLISTS = {
    (".NET", "2.4"): (
        "(1) every controller action that should require authentication has an "
        "[Authorize] attribute -- flag any [AllowAnonymous] or missing [Authorize] "
        "on an endpoint that looks like it handles user/account/payment data; "
        "(2) JWT bearer configuration (AddJwtBearer/TokenValidationParameters) "
        "explicitly sets ValidateAudience=true and ValidateIssuer=true with real, "
        "non-default expected values; (3) UseAuthentication/UseAuthorization "
        "middleware is registered, in the correct order, in Program.cs/Startup.cs."
    ),
}
```

Keyed by `(platform, sub_id)` -- this mirrors the existing precedent in
`reviews.py`, which already special-cases sub-criterion `"1.4"` by its literal ID
for the compile-check merge. Clause IDs are already treated as stable
conventions in this codebase, not arbitrary per-template text.

`category_instructions()` changes from building `criteria_lines` as a flat
`"\n".join(...)` of `f"{sub_id}: {descriptions.get(sub_id, '')}"` to appending a
"Specifically check for: ..." block under any line whose `(platform, sub_id)`
has an entry in `CLAUSE_CHECKLISTS`. Every other clause is unaffected -- still
just the raw template description, exactly as today.

## Testing

- `test_dotnet_analyzer_context.py` (or wherever `gather_code_context` is
  already tested): a `tmp_path` with several `.cs` files placed so that
  `Program.cs` and a `*Controller.cs` file would sort late alphabetically (e.g.
  under a folder starting with `Z`), plus enough early-alphabetical filler files
  to exceed a small `max_chars` budget. Assert `Program.cs` and the controller
  file's content appear in the returned context despite the tight budget, and
  that some early-alphabetical filler file got truncated out instead.
- `llm_prompts` tests: `category_instructions(".NET", ["2.4"], {"2.4": "Authentication and authorization correctly enforced"}, ...)` includes the checklist text; the same call with `platform="Android"` or a different `sub_id` does not.
