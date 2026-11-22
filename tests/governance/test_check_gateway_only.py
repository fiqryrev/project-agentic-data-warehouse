"""check_gateway_only: a provider URL or key name outside the gateway config fails."""
import pytest

from helpers import check_gateway_only as c
from helpers.govlib import tracked_files


def test_repo_passes():
    assert c.check(tracked_files()) == []


@pytest.mark.parametrize("text, expect", [
    ('client = OpenAI(base_url="https://api.openai.com/v1")', "provider host api.openai.com"),
    ("curl https://openrouter.ai/api/v1/chat/completions", "provider host openrouter.ai"),
    ("url: https://integrate.api.nvidia.com/v1", "provider host integrate.api.nvidia.com"),
    ("key = os.environ['ANTHROPIC_API_KEY']", "provider key name ANTHROPIC_API_KEY"),
    ("export NVIDIA_API_KEY=", "provider key name NVIDIA_API_KEY"),
    ("api_key: os.environ/OPENROUTER_API_KEY", "provider key name OPENROUTER_API_KEY"),
])
def test_provider_reference_found(text, expect):
    assert any(expect in hit for hit in c.scan_text(text)), c.scan_text(text)


@pytest.mark.parametrize("text", [
    "base_url = http://localhost:4000/v1",
    "LITELLM_MASTER_KEY=",
    "REASONING_API_KEY=<gateway virtual key>",
    "we compare OpenRouter and NVIDIA models",
    "see notopenrouter.ai.example",
])
def test_gateway_and_prose_pass(text):
    assert c.scan_text(text) == []


def test_bad_file_fails_and_gateway_config_passes(tmp_path):
    bad = "llm/ask.py"
    ok = ["infra/llm-gateway/config.yaml", ".env.example"]
    for rel in [bad, *ok]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("api_key: os.environ/OPENAI_API_KEY\nhttps://api.openai.com/v1\n")
    errs = c.check([bad, *ok], root=tmp_path)
    assert len(errs) == 2 and all(e.startswith("llm/ask.py line") for e in errs)


def test_lookalike_paths_are_not_allowed():
    assert c.allowed("infra/llm-gateway/config.yaml")
    assert not c.allowed("infra/llm-gateway-old/config.yaml")
    assert not c.allowed("docs/.env.example")
