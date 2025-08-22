from llm_client.openai_utils import call_openai_chat_model
from llm_client.googleai_utils import call_gemini_chat_model

import os
import toml
import logging
from typing import Optional

import google.generativeai as genai
from openai import OpenAI

# === Load Secrets and Configure Clients ===
# Project root directory
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, ".."))

def load_openai_secrets():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(current_dir, ".."))
    secrets_path = os.path.join(root_dir, "secrets", "openAI.toml")
    return toml.load(secrets_path)

def load_googleai_secrets():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(current_dir, ".."))
    google_secrets_path = os.path.join(root_dir, "secrets", "googleAI.toml")
    return toml.load(google_secrets_path)

# # Load OpenAI credentials
# openai_secrets_path = os.path.join(root_dir, "secrets", "openAI.toml")
# openai_config = toml.load(openai_secrets_path)
# OPENAI_API_KEY = openai_config["openai"]["api_key"]
# OPENAI_MODEL = openai_config["openai"]["model"]
# openai_client = OpenAI(api_key=OPENAI_API_KEY)

# # Load Gemini credentials
# google_secrets_path = os.path.join(root_dir, "secrets", "googleAI.toml")
# google_config = toml.load(google_secrets_path)
# GEMINI_API_KEY = google_config["googleai"]["api_key"]
# GEMINI_MODEL = google_config["googleai"]["model"]
# genai.configure(api_key=GEMINI_API_KEY)


def call_llm(
        system_prompt: str,
        user_prompt: str,
        logger: Optional[logging.Logger] = None,
        temperature: float = 0.3,
        model_priority: list[str] = ["gemini", "openai"]
) -> str:
    """
    Central orchestrator for request–response LLM tasks.
    Tries a prioritized list of LLM providers (e.g. Gemini, then OpenAI).

    Args:
        system_prompt (str): System instructions for the model's behavior.
        user_prompt (str): Actual input or question for the LLM.
        logger (Optional[logging.Logger]): Optional logger instance.
        temperature (float): Sampling temperature.
        model_priority (list[str]): List of LLM providers in order of preference ("gemini", "openai").

    Returns:
        str: Model response text (stripped), or empty string if all fail.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    for vendor in model_priority:
        try:
            if vendor == "gemini":
                google_config = load_googleai_secrets()
                GEMINI_API_KEY = google_config["googleai"]["api_key"]
                GEMINI_MODEL = google_config["googleai"]["model"]
                genai.configure(api_key=GEMINI_API_KEY)

                logger.info("🔁 Trying Gemini (Google) model...")
                response = call_gemini_chat_model(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=GEMINI_MODEL,
                    temperature=temperature,
                    logger=logger,
                )
                if response:
                    logger.info("✅ Gemini returned a valid response.")
                    return response
                else:
                    logger.warning("⚠️ Gemini returned an empty response.")

            elif vendor == "openai":
                openai_config = load_openai_secrets()
                OPENAI_API_KEY = openai_config["openai"]["api_key"]
                OPENAI_MODEL = openai_config["openai"]["model"]
                openai_client = OpenAI(api_key=OPENAI_API_KEY)

                logger.info("🔁 Trying OpenAI model...")
                response = call_openai_chat_model(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=OPENAI_MODEL,
                    temperature=temperature,
                    logger=logger,
                    client=openai_client,
                )
                if response:
                    logger.info("✅ OpenAI returned a valid response.")
                    return response
                else:
                    logger.warning("⚠️ OpenAI returned an empty response.")

            else:
                logger.warning(f"❌ Unknown LLM vendor: {vendor}")

        except Exception as e:
            logger.error(f"❌ Error while calling {vendor}: {e}")
            continue

    logger.error("❌ All LLM providers failed. Returning empty string.")
    return ""

if __name__ == "__main__":
    from config_logging import get_logger

    logger = get_logger("llm_orchestrator_test", log_file="logs/llm_orchestrator_test.log", include_timestamp_in_filename=False)

    system_prompt = "You are a helpful assistant that filters football news articles for relevance."
    user_prompt = """
    Here are 3 article headlines:
    1. 'Real Madrid closes training session to prepare for El Clasico.'
    2. 'Top 10 LaLiga stadiums ranked by attendance.'
    3. 'Barcelona to rest several starters ahead of Champions League.'

    Which of these are relevant for a fantasy football manager? Return only the useful headlines.
    """

    response = call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        logger=logger
    )

    print("\n🤖 Unified LLM Response:\n")
    print(response)

