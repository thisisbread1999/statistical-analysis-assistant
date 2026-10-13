"""Configure Model A and Model B separately (cloud APIs or local Ollama models), or the mock stand-ins.

MODEL_A / MODEL_B use the format provider:model, e.g. openai:gpt-4.1-mini, anthropic:claude-sonnet-5-5,
ollama:qwen3:8b. LLM_MODE is real, mock, or auto (real when every chosen model is usable).
"""
import os

from . import settings

PROVIDERS = ("openai", "anthropic", "google_genai", "ollama")
KEY_FOR_PROVIDER = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "google_genai": "GOOGLE_API_KEY"}
DEFAULT_MODEL_A = "ollama:qwen3:8b"
DEFAULT_MODEL_B = "ollama:gemma3:12b"


def load_env() -> None:
    """Read API keys and model names from the project's .env file, if python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
        load_dotenv(settings.PROJECT_DIR / ".env")
    except ImportError:
        pass


def resolved_model(model_name: str) -> tuple:
    """(provider, model) as init_chat_model resolves it,
    e.g. 'gpt-4.1-mini' -> ('openai', 'gpt-4.1-mini'), 'ollama:qwen3:8b' -> ('ollama', 'qwen3:8b')."""
    name = model_name.strip().lower()
    prefix, _, rest = name.partition(":")
    if prefix in PROVIDERS and rest:
        if prefix == "ollama" and ":" not in rest:
            rest += ":latest"
        return prefix, rest
    provider = ("openai" if name.startswith(("gpt-", "o1", "o3", "o4", "chatgpt")) else
                "anthropic" if name.startswith("claude") else
                "google_genai" if name.startswith("gemini") else "")
    return provider, name


def key_present(model_name: str) -> bool:
    provider, _ = resolved_model(model_name)
    if not provider:
        raise ValueError("Use a supported provider:model identifier.")
    env_var = KEY_FOR_PROVIDER.get(provider)
    return env_var is None or bool(os.getenv(env_var))


def check_ollama_models(model_names: list) -> None:
    """For local models: is the Ollama app running, and have the models been downloaded?"""
    import requests
    wanted = [resolved_model(n)[1] for n in model_names if resolved_model(n)[0] == "ollama"]
    if not wanted:
        return
    try:
        response = requests.get(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/") + "/api/tags", timeout=5)
        response.raise_for_status()
        tags = response.json()
    except (requests.RequestException, ValueError):
        raise RuntimeError("Ollama is not running: start the Ollama app, then try again.")
    have = {m["name"] for m in tags.get("models", [])}
    missing = [m for m in wanted if (m if ":" in m else m + ":latest") not in have]
    if missing:
        raise RuntimeError(f"Download the local model(s) first, e.g.  ollama pull {missing[0]}")
    digests = {m["name"]: m.get("digest") for m in tags.get("models", [])}
    identities = [digests[m] or m for m in wanted]
    if len(set(identities)) != len(identities):
        raise ValueError("Model A and Model B resolve to the same Ollama weights; choose distinct models.")


def make_chat_model(model_name: str):
    """Create one chat model. Cloud APIs and local Ollama models take different settings."""
    from langchain.chat_models import init_chat_model
    if resolved_model(model_name)[0] == "ollama":
        # Low temperature reduces sampling variation; it does not guarantee reproducibility.
        # "Thinking" is off by default because it made one call take ~100 s; OLLAMA_THINKING=on enables it.
        thinking = os.getenv("OLLAMA_THINKING", "off").lower() == "on"
        return init_chat_model(model_name, num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "16384")),
                               num_predict=int(os.getenv("OLLAMA_NUM_PREDICT", "4096")), temperature=0,
                               reasoning=thinking, base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                               client_kwargs={"timeout": float(os.getenv("OLLAMA_TIMEOUT", "180"))})
    # Cloud model: no temperature argument, because several current models only accept their default value.
    return init_chat_model(model_name, max_tokens=16000, timeout=180, max_retries=2)


def resolve_configuration() -> dict:
    """Read MODEL_A, MODEL_B and LLM_MODE (after .env) and decide the mode actually used."""
    load_env()
    model_a = os.getenv("MODEL_A", DEFAULT_MODEL_A)
    model_b = os.getenv("MODEL_B", DEFAULT_MODEL_B)
    mode = os.getenv("LLM_MODE", "auto").lower()
    if mode == "auto":
        mode = "real" if (key_present(model_a) and key_present(model_b)) else "mock"
        if mode == "real":
            try:
                check_ollama_models([model_a, model_b])
            except RuntimeError:
                mode = "mock"
    if mode not in ("real", "mock"):
        raise ValueError("LLM_MODE must be 'real', 'mock' or 'auto'")
    return {"mode": mode, "model_a": model_a, "model_b": model_b}


def create_agents(configuration: dict | None = None):
    """Return (agent_a, agent_b, configuration). Model A and Model B are created by separate calls."""
    from .agents import AnalysisAgentA, MockAnalysisAgentA, MockReviewAgentB, ReviewAgentB
    configuration = configuration or resolve_configuration()
    if configuration["mode"] == "mock":
        return MockAnalysisAgentA(), MockReviewAgentB(), configuration
    if resolved_model(configuration["model_a"]) == resolved_model(configuration["model_b"]):
        raise ValueError("Model A and Model B must be different underlying models.")
    check_ollama_models([configuration["model_a"], configuration["model_b"]])
    agent_a = AnalysisAgentA(make_chat_model(configuration["model_a"]), configuration["model_a"])
    agent_b = ReviewAgentB(make_chat_model(configuration["model_b"]), configuration["model_b"])
    return agent_a, agent_b, configuration
