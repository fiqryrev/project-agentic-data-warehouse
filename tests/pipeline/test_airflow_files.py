"""The DAG, compose file and .env helper, read statically (Airflow is not installed locally)."""
import ast
import importlib.util
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
DAG_FILE = REPO / "airflow" / "dags" / "warehouse_daily.py"


def dag_tree():
    return ast.parse(DAG_FILE.read_text(encoding="utf-8"))


def call_kwargs(tree, func_name):
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == func_name:
            out.append({k.arg: k.value for k in node.keywords})
    return out


def test_dag_runs_one_day_at_a_time_in_order():
    dag = call_kwargs(dag_tree(), "DAG")[0]
    assert ast.literal_eval(dag["dag_id"]) == "warehouse_daily"
    assert ast.literal_eval(dag["catchup"]) is True
    assert ast.literal_eval(dag["max_active_runs"]) == 1
    assert ast.literal_eval(dag["is_paused_upon_creation"]) is True
    defaults = {ast.literal_eval(k): v for k, v in zip(dag["default_args"].keys, dag["default_args"].values)}
    assert ast.literal_eval(defaults["depends_on_past"]) is True


def test_dag_has_tasks_1_to_9_in_order():
    tasks = [ast.literal_eval(kw["task_id"]) for kw in call_kwargs(dag_tree(), "BashOperator")]
    assert tasks == ["generate_source", "load_lake", "dbt_build", "quality_gate", "publish_snapshot",
                     "refresh_ontology", "golden_questions", "land_llm_telemetry", "record_run"]
    chain = [n for n in ast.walk(dag_tree()) if isinstance(n, ast.Expr) and isinstance(n.value, ast.BinOp)]
    names = []
    node = chain[0].value
    while isinstance(node, ast.BinOp):
        names.insert(0, node.right.id)
        node = node.left
    names.insert(0, node.id)
    assert names == tasks


def test_refresh_is_skipped_when_the_ontology_profile_is_down():
    refresh = [kw for kw in call_kwargs(dag_tree(), "BashOperator")
               if ast.literal_eval(kw["task_id"]) == "refresh_ontology"][0]
    assert ast.literal_eval(refresh["skip_on_exit_code"]) == 99


def test_golden_is_skippable_and_never_holds_the_next_day():
    tasks = {ast.literal_eval(kw["task_id"]): kw for kw in call_kwargs(dag_tree(), "BashOperator")}
    golden = tasks["golden_questions"]
    assert ast.literal_eval(golden["skip_on_exit_code"]) == 99
    assert "llm.golden" in ast.unparse(golden["bash_command"]) and "GOLDEN_ENABLED" in ast.unparse(golden["bash_command"])
    assert "GOLDEN_FLAG" in ast.unparse(golden["env"]) and ast.literal_eval(golden["append_env"]) is True
    for name in ("golden_questions", "record_run"):
        assert ast.literal_eval(tasks[name]["depends_on_past"]) is False, name


def test_telemetry_runs_after_a_failure_and_skips_without_obs():
    tasks = {ast.literal_eval(kw["task_id"]): kw for kw in call_kwargs(dag_tree(), "BashOperator")}
    t8 = tasks["land_llm_telemetry"]
    assert ast.unparse(t8["trigger_rule"]) == "TriggerRule.ALL_DONE"
    assert ast.literal_eval(t8["skip_on_exit_code"]) == 99
    assert ast.literal_eval(t8["depends_on_past"]) is False
    assert "llm.telemetry" in ast.unparse(t8["bash_command"]) and "--init-only" in ast.unparse(tasks["load_lake"]["bash_command"])


def test_record_run_runs_after_a_failure():
    record = [kw for kw in call_kwargs(dag_tree(), "BashOperator")
              if ast.literal_eval(kw["task_id"]) == "record_run"][0]
    assert ast.unparse(record["trigger_rule"]) == "TriggerRule.ALL_DONE"


def test_dag_writes_only_the_build_file():
    text = DAG_FILE.read_text(encoding="utf-8")
    assert 'BUILD_DB = "data/build/dwh.duckdb"' in text
    assert "--target prod" in text and "data/dev" not in text


def test_compose_binds_ports_to_localhost_and_pins_images():
    doc = yaml.safe_load((REPO / "infra" / "compose.yml").read_text(encoding="utf-8"))
    for name, svc in doc["services"].items():
        assert set(svc["profiles"]) <= {"core", "obs", "ontology"} and svc["profiles"], name
        for port in svc.get("ports", []):
            assert port.startswith("127.0.0.1:"), (name, port)
        image = svc["image"]
        assert (":" in image or "@sha256:" in image) and ":latest" not in image, (name, image)
    assert "airflow/Dockerfile" in doc["services"]["airflow-scheduler"]["build"]["dockerfile"]


