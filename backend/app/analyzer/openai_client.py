import os


def is_stub_mode() -> bool:
    return not os.environ.get("AZURE_OPENAI_KEY")
