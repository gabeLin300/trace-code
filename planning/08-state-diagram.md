# 08 - State Diagram

## Goal
Provide a concrete state-machine view of `trace` runtime flow for planning and grading artifacts.

```mermaid
stateDiagram-v2
    [*] --> Startup
    Startup --> SessionReady: bootstrap workspace + load config + start MCP
    SessionReady --> AwaitInput

    AwaitInput --> BuiltinCommand: /help /config /sessions /exit
    BuiltinCommand --> AwaitInput

    AwaitInput --> BuildTaskContext: user task
    BuildTaskContext --> DecideToolNeed

    DecideToolNeed --> LLMAnswer: no tool needed
    LLMAnswer --> PersistTurn

    DecideToolNeed --> ExecuteTool: tool needed
    ExecuteTool --> ToolBlocked: blocked/requires_confirmation/error
    ToolBlocked --> PersistTurn

    ExecuteTool --> DecideNextStep: tool success
    DecideNextStep --> ExecuteTool: model returns TOOL:<command>
    DecideNextStep --> FinalAnswer: model returns FINAL:<answer>
    FinalAnswer --> PersistTurn

    PersistTurn --> AwaitInput
    AwaitInput --> Shutdown: /exit
    Shutdown --> [*]
```

## Notes
- The autonomous loop is bounded by a max-step limit to avoid unbounded execution.
- Non-read shell commands remain governed by safety confirmation policies.
