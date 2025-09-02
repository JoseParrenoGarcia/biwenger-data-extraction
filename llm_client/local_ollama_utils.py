# === FILE: llm_client/local_ollama_utils.py ===
import os
import toml
import logging
import requests
from typing import Optional, Dict, Any, List

from openai import OpenAI
from requests.exceptions import ConnectionError as RequestsConnectionError, ReadTimeout as RequestsReadTimeout

DEFAULT_LOCAL_BASE_URL = "http://localhost:11434/v1"  # Ollama OpenAI-compatible endpoint
DUMMY_API_KEY = "ollama"  # Required by OpenAI client but ignored by Ollama


# ---------- Paths & Config ----------
def _repo_root() -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(current_dir, ".."))

def _local_secrets_path() -> str:
    return os.path.join(_repo_root(), "secrets", "local.toml")

def load_local_ollama_secrets() -> Dict[str, Any]:
    """
    Reads secrets/local.toml.

    Example:
        [local]
        base_url = "http://localhost:11434/v1"
        model = "llama3.1"
        request_timeout_sec = 180
        max_input_chars = 900000
    """
    path = _local_secrets_path()
    if not os.path.exists(path):
        # Provide sane defaults even if the file doesn't exist
        return {
            "local": {
                "base_url": DEFAULT_LOCAL_BASE_URL,
                "model": "llama3.1",
                "request_timeout_sec": 180,
                "max_input_chars": 900_000,
            }
        }
    return toml.load(path)


# ---------- Utilities ----------
def _truncate_chars(text: str, max_chars: Optional[int]) -> str:
    if not max_chars or max_chars <= 0:
        return text
    return text if len(text) <= max_chars else text[:max_chars]

def list_local_models(base_url: str = DEFAULT_LOCAL_BASE_URL) -> List[str]:
    """
    Returns locally-available model names (those you've 'pulled' into Ollama).
    Uses the native Ollama endpoint /api/tags rather than the OpenAI shim.
    """
    host = base_url.replace("/v1", "")
    try:
        resp = requests.get(f"{host}/api/tags", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


# ---------- Main call ----------
def call_local_ollama_chat_model(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,                 # e.g. "llama3.1", "gpt-oss:20b", "gemma3:4b"
    temperature: float = 0.3,
    logger: Optional[logging.Logger] = None,
    base_url: Optional[str] = None,              # override if needed
    request_timeout_sec: Optional[int] = None,   # total request timeout
    max_input_chars: Optional[int] = None        # crude guard for context
) -> str:
    """
    Calls a local LLM served by Ollama via its OpenAI-compatible Chat Completions API.
    You can pick the model per call. Uses simple char-based truncation to avoid
    overfilling the context window (token-accurate control can be added later).
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    cfg = load_local_ollama_secrets().get("local", {})
    base_url = base_url or cfg.get("base_url", DEFAULT_LOCAL_BASE_URL)
    model = model or cfg.get("model", "llama3.1")
    request_timeout_sec = request_timeout_sec or cfg.get("request_timeout_sec", 180)
    max_input_chars = max_input_chars or cfg.get("max_input_chars", 900_000)

    # Health check: is Ollama up?
    try:
        host = base_url.replace("/v1", "")
        requests.get(f"{host}/api/version", timeout=3)
    except (RequestsConnectionError, RequestsReadTimeout):
        logger.error("❌ Could not reach Ollama. Is `ollama serve` running?")
        return ""

    client = OpenAI(base_url=base_url, api_key=DUMMY_API_KEY, timeout=request_timeout_sec)

    sp = _truncate_chars(system_prompt or "", max_input_chars // 2)       # leave headroom for user + response
    up = _truncate_chars(user_prompt or "", max_input_chars - len(sp))

    try:
        logger.info(f"🔁 Calling local model via Ollama: model='{model}', base_url='{base_url}'")
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sp},
                {"role": "user", "content": up},
            ],
            temperature=temperature,
        )
        if resp and resp.choices and resp.choices[0].message:
            return (resp.choices[0].message.content or "").strip()
        logger.warning("⚠️ Local model returned no choices.")
        return ""
    except Exception as e:
        logger.error(f"❌ Local model call failed: {e}")
        return ""


# ---------- CLI test ----------
if __name__ == "__main__":
    import argparse

    # Basic logger
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )
    log = logging.getLogger("local_ollama_utils_test")

    # Load secrets/config
    cfg = load_local_ollama_secrets().get("local", {})
    default_base_url = cfg.get("base_url", DEFAULT_LOCAL_BASE_URL)
    default_model = cfg.get("model", "llama3.1")

    # CLI args let you override model & prompts easily
    parser = argparse.ArgumentParser(description="Smoke test for local Ollama chat call.")
    parser.add_argument("--model", type=str, default=default_model, help="Model name to use (e.g. llama3.1, gpt-oss:20b)")
    parser.add_argument("--base-url", type=str, default=default_base_url, help="OpenAI-compatible base URL (Ollama).")
    args = parser.parse_args()

    # Show which models are available
    available = list_local_models(args.base_url)
    if available:
        print("📦 Local models found:", ", ".join(available))
    else:
        print("⚠️ No local models reported. Did you run `ollama pull <model>`?")

    # Example prompts (mirroring your Gemini test)
    system_prompt = "You are a helpful assistant that filters football news articles for fantasy relevance."
    user_prompt = """
    Here are 3 article headlines:
    1. 'Real Madrid closes training session to prepare for El Clasico.'
    2. 'Top 10 LaLiga stadiums ranked by attendance.'
    3. 'Barcelona to rest several starters ahead of Champions League.'

    Which of these are relevant for a fantasy football manager where we are interested in possible lineups? Return only the useful headlines.
    """

    result = call_local_ollama_chat_model(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model="gemma3:4b",
        base_url=args.base_url,
        logger=log,
    )

    print("🤖 Local model response:\n")
    print(result or "[Empty response]")
