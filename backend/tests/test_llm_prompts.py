from app.analyzer.llm_prompts import category_instructions


def test_category_instructions_includes_the_checklist_for_dotnet_clause_2_4():
    prompt = category_instructions(
        "Reliability, Security & Observability",
        ["2.4"],
        {"2.4": "Authentication and authorization correctly enforced"},
        platform=".NET",
    )

    assert "2.4: Authentication and authorization correctly enforced" in prompt
    assert "Specifically check for:" in prompt
    assert "[Authorize]" in prompt
    assert "ValidateAudience=true" in prompt
    assert "ValidateIssuer=true" in prompt


def test_category_instructions_omits_the_checklist_for_a_different_sub_id():
    prompt = category_instructions(
        "Reliability, Security & Observability",
        ["2.1"],
        {"2.1": "Proper exception handling"},
        platform=".NET",
    )

    assert "Specifically check for:" not in prompt
    assert "[Authorize]" not in prompt


def test_category_instructions_omits_the_dotnet_2_4_checklist_for_a_different_platform():
    prompt = category_instructions(
        "Reliability, Security & Observability",
        ["2.4"],
        {"2.4": "Authentication and authorization correctly enforced"},
        platform="Android",
    )

    assert "2.4: Authentication and authorization correctly enforced" in prompt
    assert "Specifically check for:" not in prompt
    assert "[Authorize]" not in prompt


def test_category_instructions_still_lists_every_sub_criterion_when_only_one_has_a_checklist():
    prompt = category_instructions(
        "Reliability, Security & Observability",
        ["2.1", "2.4"],
        {
            "2.1": "Proper exception handling",
            "2.4": "Authentication and authorization correctly enforced",
        },
        platform=".NET",
    )

    assert "2.1: Proper exception handling" in prompt
    assert "2.4: Authentication and authorization correctly enforced" in prompt
    assert prompt.count("Specifically check for:") == 1
