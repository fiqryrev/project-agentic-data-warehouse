---
name: branch-name
description: Name the branch and worktree for an issue. Use at loop step 2, right after the plan is approved.
---

# branch-name

- Branch: `<issue>-<slug>`, lower case, words joined by `-`, at most 50 characters.
  Example: `7-generator-daily-partitions`. `check_worknote` reads the issue number from it
  when the PR body has no `Closes #<issue>`.
- Worktree: `git worktree add .worktrees/<issue>-<slug> -b <issue>-<slug> origin/main`.
- Never commit on `main`; the Bash hook blocks it.
