import os

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import AzureChatOpenAI

from app.chatbot.tools import query_reviews

SYSTEM_PROMPT = (
    "You are an assistant embedded in a code review dashboard. You answer "
    "questions about past code review history using the query_reviews tool "
    "-- platform, score, date, and per-clause remarks/warnings. Answer only "
    "from what the tool returns; if nothing matches, say so plainly rather "
    "than guessing or filling gaps from general knowledge. Be concise."
)


def _build_agent_executor() -> AgentExecutor:
    llm = AzureChatOpenAI(
        azure_endpoint=os.environ["OPENAI_API_BASE"],
        azure_deployment=os.environ["OPENAI_DEPLOYMENT_NAME"],
        api_version=os.environ["OPENAI_API_VERSION"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        temperature=0.2,
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    agent = create_tool_calling_agent(llm, [query_reviews], prompt)
    return AgentExecutor(agent=agent, tools=[query_reviews], return_intermediate_steps=True, max_iterations=5)


def _to_lc_history(history: list[dict]) -> list:
    messages = []
    for turn in history:
        if turn["role"] == "user":
            messages.append(HumanMessage(content=turn["content"]))
        else:
            messages.append(AIMessage(content=turn["content"]))
    return messages


def _extract_sources(intermediate_steps: list) -> list[dict]:
    sources_by_id = {}
    for _action, observation in intermediate_steps:
        if not isinstance(observation, list):
            continue
        for item in observation:
            if isinstance(item, dict) and "id" in item:
                sources_by_id[item["id"]] = item
    return list(sources_by_id.values())


async def answer_question(message: str, history: list[dict]) -> dict:
    executor = _build_agent_executor()
    result = await executor.ainvoke({"input": message, "chat_history": _to_lc_history(history)})
    return {
        "answer": result["output"],
        "sources": _extract_sources(result.get("intermediate_steps", [])),
    }
