"""Auto Ontology wiring (compose, overlay, edge) and the ontology-check helpers, without a network."""
import re
from pathlib import Path

import yaml

from llm import ontology_check as oc

REPO = Path(__file__).resolve().parents[2]
AO_DIR = REPO / "infra" / "auto-ontology"
COMPOSE = yaml.safe_load((REPO / "infra" / "compose.yml").read_text(encoding="utf-8"))
SVC = COMPOSE["services"]
AO_SERVICES = ("auto-ontology-migrate", "frontend-migrate", "ingestion-service", "auto-ontology",
               "auto-ontology-frontend", "ao-db", "ao-seed")


def test_upstream_is_pinned_and_images_carry_the_sha():
    sha = (AO_DIR / "UPSTREAM_SHA").read_text().strip()
    assert re.fullmatch(r"[0-9a-f]{40}", sha)
    for name in ("auto-ontology", "auto-ontology-frontend"):
        assert SVC[name]["image"].endswith(":" + sha[:12]), name
    assert "infra/auto-ontology/upstream/" in (REPO / ".gitignore").read_text()


def test_overlay_patches_are_small_and_targeted():
    patches = sorted((AO_DIR / "patches").glob("*.patch"))
    assert [p.name for p in patches] == ["0001-duckdb-connector-reads-comments.patch",
                                         "0002-chat-api-calculation-only.patch",
                                         "0003-request-id-tags-model-calls.patch",
                                         "0004-change-notices.patch"]
    first, second, third, _ = (p.read_text() for p in patches)
    assert re.findall(r"^\+\+\+ b/(.+)$", first, re.M) == ["auto_ontology/connectors/duckdb.py"]
    assert "duckdb_tables()" in first and "duckdb_columns()" in first and "AS description" in first
    # 0002 (issue 34): the chat API passes calculation_only through to the text-to-SQL agent.
    assert re.findall(r"^\+\+\+ b/(.+)$", second, re.M) == [
        "auto_ontology/server/chat/helpers.py", "auto_ontology/server/chat/router.py",
        "auto_ontology/server/chat/worker.py"]
    assert "calculation_only: bool | None" in second and '"calculation_only": calculation_only' in second
    # 0003 (issue 36): a request id from the chat API tags every model call (chat, embed, rerank).
    touched = re.findall(r"^\+\+\+ b/(.+)$", third, re.M)
    assert {"auto_ontology/utils/request_tags.py", "auto_ontology/utils/llm_invoke.py",
            "auto_ontology/utils/embedding.py", "auto_ontology/utils/rerank.py"} <= set(touched)
    assert "x-litellm-tags" in third and "set_request_id(request_id)" in third


def test_every_patched_file_carries_a_change_notice():
    """Apache-2.0 section 4(b), Codex review on #66: every file the functional patches modify or add
    gets a notice that it was changed (0004, applied last), below NVIDIA's own header, which stays."""
    patches = sorted((AO_DIR / "patches").glob("*.patch"))
    functional, notices = patches[:-1], patches[-1].read_text()
    touched = {f for p in functional for f in re.findall(r"^\+\+\+ b/(.+)$", p.read_text(), re.M)}
    noticed = set(re.findall(r"^\+\+\+ b/(.+)$", notices, re.M))
    assert touched and touched == noticed, (touched - noticed, noticed - touched)
    added = [ln for ln in notices.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    assert all("project-agentic-data-warehouse" in ln or "Apache License" in ln or "applied at build" in ln
               for ln in added), added
    assert not [ln for ln in notices.splitlines() if ln.startswith("-") and not ln.startswith("---")]


def test_auto_ontology_has_no_way_out_but_the_gateway():
    nets = COMPOSE["networks"]
    assert nets["ontology"]["internal"] is True
    for name in AO_SERVICES:
        assert SVC[name]["networks"] == ["ontology"], name
        assert "ports" not in SVC[name], name
    assert set(SVC["llm-gateway"]["networks"]) == {"default", "ontology"}
    assert set(SVC["ao-edge"]["networks"]) == {"default", "ontology"}
    assert SVC["ao-edge"]["ports"] == ["127.0.0.1:3000:3000"]


def test_edge_publishes_the_ui_only():
    conf = (AO_DIR / "edge.conf").read_text()
    assert re.findall(r"listen (\d+);", conf) == ["3000"]
    assert "auto-ontology-frontend:3000" in conf and "auto-ontology:3001" not in conf


def test_every_model_role_points_at_the_gateway_with_the_caller_key():
    env = SVC["auto-ontology"]["environment"]
    for role in ("DEFAULT_MODELS", "REASONING", "NON_REASONING", "EMBED"):
        assert env[f"{role}_ENDPOINT"] == "http://llm-gateway:4000/v1", role
        assert env[f"{role}_API_KEY"] == "${GATEWAY_KEY_AUTO_ONTOLOGY:-}", role
    assert env["RERANK_ENDPOINT"].startswith("http://llm-gateway:4000/") and env["RERANK_ENDPOINT"].endswith("/reranking")
    assert env["CONNECTION_STRINGS"] == "duckdb:///data/serve/analytics.duckdb"
    assert env["EMBED_MODEL"] == "adw-embed"


def test_serve_directory_is_mounted_read_only():
    for name in ("ingestion-service", "auto-ontology"):
        assert "../data/serve:/data/serve:ro" in SVC[name]["volumes"], name


def test_socket_proxy_allows_only_the_two_restarts():
    cmd = " ".join(SVC["docker-proxy"]["command"])
    allow_post = re.search(r"-allowPOST=(\S+)", cmd).group(1)
    pattern = re.compile(allow_post)
    assert pattern.match("/v1.41/containers/wh-auto-ontology-1/restart")
    assert pattern.match("/v1.41/containers/wh-ingestion-service-1/restart")
    for bad in ("/v1.41/containers/wh-ao-db-1/restart", "/v1.41/containers/create",
                "/v1.41/containers/wh-auto-ontology-1/stop", "/v1.41/containers/wh-auto-ontology-1/exec"):
        assert not pattern.match(bad), bad
    assert "-allowfrom=airflow-scheduler" in cmd
    assert ":ro" in SVC["docker-proxy"]["volumes"][0]


def test_compile_flag_is_seeded_before_ingestion_starts():
    seed = " ".join(SVC["ao-seed"]["command"])
    assert "semantic_compilation_enabled" in seed and "on conflict (key) do nothing" in seed
    assert SVC["ingestion-service"]["depends_on"]["ao-seed"]["condition"] == "service_completed_successfully"


def test_numbers_in_reads_the_json_string_rows_auto_ontology_sends():
    assert oc.numbers_in(['[{"net_revenue_idr":718545885.0}]']) == [718545885.0]
    assert oc.numbers_in([{"a": 1, "b": "x"}, [2, "3"]]) == [1.0, 2.0, 3.0]
    assert oc.numbers_in(None) == [] and oc.numbers_in([True]) == []


def test_answer_matches_within_a_rupiah():
    answer = {"sql_response_from_db": ['[{"net_revenue_idr":901257780.0}]']}
    assert oc.answer_matches(answer, 901257780) and oc.answer_matches(answer, 901257781)
    assert not oc.answer_matches(answer, 901257790)
    assert not oc.answer_matches({"sql_response_from_db": None}, 1)


def test_caller_of_reads_dict_or_json_metadata():
    assert oc.caller_of({"metadata": {"user_api_key_alias": "auto-ontology"}}) == "auto-ontology"
    assert oc.caller_of({"metadata": '{"user_api_key_alias": "agent-dev"}'}) == "agent-dev"
    assert oc.caller_of({}) is None
