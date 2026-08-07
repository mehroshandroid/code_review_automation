import re

# Keyed by (platform, sub_id) -- mirrors the existing precedent in reviews.py,
# which already special-cases sub-criterion "1.4" by its literal ID for the
# compile-check merge, so clause IDs are already treated as stable
# conventions in this codebase rather than arbitrary per-template text.
# Every clause without an entry here keeps the plain, generic behavior --
# just its raw template description, unchanged.
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


def category_instructions(category_name: str, sub_criteria: list, descriptions: dict, platform: str = "Android") -> str:
    lines = []
    for sub_id in sub_criteria:
        line = f"{sub_id}: {descriptions.get(sub_id, '')}"
        checklist = CLAUSE_CHECKLISTS.get((platform, sub_id))
        if checklist:
            line += f"\n  Specifically check for: {checklist}"
        lines.append(line)
    criteria_lines = "\n".join(lines)
    return (
        f"Score the following {category_name} sub-criteria as an expert {platform} code reviewer, "
        f"based ONLY on the code above:\n"
        f"{criteria_lines}\n\n"
        "For each sub-criterion, score 0 (fails), 1 (meets it), or null if the "
        "code snippet does not contain enough information to judge that specific sub-criterion "
        "(e.g. it asks about PR comments, commit history, or other context not present in "
        "source code -- do not guess or assume in that case, use null). "
        "Each remark must be specific to its own sub-criterion's exact wording above, not a "
        "general comment about the code as a whole or about a different sub-criterion.\n"
        'Respond as JSON: {"<id>": {"score": <num or null>, "remark": "<1-2 sentences>"}, ...}'
    )


def code_context_message(code_snippets: str, platform: str = "Android") -> str:
    return (
        f"You are an expert {platform} code reviewer. Here is the {platform} project's "
        f"source code for review:\n\n{code_snippets}"
    )


def general_remarks_prompt(platform: str = "Android") -> str:
    return (
        f"You are an expert {platform} code reviewer. Given per-criterion scores and remarks "
        "from a completed code review, write a concise 2-3 sentence overall summary of the "
        "code quality, highlighting the weakest areas. Respond with plain text only, no JSON."
    )


def build_findings_summary(category_results: dict) -> str:
    lines = []
    for result in category_results.values():
        for sub_id, sub in result["sub_scores"].items():
            lines.append(f"{sub_id}: score={sub.get('score')}, remark={sub.get('remark') or ''}")
    return "\n".join(lines) if lines else "No findings were scored."


def normalize_score_result(parsed: dict, sub_criteria: list) -> dict:
    """Guarantees the returned dict has exactly sub_criteria's keys, in that
    exact order -- regardless of what order (or completeness) the model's
    JSON used. Callers rely on this order to align each sub-criterion's
    score/remark to the correct row when writing the Excel output
    positionally; a model that reorders, skips, or hallucinates an extra key
    would otherwise silently misalign every row after the discrepancy.
    """
    result = {}
    for sub_id in sub_criteria:
        entry = parsed.get(sub_id) if isinstance(parsed, dict) else None
        if isinstance(entry, dict):
            result[sub_id] = {"score": entry.get("score"), "remark": entry.get("remark", "")}
        else:
            result[sub_id] = {"score": None, "remark": ""}
    return result


def strip_markdown_fences(content: str) -> str:
    """Defensive fallback: response_format=json_object should prevent this, but
    strip a ```json ... ``` or ``` ... ``` wrapper if the model adds one anyway.
    """
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", content.strip(), re.DOTALL)
    return match.group(1) if match else content
