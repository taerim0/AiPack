"""GeminiProvider's model resolution -- constructed URL only, no network
calls (checking .url is enough to verify precedence without needing a real
API key or GEMINI_MODEL to reach through to an actual request).
"""

import llm


def _model_in_url(provider) -> str:
    return provider.url.split("/models/")[1].split(":")[0]


def test_gemini_provider_defaults_to_default_model_with_no_override(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert _model_in_url(llm.GeminiProvider(api_key="x")) == llm.GeminiProvider.DEFAULT_MODEL


def test_gemini_provider_env_var_overrides_the_default(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash")
    assert _model_in_url(llm.GeminiProvider(api_key="x")) == "gemini-3.5-flash"


def test_gemini_provider_explicit_arg_wins_over_env_var(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash")
    provider = llm.GeminiProvider(api_key="x", model="gemini-3.7-flash")
    assert _model_in_url(provider) == "gemini-3.7-flash"
