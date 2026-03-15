# 07 - End-to-End Acceptance Scenario

## Goal
Define the baseline Milestone 1 smoke scenario that must pass before advancing phases.

## Scope
- In scope: one happy-path end-to-end CLI flow validating startup UX, session lifecycle, tool execution, and persistence.
- Out of scope: exhaustive provider or failure-mode coverage (covered by broader test matrix and later suites).

## Design

### Scenario: Baseline Interactive Flow
1. Launch `trace` in an empty or fresh workspace.
2. Verify ASCII startup banner is shown when `ui.show_banner=true` and no `--no-banner` flag is supplied.
3. Start a new session and verify a session file is created under `.assistant/sessions/`.
4. Submit a user request that triggers a read-only tool call.
5. Verify tool execution result is displayed and summarized.
6. Exit and relaunch `trace`.
7. Resume prior session and verify chat/tool history consistency.

### Required Preconditions
- Default provider route set to Ollama `qwen3:8b-instruct` (or deterministic fallback route available).
- Workspace bootstrap and session persistence are enabled.
- Safety policy defaults are active.

### Pass/Fail Criteria
- PASS when all scenario steps complete without manual data repair.
- FAIL if banner behavior is inconsistent with config/flag, session is not persisted/reloaded, or tool result is not retained in history.

## Acceptance Criteria
- Scenario can be executed both manually and via automated smoke test harness.
- Outputs and state transitions are deterministic enough for CI gating.
- Scenario remains aligned with current technical spec and roadmap milestones.

## Notes
This scenario is the minimum integration gate for completing Milestone 1.
