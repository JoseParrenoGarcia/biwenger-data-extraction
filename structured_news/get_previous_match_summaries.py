from config_logging import get_logger
from supabase_client.connection import get_supabase_client
from supabase_client.utils import check_if_table_exists, insert_rows_into_table
from structured_news.utils import (
    get_unique_teams,
    get_recent_articles,
    filter_articles_by_team,
    filter_articles_by_tag,
    build_articles_compact_payload,
    MODULE_PROFILES
)
import pandas as pd
from textwrap import dedent
from llm_client.llm_orchestrator import call_llm

def prompt_previous_match_digest(team: str, articles_compact: list[dict]) -> tuple[str, str]:
    system_prompt = dedent("""
        Eres un analista de noticias experto en fútbol para Biwenger.
        Tu objetivo es generar un RESUMEN EN ESPAÑOL, en Markdown, sobre la **alineación probable del próximo partido** del equipo indicado.
        Debe ser útil para managers de fantasy (Biwenger), con foco en disponibilidad, plazos de regreso y riesgos de rotación.

        Reglas IMPORTANTES:
        - NO inventes datos. Si algo no está claro, pon “Desconocido” o “Información no confirmada”.
        - Escribe SIEMPRE en español.
        - Devuelve SOLO Markdown (sin ningún otro formato).
        - Mantén trazabilidad: incluye al final una sección **Fuentes** con viñetas y enlaces.
        - Normaliza nombres de jugadores (acentos/camel case correctos).
        - Si hay contradicciones entre artículos, menciónalas y señala el caso más fiable
          (prima oficialidad del club > medios locales reputados > agregadores).
        - No repitas la misma información: deduplica por jugador.
        - Formato de fechas preferido: DD/MM/YYYY.
        - No superes ~300–400 palabras salvo que haya muchas incidencias relevantes.
        - No uses tono publicitario; sé preciso, conciso y neutral.
        """)

    # Build a compact, readable block for the LLM from RAW TEXT snippets
    lines = []
    for a in articles_compact:
        title = (a.get("title") or "").strip()
        snippet = (a.get("summary") or a.get("content") or a.get("raw_text") or "").strip()
        date = (a.get("published_at") or "").strip()
        url = (a.get("url") or "").strip()
        lines.append(f"- [{date}] {title}\n  Extracto: {snippet}\n  Fuente: {url}")
    articles_md = "\n".join(lines) if lines else "- (sin artículos de entrada)"

    user_prompt = dedent(f"""
        Equipo: **{team}**

        A continuación tienes artículos prefiltrados relacionados con **crónicas de partidos previos**.
        Léelos y construye un informe en **Markdown** centrado en actuaciones individuales relevantes para Biwenger.
        Recuerda: NO inventes información; si hay duda, indícalo.

        ### Artículos de contexto
        {articles_md}

        ### Instrucciones de salida (DEVUELVE SOLO MARKDOWN):

        # Crónicas recientes — {team}

        > Estructura: crea una **sección por partido** (2–4 partidos si hay material). 
        Para cada partido:
        - Encabezado con **fecha (DD/MM/AAAA)**, **competición** (si se menciona), **rival** y **resultado final**.
        - Tabla de actuaciones individuales (una fila por jugador).

        ## Partido: {team} vs Rival (DD/MM/AAAA) — Competición — Resultado: X–Y
        - Breve contexto de 1–2 frases: lesiones/sanciones que afectaron, cambios relevantes, expulsiones si las hubo.

        | Jugador | Titular/Suplente | Minutos | Sustitución | G/A/Tarj | Paradas (si portero) | Nota (si aparece) | Descripción breve |
        |---|---|---:|---|---|---|---|---|
        | Nombre Apellido | Titular / Suplente | 73' | Sale 73' / Entra 17' / N/A | G:1 A:0 T:R (R/A) | 4 paradas / N/A | 6.8 / Desconocido | 2 remates, activo en banda; clave en presión |
        | Nombre Apellido | Titular | 90' | N/A | G:0 A:1 T:N/A | N/A | Desconocido | Buen pie en salida, asistió en el 1–0 |
        | Nombre Apellido | Suplente | 28' | Entra 62' | G:0 A:0 T:A | N/A | Desconocido | Entró para cerrar el partido; trabajo defensivo |

        Notas:
        - **Titular/Suplente** debe indicar condición inicial.
        - **Minutos** en formato `90'` o rango claro si aparece (ej. `62'`).
        - **Sustitución**: "Sale 73'", "Entra 62'", o "N/A".
        - **G/A/Tarj**: Goles (G), Asistencias (A), Tarjetas (T:R roja / T:A amarilla / T:N/A si no aplica).
        - **Paradas**: solo porteros; si no aplica, "N/A".
        - **Nota**: rating del medio si lo menciona, o "Desconocido".
        - **Descripción breve**: 8–20 palabras, concreta, sin táctica profunda (enfocada en rendimiento individual).

        ## Observaciones para Biwenger
        -> 3–6 bullets con implicaciones prácticas derivadas de estas actuaciones:
          - jugadores que se consolidan como titulares
          - suplentes con minutos crecientes
          - tiradores de penaltis/faltas/córners (si se menciona)
          - riesgos de rotación detectados

        ## Fuentes
        - Enumera artículos usados (1 línea por fuente): **fecha** – *título (si disponible)* – enlace.

        (Recuerda: Solo Markdown en la salida, sin JSON ni explicaciones adicionales.)
        """)

    return system_prompt, user_prompt


