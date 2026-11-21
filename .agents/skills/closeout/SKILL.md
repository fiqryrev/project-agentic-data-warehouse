---
name: closeout
description: Close out an issue after its PR is merged. Use at loop step 7 only when the owner says to close out; also the pre-flight check at step 0.
---

# closeout

Only when the owner says so. Merging is never implied.

1. Confirm the PR is merged and `main` is green: `gh pr view <n> --json state,mergeCommit`
   and `gh run list --branch main --limit 1`.
2. Update the worknote's last section with the outcome, if anything changed after merge
   (that is a new small PR, never a push to `main`).
3. Close the issue with a one-line comment linking the PR: `gh issue close <issue> -c "..."`.
4. Remove the worktree and the local branch: `git worktree remove .worktrees/<issue>-<slug>`
   then `git branch -d <issue>-<slug>`.

Pre-flight (step 0): `gh issue list --state open --label milestone` shows no issue whose PR is
already merged; if one does, close it out first.
