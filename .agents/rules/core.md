# Core rules (one line each; the story is in history/core.md)

1. Plan before edit: no file changes until the owner approves the plan in chat.
2. Branch, never the default: work on `<issue>-<slug>` in `.worktrees/`; never commit or push `main`.
3. Never merge unless the owner tells you to merge a named PR; the owner runs the merge.
4. No secrets, home paths or personal identifiers in any file, issue, PR or log line.
5. Every number cites its query: a figure in a PR, worknote or answer names the SQL or command behind it.
6. Ask before commit, push, PR or issue changes; one approval covers one action.
7. Verify a literal before filtering on it: profile the column (`GROUP BY`) or cite a `da-` entry verified within 90 days.
8. Every PR touches its issue's worknote and ends with the `## AI usage` footer rendered by the helper.
9. Every pre-merge item ends in `→ PASS`, `→ FAIL: reason` or `→ SKIP[rule]: reason`.
10. Log each decision point and external call with `helpers/log_agent_action.py`.
11. Secrets live only in the gitignored `.env`; never print or commit it.
12. Agents read data through the read-only serving snapshot; only Airflow writes the daily build file.
