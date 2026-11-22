---
name: label-review
description: Turn human labels from the Langfuse queue answer-review into golden questions, da- entries and dbt issues. Use when the owner asks to process labels, or after a labelling session.
---

# label-review

Labels are given by a person in Langfuse (http://127.0.0.1:3001, queue `answer-review`, the
form in `infra/langfuse/scores.yaml`). This skill turns them into reviewed changes (PLAN 8.4).

1. Dry run: `make label-prs`. It lists every new label (trace, labeller, verdict) and what it
   becomes; labels already in `evals/labels/processed.yaml` are skipped.
2. Show the owner the list and wait for a yes. A label written by an agent (labeller `api`) is
   said to be one.
3. `make label-prs OPEN=1`: one issue, one worktree under `.worktrees/`, one worknote, one PR
   (golden questions, `da-` entries, the label record), plus a dbt issue per `wrong_grain` or
   `wrong_number`. The PR body proposes ontology corrections; never apply one in Auto Ontology
   without the owner.
4. Read each new `da-` entry: tighten the title and Terms to the term that was misread, and
   re-run its Counts SQL (skill `knowledge-add`). Push to the same PR.
5. Never merge. Remove the batch worktree after the owner merges it (skill `closeout`).
