-- Enable UUID generation (required for gen_random_uuid())
create extension if not exists "pgcrypto";

-- Create logical schemas (optional, but useful for staging vs production separation)
create schema if not exists staging;
create schema if not exists prod;

-- Define the table for storing filtered article URLs (staging version)
create table if not exists staging.article_urls (
    id uuid primary key default gen_random_uuid(),   -- Unique identifier for each row, generated automatically
    team text not null,                              -- Name of the football team (e.g., "Valencia", "Real Madrid")
    source text not null,                            -- URL of the source (e.g., the landing page that was scraped)
    url text not null,                               -- Direct link to the actual article
    created_at timestamptz default now(),            -- Timestamp of insertion (auto-filled with current UTC time)
    unique (team, url)                               -- Prevents duplicate entries for the same team + article URL
);

-- Optional: define production table with same schema
create table if not exists prod.article_urls (
    id uuid primary key default gen_random_uuid(),   -- Same as staging, but for production environment
    team text not null,
    source text not null,
    url text not null,
    created_at timestamptz default now(),
    unique (team, url)
);
