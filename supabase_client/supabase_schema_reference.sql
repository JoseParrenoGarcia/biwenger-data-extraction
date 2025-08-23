-- Enable UUID generation (required for gen_random_uuid())
create extension if not exists "pgcrypto";

-- Create logical schemas (optional, but useful for staging vs production separation)
create schema if not exists staging;
create schema if not exists prod;

-- Define the table for storing filtered article URLs (staging version)
create table if not exists public.article_urls (
    id uuid primary key default gen_random_uuid(),   -- Unique identifier for each row, generated automatically
    team text not null,                              -- Name of the football team (e.g., "Valencia", "Real Madrid")
    source text not null,                            -- URL of the source (e.g., the landing page that was scraped)
    url text not null,                               -- Direct link to the actual article
    created_at timestamptz default now(),            -- Timestamp of insertion (auto-filled with current UTC time)
    unique (team, url)                               -- Prevents duplicate entries for the same team + article URL
);

-- Define the table for storing full article contents and LLM enrichment
create table if not exists public.article_contents (
    id uuid primary key default gen_random_uuid(),   -- Unique identifier for each row (auto-generated)

    article_id uuid not null references public.article_urls(id) on delete cascade,  -- FK to original article_urls table
    url_text text not null,                              -- Redundant copy of the article URL for convenience/debugging

    published_date date,                                 -- Date the article was published (if extractable)
    scrape_timestamp timestamptz default now(),          -- Timestamp when content was scraped (auto-filled)

    title text,                                          -- Article title, extracted from the HTML
    raw_text text,                                       -- Full article body content (raw)

    summary_llm text,                                    -- Optional LLM-generated summary
    tags_llm text[],                                     -- Tags inferred by LLM (e.g., ['cronica_partido', 'lesiones_sanciones'])
    recognised_teams_llm text[],                         -- Teams mentioned in the article (LLM-extracted)
    recognised_people_llm text[],                        -- Named players/coaches/etc. mentioned (LLM-extracted)

    -- Add any further enrichment fields below as needed in the future
    unique (article_id)                                  -- Ensures one-to-one relationship with article_urls
);
