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

def prompt_transfer_digest(team: str, articles_compact: list[dict]) -> tuple[str, str]:
    system_prompt = dedent("""
        Eres un analista de noticias experto en fútbol para Biwenger.
        Tu objetivo es generar un RESUMEN EN ESPAÑOL, en Markdown, sobre el estado de fichajes del equipo indicado.
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

        A continuación tienes artículos prefiltrados relacionados con **fichajes** del {team}.
        Léelos y construye un **informe de mercado** en **Markdown** orientado a Biwenger.
        Recuerda: NO inventes información; si hay duda, indícalo.

        ### Artículos de contexto
        {articles_md}

        ### Instrucciones de salida (DEVUELVE SOLO MARKDOWN):

        # Mercado de fichajes — {team}

        ## Resumen ejecutivo
        - Bullets con la foto global: altas/casi cerradas, salidas probables, prioridades del club y riesgos.

        ## Altas (entradas)
        - Tabla con los movimientos hacia el {team}.
        | Jugador | Procedencia | Estado operación | Tipo | Coste/condiciones | Rol esperado | Impacto Biwenger | ETA |
        |---|---|---|---|---|---|---|---|
        | Nombre Apellido | Club origen / “Libre” | **Oficial** / **Avanzada** / **Negociación** / **Rumor** | Traspaso / Cesión (con/sin compra) | (€, cláusulas si se mencionan) | **Titular** / **Rotación** / **Suplente** | ↑ / ↔ / ↓ + breve motivo | Fecha estimada / “Desconocido” |

        ## Bajas (salidas)
        - Tabla con los movimientos de salida del {team}.
        | Jugador | Destino | Estado operación | Tipo | Ingreso/condiciones | Situación en destino | Impacto Biwenger | Nota liga |
        |---|---|---|---|---|---|---|---|
        | Nombre Apellido | Club destino | **Oficial** / **Avanzada** / **Negociación** / **Rumor** | Traspaso / Cesión | (€, variables) | **Titular** / **Rotación** / **Suplente** (si se infiere) | ↑ / ↔ / ↓ + breve motivo | “Sigue en LaLiga” / “Fuera de LaLiga” |

        - **Nota liga 1** es importante: si el jugador sale **fuera de LaLiga**, suele implicar una caída fuerte de valor en Biwenger.
        - **Nota liga 2** es importante: si el jugador va a tener un rol importante nada mas llegar o va a ser suplente tambien tiene implicaciones de valor.

        ## Operaciones en seguimiento (si aplica)
        - Lista breve de objetivos/rumores relevantes con su estado actual y cuello de botella (p. ej., negociación por fee, ficha, medical, etc.).

        ## Observaciones para Biwenger
        - 3–6 bullets prácticos: subidas/bajadas de valor esperadas, tapados, riesgos de minutos, cambios de tiradores (penaltis/faltas), efecto en posiciones colindantes.

        ## Fuentes
        - Enumera artículos usados (1 línea por fuente): **fecha** – *título (si disponible)* – enlace.

        Definiciones de “Estado operación”:
        - **Oficial**: anuncio oficial del club o registro en organismo oficial.
        - **Avanzada**: acuerdo muy cercano (p. ej. “principio de acuerdo”, “a falta de firma/medical”).
        - **Negociación**: conversaciones activas pero sin acuerdo.
        - **Rumor**: especulación sin confirmaciones sólidas.

        (Recuerda: Solo Markdown en la salida, sin JSON ni explicaciones adicionales.)
        """)

    return system_prompt, user_prompt


def ETL_get_transfer_news():
    logger = get_logger("ETL_get_transfer_news", log_file="logs/ETL_get_transfer_news.log")
    logger.info("🚀 Starting ETL pipeline for ETL_get_transfer_news...")

    supabase = get_supabase_client()
    table_name = "article_for_streamlit"

    # if not check_if_table_exists(supabase, table_name):
    #     logger.error(f"❌ Table '{table_name}' does not exist in Supabase.")
    # else:
    #     # Delete everything first (truncate semantics)
    #     supabase.table(table_name).delete().neq("id", 0).execute()
    #     logger.info(f"🗑️ Cleared existing rows from '{table_name}'")

    logger.info("=" * 60)
    logger.info("READING SUPABASE TABLE AND EXTRACTING UNIQUE TEAMS")
    logger.info("=" * 60)

    teams = sorted(list(get_unique_teams("article_urls", logger)))
    transfer_tags = MODULE_PROFILES["transfers"]["tags"]
    transfer_days = MODULE_PROFILES["transfers"]["days"]

    logger.info(f"Processing {len(teams)} teams: {teams}")
    for team in teams:
        logger.info("=" * 60)
        logger.info(f"HANDLING TRANSFERS FOR TEAM: {team}")
        logger.info("=" * 60)

        # Pull once for the cutoff window
        logger.info(f"Extract all articles from the last {transfer_days} days...")
        all_articles_df = get_recent_articles("article_contents", days=transfer_days, logger=logger)
        if all_articles_df.empty:
            logger.info("No recent articles. Exiting.")
            return

        logger.info(f"Filtering articles for team: {team}")
        team_articles_df = filter_articles_by_team(all_articles_df, team)
        if team_articles_df.empty:
            logger.info(f"No articles for team {team}. Skipping.")
            continue

        logger.info(f"Filtering articles with injury tags: {transfer_tags}")
        tag_df = filter_articles_by_tag(
            team_articles_df,
            tags=transfer_tags,
            tags_col="tags_llm",  # change if your column name differs
            match="any",
            case_insensitive=True,
        )
        logger.info(f"Found {len(tag_df)} transfer-tagged articles for {team}")

        logger.info("-" * 30)
        logger.info("FORMATTING LLM OUTPUT FOR TRANSFER TABLE")
        logger.info("-" * 30)
        logger.info("Transforming the dataframe to dictionary format for LLM ingestion")
        articles_payload = build_articles_compact_payload(
            tag_df, logger=logger, max_items=60, max_summary_chars=35_000
        )

        if not articles_payload:
            logger.info(f"No injury articles for {team}. Skipping.")
            continue

        logger.info("Building system and user prompts for LLM")
        system_prompt, user_prompt = prompt_transfer_digest(team, articles_payload)

        logger.info("Calling LLM orchestrator")
        md = call_llm(system_prompt, user_prompt, logger=logger)

        records_to_write_to_supabase = [
            {
                "team": team,
                "tag": transfer_tags,
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

    ETL_get_transfer_news()