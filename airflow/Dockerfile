# Airflow plus the project's own Python environment (generator, loader, dbt v2).
# Airflow keeps its own environment; the project runs from /opt/wh-venv through uv, so the two
# never share packages. Built by infra/compose.yml (profile core).
FROM apache/airflow:3.4.0-python3.12@sha256:818f94affc5bd7ce0be0cc04f2ace09aa8382e65190a73a08881229ff32700cb

USER root
COPY --from=ghcr.io/astral-sh/uv:0.11.8@sha256:3b7b60a81d3c57ef471703e5c83fd4aaa33abcd403596fb22ab07db85ae91347 /uv /usr/local/bin/uv
RUN mkdir -p /opt/wh-venv /opt/wh-build && chown airflow: /opt/wh-venv /opt/wh-build

USER airflow
ENV UV_PROJECT_ENVIRONMENT=/opt/wh-venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_NO_SYNC=1
WORKDIR /opt/wh-build
COPY --chown=airflow pyproject.toml uv.lock ./
RUN uv sync --frozen --group dbt --no-dev --no-install-project \
 && /opt/wh-venv/bin/dbt --version
# dbt downloads its DuckDB driver on first use; fetch it now so runs never need the network.
RUN /opt/wh-venv/bin/dbt system install-drivers
WORKDIR /opt/wh
