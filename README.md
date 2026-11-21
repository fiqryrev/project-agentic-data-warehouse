# project-agentic-data-warehouse

A local data warehouse (DuckDB, dbt, Airflow) feeding NVIDIA Auto Ontology, with a LiteLLM
gateway and Langfuse traces. The design is in [PLAN.md](PLAN.md); agents start at
[AGENTS.md](AGENTS.md).

```bash
uv sync
uv run pytest -q
```
