Add the thing.

Closes #12

## Pre-merge

- [x] `uv run pytest -q` → PASS
- [x] gitleaks → SKIP[no-network]: ran in CI only
- `check_pr_body` on this body → PASS

## Post-merge

- Close #12 and remove the worktree

## AI usage

```text
Harness Tool: Claude Code
Model Name: claude-opus-5-5 (effort medium), claude-haiku-5-5 (effort low)
Input Token Usage: 1,000 ($0.01) - Cache hit (500, $0.00)
Output Token Usage: 100 ($0.00) - Cache hit (0, $0.00)
Total Token: 1,100 ($0.01) - Cache hit (500, $0.00)
Metadata: 2 requests, 1 session, no subagents; prices from the official page on 2026-11-21; list-price estimate, not money paid
```
<!-- ai-usage-ledger: {"sessions":{"s":{"from":null,"to":"2026-11-21T10:00:00Z"}},"v":1} -->
