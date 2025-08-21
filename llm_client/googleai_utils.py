import logging
from typing import Optional
import google.generativeai as genai


def call_gemini_chat_model(
    system_prompt: str,
    user_prompt: str,
    model: str = "gemini-2.5-flash",
    temperature: float = 0.3,
    logger: Optional[logging.Logger] = None,
) -> str:
    """
    Calls the Gemini (Google Generative AI) chat model using the Generative AI SDK.

    Args:
        system_prompt (str): Optional background instructions (not officially supported like OpenAI).
        user_prompt (str): User-facing prompt.
        model (str): Gemini model to use (default: "gemini-pro").
        temperature (float): Controls randomness.
        logger (Optional[logging.Logger]): Optional logger instance.

    Returns:
        str: Model's plain text response, or empty string on failure.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    try:
        # Gemini doesn’t support full chat history natively — just prepend system prompt
        prompt = f"{system_prompt.strip()}\n\n{user_prompt.strip()}"

        model_obj = genai.GenerativeModel(model)
        response = model_obj.generate_content(prompt, generation_config={"temperature": temperature})

        if hasattr(response, "text"):
            return response.text.strip()
        else:
            logger.warning("Gemini response had no 'text' attribute.")
            return ""

    except Exception as e:
        logger.error(f"❌ Gemini API call failed: {e}")
        return ""

if __name__ == "__main__":
    import os
    import toml

    # Load secrets from TOML file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(current_dir, ".."))
    secrets_path = os.path.join(root_dir, "secrets", "googleAI.toml")
    config = toml.load(secrets_path)
    GEMINI_API_KEY = config["googleai"]["api_key"]
    GEMINI_MODEL = config["googleai"]["model"]

    # Configure the Gemini client
    genai.configure(api_key=GEMINI_API_KEY)

    # Example prompts
    system_prompt = "You are a helpful assistant that filters football news articles for relevance."
    user_prompt = """
    Here are 3 article headlines:
    1. 'Real Madrid closes training session to prepare for El Clasico.'
    2. 'Top 10 LaLiga stadiums ranked by attendance.'
    3. 'Barcelona to rest several starters ahead of Champions League.'

    Which of these are relevant for a fantasy football manager? Return only the useful headlines.
    """

    # Call Gemini
    result = call_gemini_chat_model(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=GEMINI_MODEL,
    )

    print("\n🤖 Gemini response:\n")
    print(result)