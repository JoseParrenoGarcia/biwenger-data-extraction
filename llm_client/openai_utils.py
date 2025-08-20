import logging
import tiktoken
from typing import Optional

def truncate_user_prompt(user_prompt: str, model: str, max_tokens: int) -> str:
    enc = tiktoken.encoding_for_model(model)
    user_tokens = enc.encode(user_prompt)
    if len(user_tokens) > max_tokens:
        user_tokens = user_tokens[:max_tokens]
    return enc.decode(user_tokens)

def call_openai_chat_model(
    system_prompt: str,
    user_prompt: str,
    model: str = "gpt-4o-mini",
    max_tokens: int = 128_000,
    temperature: float = 0.3,
    logger: Optional[logging.Logger] = None,
    client=None  # Injected OpenAI client
) -> str:
    """
    Calls the OpenAI Chat Completion API with a system and user prompt,
    handling token truncation to stay within model limits.

    Args:
        system_prompt (str): Instructions for the assistant's behavior.
        user_prompt (str): The user's input or question.
        model (str): OpenAI model to use
        max_tokens (int): Token budget
        temperature (float): Sampling temperature (default: 0.3).
        logger (Optional[logging.Logger]): Logger to use. Defaults to print().
        client: Optional OpenAI client instance (recommended to inject for testability).

    Returns:
        str: The model's plain text response, or an empty string on error.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    try:
        # Token encoding for selected model
        enc = tiktoken.encoding_for_model(model)

        # Estimate tokens used by system prompt
        system_tokens = enc.encode(system_prompt)
        system_token_count = len(system_tokens)

        buffer_tokens = 2000  # For role formatting, assistant response, etc.
        available_user_tokens = max_tokens - system_token_count - buffer_tokens

        if available_user_tokens < 100:
            logger.warning("Not enough room left for user prompt after system prompt.")
            return ""

        # Truncate user prompt if necessary
        truncated_user_prompt = truncate_user_prompt(user_prompt, model, available_user_tokens)

        # Call OpenAI Chat Completion API
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": truncated_user_prompt}
            ],
            temperature=temperature
        )

        # Extract and return the response
        if response.choices and response.choices[0].message:
            return response.choices[0].message.content.strip()
        else:
            logger.warning("OpenAI response had no choices.")
            return ""

    except Exception as e:
        logger.error(f"❌ OpenAI API call failed: {e}")
        return ""


if __name__ == "__main__":
    from openai import OpenAI
    import os
    import toml

    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(current_dir, ".."))
    secrets_path = os.path.join(root_dir, "secrets", "openAI.toml")
    config = toml.load(secrets_path)
    OPENAI_API_KEY = config["openai"]["api_key"]
    OPENAI_MODEL = config["openai"]["model"]
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

    # Example prompts
    system_prompt = "You are a helpful assistant that filters football news articles for relevance."
    user_prompt = """
    Here are 3 article headlines:
    1. 'Real Madrid closes training session to prepare for El Clasico.'
    2. 'Top 10 LaLiga stadiums ranked by attendance.'
    3. 'Barcelona to rest several starters ahead of Champions League.'

    Which of these are relevant for a fantasy football manager? Return only the useful headlines.
    """

    result = call_openai_chat_model(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        client=openai_client
    )

    print("\n🧠 LLM Response:")
    print(result)
