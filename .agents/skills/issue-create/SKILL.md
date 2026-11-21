---
name: issue-create
description: Create or confirm the GitHub issue for a piece of work, label it and move it to In Progress. Use at loop step 4, before any edit is committed.
---

# issue-create

1. Search first: `gh issue list --state all --search "<keywords>"`. Reuse a matching open issue.
2. If none, draft the issue in chat (title, why, done-when, out of scope) and wait for the
   owner's yes. Then `gh issue create --title "<title>" --body-file <file> --label <label>`.
3. Labels: one of `milestone`, `bug`, `chore`, `docs`; add `M<n>` for milestone work.
4. Move it to In Progress on the project board if one exists.
5. Note the issue number: the branch (`branch-name`) and the worknote
   (`docs/task-management/<issue>-<slug>.md`) are named from it.

Never paste secrets, home paths, or personal identifiers into an issue.