def ETL_get_previous_match_news():
    logger = get_logger("ETL_get_previous_match_news", log_file="logs/ETL_get_previous_match_news.log")
    logger.info("🚀 Starting ETL pipeline for ETL_get_previous_match_news...")

    supabase = get_supabase_client()
    table_name = "article_for_streamlit"

    logger.info("=" * 60)
    logger.info("READING SUPABASE TABLE AND EXTRACTING UNIQUE TEAMS")
    logger.info("=" * 60)

    teams = sorted(list(get_unique_teams("article_urls", logger)))
    previous_match_tags = MODULE_PROFILES["cronica_partido"]["tags"]
    previous_match_days = MODULE_PROFILES["cronica_partido"]["days"]

    logger.info(f"Processing {len(teams)} teams: {teams}")
    for team in teams:
        logger.info("=" * 60)
        logger.info(f"HANDLING PREVIOUS MATCHES FOR TEAM: {team}")
        logger.info("=" * 60)

        # Pull once for the cutoff window
        logger.info(f"Extract all articles from the last {previous_match_days} days...")
        all_articles_df = get_recent_articles("article_contents", days=previous_match_days, logger=logger)
        if all_articles_df.empty:
            logger.info("No recent articles. Exiting.")
            return

        logger.info(f"Filtering articles for team: {team}")
        team_articles_df = filter_articles_by_team(all_articles_df, team)
        if team_articles_df.empty:
            logger.info(f"No articles for team {team}. Skipping.")
            continue

        logger.info(f"Filtering articles with injury tags: {previous_match_tags}")
        tag_df = filter_articles_by_tag(
            team_articles_df,
            tags=previous_match_tags,
            tags_col="tags_llm",  # change if your column name differs
            match="any",
            case_insensitive=True,
        )
        logger.info(f"Found {len(tag_df)} transfer-tagged articles for {team}")

        logger.info("-" * 30)
        logger.info("FORMATTING LLM OUTPUT FOR PREVIOUS MATCHES TABLE")
        logger.info("-" * 30)
        logger.info("Transforming the dataframe to dictionary format for LLM ingestion")
        articles_payload = build_articles_compact_payload(
            tag_df, logger=logger, max_items=60, max_summary_chars=35_000
        )

        if not articles_payload:
            logger.info(f"No injury articles for {team}. Skipping.")
            continue

        logger.info("Building system and user prompts for LLM")
        system_prompt, user_prompt = prompt_previous_match_digest(team, articles_payload)

        logger.info("Calling LLM orchestrator")
        md = call_llm(system_prompt, user_prompt, logger=logger)

        records_to_write_to_supabase = [
            {
                "team": team,
                "tag": previous_match_tags,
                "markdown_document": md
            }
        ]

        logger.info("-" * 30)
        logger.info("WRITING RESULTS BACK TO SUPABASE")
        logger.info("-" * 30)
        if not check_if_table_exists(supabase, table_name):
            logger.error(f"❌ Table '{table_name}' does not exist in Supabase.")
        else:
            if records_to_write_to_supabase:
                # Insert fresh rows
                insert_rows_into_table(supabase, table_name=table_name, rows=records_to_write_to_supabase)
                logger.info(f"✅ Inserted {len(records_to_write_to_supabase)} rows into '{table_name}'")
            else:
                logger.info("⏩ No new rows to insert.")


if __name__ == "__main__":
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', None)

    ETL_get_previous_match_news()