#!/usr/bin/env python3
"""Test Tavily API key availability and direct search."""

import os
from pathlib import Path

# Load .env manually
from trace_code.config_init import _load_env_values, _resolve_env_path
from trace_code.config import TraceSettings
from trace_code.mcp.web_search_server import resolve_tavily_api_key, tavily_search

settings = TraceSettings()
env_path = _resolve_env_path(Path(settings.workspace_root))
env_values = _load_env_values(env_path)

print(f"✓ Config loaded from: {env_path}")
print(f"✓ Keys in .env: {list(env_values.keys())}")

# Load into environment
for key, value in env_values.items():
    if key and value:
        os.environ[key] = value

# Test API key resolution
try:
    api_key = resolve_tavily_api_key(
        explicit_api_key=None,
        env_var_name="TAVILY_API_KEY",
        prompt_if_missing=False,
    )
    print(f"✓ TAVILY_API_KEY resolved: {api_key[:20]}...")
except Exception as e:
    print(f"✗ Failed to resolve API key: {e}")
    exit(1)

# Test actual search
try:
    result = tavily_search(
        api_key=api_key,
        query="langchain documentation",
        max_results=3,
        search_depth="basic",
    )
    print(f"\n✓ Tavily API call succeeded!")
    print(f"  Answer: {result.get('answer', 'N/A')[:100]}")
    print(f"  Results: {len(result.get('results', []))} found")
    for r in result.get('results', []):
        print(f"    - {r['title'][:60]}: {r['url']}")
except Exception as e:
    print(f"✗ Tavily API call failed: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
