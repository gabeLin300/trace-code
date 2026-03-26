# 09 - Sequence Diagrams

## Scenario A: Documentation Question with Local RAG MCP

```mermaid
sequenceDiagram
    participant U as User
    participant CLI as CLI Interface
    participant AG as Agent Loop
    participant LM as LLM Provider
    participant KM as Local Knowledge MCP

    U->>CLI: "search langchain docs for retrieval"
    CLI->>AG: start task
    AG->>KM: knowledge.search_langchain_docs(query)
    KM-->>AG: retrieved chunks
    AG->>LM: decide next step with tool output
    LM-->>AG: FINAL: synthesized answer
    AG-->>CLI: final response + tool trace
    CLI-->>U: display tool call and answer
```

## Scenario B: Read File then Edit via Iterative Tool Calls

```mermaid
sequenceDiagram
    participant U as User
    participant CLI as CLI Interface
    participant AG as Agent Loop
    participant LM as LLM Provider
    participant FS as Filesystem MCP

    U->>CLI: "read app.py and update greeting"
    CLI->>AG: start task
    AG->>FS: fs.read(app.py)
    FS-->>AG: file content
    AG->>LM: decide next step with read output
    LM-->>AG: TOOL: run command apply patch...
    AG->>FS: fs.write/apply change
    FS-->>AG: write success
    AG->>LM: decide next step with write result
    LM-->>AG: FINAL: change summary
    AG-->>CLI: final response + tool trace
    CLI-->>U: show steps and completion
```

## Scenario C: Recency Query with External Web MCP

```mermaid
sequenceDiagram
    participant U as User
    participant CLI as CLI Interface
    participant AG as Agent Loop
    participant WEB as Tavily MCP
    participant LM as LLM Provider

    U->>CLI: "latest langchain release changes?"
    CLI->>AG: start task
    AG->>WEB: web.search(query)
    WEB-->>AG: answer + sources
    AG->>LM: decide next step with web results
    LM-->>AG: FINAL: concise summary
    AG-->>CLI: final response + tool trace
    CLI-->>U: display web tool call and summary
```
