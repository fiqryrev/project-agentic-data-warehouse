---
name: pr-open
description: Write the PR body and open the pull request. Use at loop step 6, only after the owner says yes to commit and PR.
---

# pr-open

Body sections, in this order (`check_pr_body` enforces them):

```markdown
<summary: what changed and why, a few lines>

Closes #<issue>

## Pre-merge

- <check you ran> → PASS
- <check that failed> → FAIL: <reason>          (blocks the merge)
- <check you skipped> → SKIP[<rule>]: <reason>

## Post-merge

- <what happens after merge, e.g. close the issue, remove the worktree>

## AI usage
```

Then render the footer, which replaces the `## AI usage` section with the fixed six-line
block and the hidden ledger line:

```bash
uv run python helpers/ai_usage_footer.py render --body-file pr-body.md --prior-from-gh
uv run python -m helpers.check_pr_body --body-file pr-body.md
gh pr create --title "<type>: <title>" --body-file pr-body.md
```

- No tool watermark ("Generated with ...", "Co-Authored-By:") in the body.
- After every later push that changes the work, re-render with `--pr <number>` and
  `gh pr edit <number> --body-file pr-body.md`.
- Answer and resolve every review thread before asking the owner to merge.
