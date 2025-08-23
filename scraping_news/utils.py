import re

def extract_code_block(text: str) -> str:
    """
    Extracts a JSON-like code block from an LLM response that may be wrapped in triple backticks or triple quotes.

    Supports:
    - ```json
    - ```python
    - ``` (no lang)
    - '''python
    - ''' (no lang)

    Args:
        text (str): Raw string from LLM

    Returns:
        str: Cleaned block, or original text if no match found
    """
    # Matches ```json\n{...}\n```, ```python\n{...}```, '''python\n{...}''', etc.
    match = re.search(r"(?:```|''')\s*(?:json|python)?\s*(\{.*?\})\s*(?:```|''')", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()