"""Smoke-check helper; requires an already populated vector store."""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


def answer(question: str):
    load_dotenv()
    key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
    store_id = os.getenv("OPENAI_VECTOR_STORE_ID")
    model = os.getenv("OPENAI_MODEL")
    if not all([key, store_id, model]):
        raise ValueError("Set OPENAI_API_KEY and OPENAI_MODEL, and sync documents to a vector store first.")
    client = OpenAI(api_key=key, timeout=60, max_retries=1)
    response = client.responses.create(
        model=model,
        instructions=(Path(__file__).parent / "prompts/system.txt").read_text(encoding="utf-8"),
        input=question,
        tools=[{"type": "file_search", "vector_store_ids": [store_id]}],
        tool_choice="required",
        include=["file_search_call.results"],
    )
    return response


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?", default="How do I add a YouTube video?")
    args = parser.parse_args()
    try:
        response = answer(args.question)
    except ValueError as exc:
        parser.error(str(exc))
    print(response.output_text)


if __name__ == "__main__":
    main()
