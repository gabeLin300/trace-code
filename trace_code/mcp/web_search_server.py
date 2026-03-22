from __future__ import annotations

import argparse
import getpass
import json
import os
from typing import Any
from urllib.request import Request, urlopen


TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class TavilyError(RuntimeError):
    pass


def resolve_tavily_api_key(
    *,
    explicit_api_key: str | None,
    env_var_name: str = "TAVILY_API_KEY",
    prompt_if_missing: bool = True,
) -> str:
    """Resolve Tavily API key from explicit value, env var, or user prompt."""
    if explicit_api_key and explicit_api_key.strip():
        return explicit_api_key.strip()

    env_value = os.getenv(env_var_name, "").strip()
    if env_value:
        return env_value

    if not prompt_if_missing:
        raise TavilyError(f"Missing Tavily API key. Set {env_var_name} or pass --api-key.")

    entered = getpass.getpass("Enter Tavily API key: ").strip()
    if not entered:
        raise TavilyError(f"Missing Tavily API key. Set {env_var_name} or pass --api-key.")
    return entered


def _tavily_search_request(
    *,
    api_key: str,
    query: str,
    max_results: int,
    search_depth: str,
) -> dict[str, Any]:
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_answer": True,
    }
    raw = json.dumps(payload).encode("utf-8")
    request = Request(
        TAVILY_SEARCH_URL,
        data=raw,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8", errors="replace")
    data = json.loads(body)
    if data.get("error"):
        raise TavilyError(str(data["error"]))
    return data


def tavily_search(
    *,
    api_key: str,
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
) -> dict[str, Any]:
    if not query.strip():
        raise TavilyError("query must not be empty")

    data = _tavily_search_request(
        api_key=api_key,
        query=query,
        max_results=max_results,
        search_depth=search_depth,
    )

    raw_results = data.get("results") or []
    results: list[dict[str, Any]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "score": item.get("score"),
            }
        )

    return {
        "status": "ok",
        "query": query,
        "answer": data.get("answer", ""),
        "results": results,
    }


def _build_server(api_key: str):
    try:
        from fastmcp import FastMCP
    except Exception as exc:
        raise RuntimeError("fastmcp is required to run the Tavily web search MCP server") from exc

    mcp = FastMCP("trace-web-search")

    @mcp.tool(name="web.search")
    def web_search(query: str, max_results: int = 5, search_depth: str = "basic") -> dict:
        """Search the web using Tavily and return normalized search results."""
        return tavily_search(
            api_key=api_key,
            query=query,
            max_results=max(1, min(max_results, 10)),
            search_depth=search_depth,
        )

    return mcp


def main() -> int:
    parser = argparse.ArgumentParser(prog="trace-web-search", description="External MCP server for Tavily web search")
    parser.add_argument("--api-key", default=None, help="Tavily API key override")
    parser.add_argument(
        "--api-key-env-var",
        default="TAVILY_API_KEY",
        help="Environment variable name to read Tavily API key from",
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Do not prompt for an API key when not found in args/env",
    )
    args = parser.parse_args()

    api_key = resolve_tavily_api_key(
        explicit_api_key=args.api_key,
        env_var_name=args.api_key_env_var,
        prompt_if_missing=not args.no_prompt,
    )

    server = _build_server(api_key=api_key)
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
