# biwenger-data-extraction

Biwenger-only data extraction repository focused on scraping fantasy football data from the Biwenger app and writing validated player/team outputs to Supabase.

The repository no longer performs football news scraping, article extraction, structured news generation, or LLM-based article enrichment.

Runtime logs are written under `logs/` and are intentionally ignored by Git.

## Local Setup

Install Python dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Install Playwright browsers if they are not already available:

```bash
python3 -m playwright install chromium
```

Create local secrets from the safe templates:

```bash
cp secrets/biwenger.example.toml secrets/biwenger.toml
cp secrets/supabase.example.toml secrets/supabase.toml
```

Fill in `secrets/biwenger.toml` with both Biwenger credential profiles:

- `[biwenger]` is used for current-team extraction.
- `[biwenger_player_scraper]` is used for high-volume player scraping.

Fill in `secrets/supabase.toml` with the Supabase project URL and anon key.

The `secrets/` directory remains ignored by Git except for `*.example.toml`
templates. Do not commit real credentials. OpenAI, Gemini, and local Ollama
secrets are not required for the current Biwenger-only pipeline.
