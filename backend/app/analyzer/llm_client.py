from app.analyzer import ollama_client, openai_client


async def score_category(
    provider: str, category_name: str, sub_criteria: list, descriptions: dict, code_snippets: str, model: str | None = None
) -> tuple:
    if provider == "ollama":
        return await ollama_client.score_category(category_name, sub_criteria, descriptions, code_snippets, model=model)
    return await openai_client.score_category(category_name, sub_criteria, descriptions, code_snippets)


async def generate_general_remarks(provider: str, category_results: dict, model: str | None = None) -> tuple:
    if provider == "ollama":
        return await ollama_client.generate_general_remarks(category_results, model=model)
    return await openai_client.generate_general_remarks(category_results)
