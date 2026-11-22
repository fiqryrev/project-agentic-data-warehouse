"""Gateway config, budgets, obs compose, bootstrap and smoke helpers, without a network."""
import re
import sys
from pathlib import Path

import yaml

from llm import gateway_smoke as smoke

REPO = Path(__file__).resolve().parents[2]
GW = REPO / "infra" / "llm-gateway"
sys.path.insert(0, str(GW))
import bootstrap  # noqa: E402

COMPOSE_TEXT = (REPO / "infra" / "compose.yml").read_text(encoding="utf-8")
COMPOSE = yaml.safe_load(COMPOSE_TEXT)
SERVICE_TEXT = (GW / "service.yml").read_text(encoding="utf-8")
GATEWAY_ENV = yaml.safe_load(SERVICE_TEXT)["services"]["llm-gateway"]["environment"]
CONFIG = yaml.safe_load((GW / "config.yaml").read_text(encoding="utf-8"))
BUDGETS = yaml.safe_load((GW / "budgets.yaml").read_text(encoding="utf-8"))
ALIASES = {m["model_name"] for m in CONFIG["model_list"]}


def test_aliases_are_the_ones_auto_ontology_and_m12_use():
    assert ALIASES == {"openai/adw-reasoning", "openai/adw-non-reasoning", "openai/adw-or-chat", "adw-embed"}
    embed = [m for m in CONFIG["model_list"] if m["model_name"] == "adw-embed"][0]
    assert embed["litellm_params"]["model"] == "nvidia_nim/nvidia/nemotron-3-embed-1b"


def test_provider_keys_come_from_env_only():
    for m in CONFIG["model_list"]:
        assert m["litellm_params"]["api_key"].startswith("os.environ/"), m["model_name"]
    assert CONFIG["general_settings"]["master_key"] == "os.environ/LITELLM_MASTER_KEY"
    assert CONFIG["litellm_settings"]["callbacks"] == ["langfuse_otel"]
    route = CONFIG["general_settings"]["pass_through_endpoints"][0]
    assert route["path"].endswith("/reranking") and route["auth"] is True


def test_every_caller_has_a_budget_and_only_known_aliases():
    names = [c["name"] for c in BUDGETS["callers"]]
    assert names == ["auto-ontology", "golden-runner", "agent-dev"]
    for c in BUDGETS["callers"]:
        assert 0 < c["max_budget_usd"] <= 5, c["name"]
        assert set(c["models"]) <= ALIASES, c["name"]
        assert re.fullmatch(r"GATEWAY_KEY_[A-Z_]+", c["env"])
    assert BUDGETS["budget_duration"] == "1d"
    assert set(BUDGETS["jobs"]) >= {"ingest", "compile", "chat", "golden"}


def test_key_request_carries_budget_models_and_caller_tag():
    caller = BUDGETS["callers"][2]
    body = bootstrap.key_request(caller, "1d")
    assert body == {"key_alias": "agent-dev", "max_budget": 0.5, "budget_duration": "1d",
                    "models": caller["models"], "metadata": {"tags": ["caller:agent-dev"]}}


def test_set_env_replaces_or_appends(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\nGATEWAY_KEY_AGENT_DEV=\n")
    bootstrap.set_env(env, "GATEWAY_KEY_AGENT_DEV", "sk-x")
    bootstrap.set_env(env, "NEW", "y")
    assert bootstrap.read_env(env) == {"A": "1", "GATEWAY_KEY_AGENT_DEV": "sk-x", "NEW": "y"}


def test_check_keys_names_missing_provider_keys(tmp_path, capsys):
    env = tmp_path / ".env"
    present, missing = bootstrap.PROVIDER_KEYS     # names stay in infra/llm-gateway/ (check_gateway_only)
    env.write_text(f"{present}=x\n{missing}=\n")
    assert bootstrap.check_keys(env) == 1
    assert missing in capsys.readouterr().out


def test_obs_services_are_pinned_by_digest_and_local():
    obs = {n: s for n, s in COMPOSE["services"].items() if "obs" in s["profiles"]}
    assert set(obs) == {"obs-db", "llm-gateway", "langfuse-worker", "langfuse-web",
                        "langfuse-clickhouse", "langfuse-minio", "langfuse-redis"}
    for name, svc in obs.items():
        if name != "obs-db":
            assert "@sha256:" in svc["image"], name
    assert COMPOSE["services"]["llm-gateway"]["ports"] == ["127.0.0.1:4000:4000"]
    assert COMPOSE["services"]["langfuse-web"]["ports"] == ["127.0.0.1:3001:3000"]
    assert COMPOSE["services"]["langfuse-worker"]["environment"]["TELEMETRY_ENABLED"] == "false"


def test_every_compose_variable_is_in_env_example():
    used = set(re.findall(r"\$\{([A-Z0-9_]+)", COMPOSE_TEXT + SERVICE_TEXT))
    example = set(re.findall(r"^([A-Z0-9_]+)=", (REPO / ".env.example").read_text(encoding="utf-8"), re.M))
    assert used - {"GIT_SHA"} <= example, used - example


def test_gateway_environment_comes_from_service_yml():
    gw = COMPOSE["services"]["llm-gateway"]
    assert gw["extends"] == {"file": "llm-gateway/service.yml", "service": "llm-gateway"}
    assert "environment" not in gw and "_API_KEY" not in COMPOSE_TEXT
    assert GATEWAY_ENV["LANGFUSE_OTEL_HOST"] == "http://langfuse-web:3000"


def test_no_literal_secret_in_compose():
    envs = [svc.get("environment") or {} for svc in COMPOSE["services"].values()] + [GATEWAY_ENV]
    for env in envs:
        for key, value in env.items():
            if re.search(r"PASSWORD|SECRET|_KEY$|AUTH$", key) and key != "LANGFUSE_INIT_USER_EMAIL":
                assert "${" in str(value), key


GEN = {"type": "GENERATION", "id": "g1", "model": "openai/adw-or-chat", "inputUsage": 24,
       "outputUsage": 117, "totalUsage": 141, "costDetails": {"total": 2.5e-05},
       "metadata": {"attributes.llm.response.id": "gen-1", "attributes.litellm.key_alias": "agent-dev",
                    "attributes.langfuse.trace.tags": ["job:smoke", "caller:agent-dev", "User-Agent: x"]}}


def test_find_generation_matches_the_response_id():
    span = {"type": "SPAN", "metadata": {"attributes.llm.response.id": "gen-1"}}
    assert smoke.find_generation([span, GEN], "gen-1") is GEN
    assert smoke.find_generation([GEN], "gen-2") is None


def test_generation_facts():
    f = smoke.generation_facts(GEN)
    assert (f["total_tokens"], f["cost_usd"], f["caller"]) == (141, 2.5e-05, "agent-dev")
    assert {"job:smoke", "caller:agent-dev"} <= set(f["tags"])


def test_budget_refusal_is_recognised_and_hides_the_key():
    body = {"error": {"type": "budget_exceeded", "code": "422", "message":
                      "Budget has been exceeded! Key=smoke (sk-...abcd) Current cost: 2e-05, Max budget: 1e-06"}}
    assert smoke.is_budget_refusal(422, body)
    assert not smoke.is_budget_refusal(200, body)
    assert not smoke.is_budget_refusal(500, {"error": {"type": "server"}})
    assert smoke.budget_numbers(body) == "Current cost: 2e-05, Max budget: 1e-06"
    assert "sk-" not in smoke.budget_numbers(body)