def test_compose_takes_every_password_from_env():
    text = (REPO / "infra" / "compose.yml").read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    assert doc["services"]["airflow-db"]["environment"]["POSTGRES_PASSWORD"].startswith("${AIRFLOW_DB_SECRET")
    assert "airflow:${AIRFLOW_DB_SECRET" in text and "airflow:airflow@" not in text
    example = (REPO / ".env.example").read_text(encoding="utf-8")
    assert "AIRFLOW_DB_SECRET=\n" in example and "AIRFLOW_JWT_SECRET=\n" in example


def test_dockerfile_pins_airflow_and_uv():
    text = (REPO / "airflow" / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM apache/airflow:3.3.2-python3.12" in text
    assert "ghcr.io/astral-sh/uv:0.11.8" in text and "--frozen" in text


def load_env_secrets():
    spec = importlib.util.spec_from_file_location("env_secrets", REPO / "airflow" / "env_secrets.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_env_secrets_fills_empty_secrets_and_keeps_set_values(tmp_path):
    mod = load_env_secrets()
    example = tmp_path / ".env.example"
    example.write_text("# c\nA_SECRET=\nPLAIN=x\n")
    env = tmp_path / ".env"
    assert mod.fill(env, example) == ["A_SECRET", "PLAIN"]
    first = mod.parse(env.read_text())
    assert len(first["A_SECRET"]) == 64 and first["PLAIN"] == "x"
    assert mod.fill(env, example) == []
    assert mod.parse(env.read_text()) == first
    env.write_text("A_SECRET=\nPLAIN=y\n")
    assert mod.fill(env, example) == ["A_SECRET"]
    again = mod.parse(env.read_text())
    assert len(again["A_SECRET"]) == 64 and again["PLAIN"] == "y"


def test_runtime_imports_are_project_dependencies():
    """The Airflow image installs the project without the dev group (`--no-dev`), so a module a
    DAG task imports must be a runtime dependency (M10: golden_questions failed on `yaml`)."""
    import tomllib
    deps = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    names = {d.split(">")[0].split("=")[0].split("<")[0].strip().lower() for d in deps}
    assert {"duckdb", "pyyaml"} <= names


def dag_constants() -> dict:
    """The DAG's module-level string constants (RUN_ENV, GOLDEN_FLAG, PY, ...)."""
    out = {}
    for node in dag_tree().body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


def test_no_free_text_template_reaches_a_command_line():
    """S1 (security review 2026-11-23): conf and run id are chosen by whoever triggers a run; they
    reach the shell only through the task environment, double-quoted."""
    consts = dag_constants()
    for kw in call_kwargs(dag_tree(), "BashOperator"):
        cmd = ast.unparse(kw["bash_command"])
        name = ast.literal_eval(kw["task_id"])
        assert "dag_run" not in cmd and "run_id" not in cmd and "conf" not in cmd, name
        if "--run-id" in cmd:
            assert '--run-id "$RUN_ID"' in cmd, name
            assert "RUN_ENV" in ast.unparse(kw["env"]) and ast.literal_eval(kw["append_env"]) is True, name
    assert consts["RUN_ENV"] == {"RUN_ID": "{{ run_id }}"}
    for value in consts.values():
        if isinstance(value, str) and "{{" in value:
            assert "{{ ds }}" in value or value in (consts["GOLDEN_FLAG"], "{{ run_id }}"), value


def render(template: str, conf: dict) -> str:
    """Render like Airflow: a sandboxed Jinja environment with StrictUndefined."""
    import types

    import jinja2.sandbox
    env = jinja2.sandbox.SandboxedEnvironment(undefined=jinja2.StrictUndefined)
    return env.from_string(template).render(dag_run=types.SimpleNamespace(conf=conf))


def test_golden_flag_renders_only_true_or_false():
    flag = dag_constants()["GOLDEN_FLAG"]
    assert render(flag, {}) == "true"                         # scheduled runs ask
    assert render(flag, {"golden": False}) == "false"         # airflow/backfill.sh
    for off in ("false", "False", "0", "no", 0):
        assert render(flag, {"golden": off}) == "false", off
    for hostile in ("x; touch /tmp/pwned", "$(touch /tmp/pwned)", "`id`", "true' && id #", "\nid"):
        assert render(flag, {"golden": hostile}) == "true", hostile


def test_golden_runner_reads_the_flag_as_a_boolean():
    from llm.golden import enabled
    assert enabled("true") and enabled("x; touch /tmp/pwned")
    assert not enabled("false") and not enabled(" FALSE ") and not enabled("0") and not enabled("no")


def test_backfill_turns_golden_off_with_a_boolean():
    text = (REPO / "airflow" / "backfill.sh").read_text(encoding="utf-8")
    assert """conf='{"golden": false}'""" in text


# --- S2 and S9 (security review 2026-11-23) ------------------------------------------------------

COMPOSE = yaml.safe_load((REPO / "infra" / "compose.yml").read_text(encoding="utf-8"))
AIRFLOW_SERVICES = [n for n, s in COMPOSE["services"].items() if "core" in s["profiles"] and n != "airflow-db"]
TASK_KEYS = {"LANGFUSE_PROJECT_PUBLIC_SECRET", "LANGFUSE_PROJECT_SECRET", "LITELLM_MASTER_SECRET", "AO_ADMIN_SECRET"}


def test_airflow_containers_never_see_dot_env():
    """The repository is mounted at /opt/wh; .env is masked so provider keys stay in the gateway."""
    assert AIRFLOW_SERVICES
    for name in AIRFLOW_SERVICES:
        vols = COMPOSE["services"][name]["volumes"]
        assert "/dev/null:/opt/wh/.env:ro" in vols, name
        for v in vols:
            src, _, target = v.partition(":")
            assert not src.rstrip("/").endswith(".env") or src == "/dev/null", (name, v)
            # The repository mount comes before the mask, so the mask wins.
            if target.startswith("/opt/wh:") or target == "/opt/wh":
                assert vols.index(v) < vols.index("/dev/null:/opt/wh/.env:ro"), name


def load_bootstrap():
    spec = importlib.util.spec_from_file_location("gw_bootstrap", REPO / "infra" / "llm-gateway" / "bootstrap.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_airflow_gets_exactly_the_task_keys_and_no_provider_key():
    bootstrap = load_bootstrap()
    for name in AIRFLOW_SERVICES:
        env = COMPOSE["services"][name]["environment"]
        keys = {k for k in env if (k.endswith("_SECRET") or k.endswith("_KEY") or k.startswith("GATEWAY_KEY"))
                and not k.startswith("AIRFLOW__")}          # Airflow's own JWT secret
        assert keys == TASK_KEYS, (name, keys)
        for k in TASK_KEYS:
            assert env[k] == "${" + k + ":-}", k
        assert not set(env) & set(bootstrap.PROVIDER_KEYS), name


def test_read_env_prefers_the_environment(tmp_path, monkeypatch):
    from llm.observe import read_env
    f = tmp_path / ".env"
    f.write_text("A_SECRET=from-file\nB_SECRET=file-only\nC_SECRET=file-c\n")
    monkeypatch.setenv("A_SECRET", "from-env")
    monkeypatch.setenv("C_SECRET", "")                      # empty does not hide the file's value
    env = read_env(f)
    assert env["A_SECRET"] == "from-env" and env["B_SECRET"] == "file-only" and env["C_SECRET"] == "file-c"
    monkeypatch.setenv("D_SECRET", "env-only")
    assert read_env(tmp_path / "missing.env")["D_SECRET"] == "env-only"   # inside Airflow: no file


def test_env_secrets_writes_owner_only(tmp_path):
    mod = load_env_secrets()
    example = tmp_path / ".env.example"
    example.write_text("A_SECRET=\n")
    env = tmp_path / ".env"
    mod.fill(env, example)
    assert env.stat().st_mode & 0o777 == 0o600
    env.chmod(0o644)                                        # an older .env is narrowed on the next write
    env.write_text("A_SECRET=\n")
    mod.fill(env, example)
    assert env.stat().st_mode & 0o777 == 0o600


def test_gateway_bootstrap_writes_owner_only(tmp_path):
    bootstrap = load_bootstrap()
    env = tmp_path / ".env"
    bootstrap.set_env(env, "GATEWAY_KEY_X", "v")
    assert env.stat().st_mode & 0o777 == 0o600
    env.chmod(0o644)
    bootstrap.set_env(env, "GATEWAY_KEY_X", "w")
    assert env.stat().st_mode & 0o777 == 0o600 and bootstrap.read_env(env)["GATEWAY_KEY_X"] == "w"


def test_redis_password_is_not_an_argument():
    redis = COMPOSE["services"]["langfuse-redis"]
    args = " ".join(redis["command"]) + " " + " ".join(redis["healthcheck"]["test"])
    assert "REDIS_SECRET" not in args and "-a" not in redis["healthcheck"]["test"]
    assert "--requirepass" not in args and "redis-server -" in args and "docker-entrypoint.sh" in args
    assert redis["environment"]["REDISCLI_AUTH"] == "${REDIS_SECRET}"
