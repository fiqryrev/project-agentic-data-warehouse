# 38: README presents the repository as an end-to-end agentic data warehouse

## Goal

The README was 11 lines. A first-time reader should see what the project does end to end, what
it showcases, how it is built, why it works, what it has shown so far, how to run it, and its
limits, with every number citing a file in the repository.

## Plan (as approved)

Approved in chat on 2026-11-22: pitch; what you can do (commands and outcomes); architecture
(Mermaid: data flow, DAG tasks 1 to 9, gateway and Langfuse, the label feedback loop); why it
works (design choices with evidence); results with sources; repository map; quickstart pointing to
the runbook; status (M0 to M12 with PRs); honest limits.

## Decisions

- **English**, like the rest of the repository; Mermaid, which GitHub renders, for the two
  diagrams (architecture and feedback loop).
- **Three kinds of agent named up front** (chat agent, coding agent, person) with what checks
  each, since that is what makes the warehouse "agentic" rather than a warehouse with a chatbot.
- **Every number has a source:** run reports in `docs/runs/`, worknotes in
  `docs/task-management/`, and model counts from the layer folders. No number without one.
- **PR references are full links**: a bare `#3` is not linked in a rendered README.
- **No upstream material**: the overlay patches are described as part of this project only.

## Done

- `README.md` rewritten (208 lines); `check_secrets`, `check_gateway_only`, `check_entry_size` OK;
  `uv run pytest -q` and `make checks` PASS.

## Open

- Re-check the Results table when the golden set grows or a new comparison runs.
- Knowledge: no new lesson.
