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
    assert "llm.golden" in ast.unparse(golden["bash_command"]) and "dag_run.conf" in ast.unparse(golden["bash_command"])
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
