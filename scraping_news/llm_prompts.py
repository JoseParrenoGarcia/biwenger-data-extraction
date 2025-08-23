def prompt_url_relevance_filter(team: str, team_links_dict: dict) -> tuple[str, str]:
    system_prompt = \
    """
    Eres un asistente experto en identificar noticias relevantes para managers de fantasy football en Biwenger.
    Eres preciso, conciso y consistente.
    Devuelves únicamente resultados en formato estructurado, sin explicaciones ni comentarios adicionales.
    """

    user_prompt = \
    f"""
    A continuación encontrarás un diccionario de URLs de artículos agrupados por fuente para el equipo {team}.
    El formato del diccionario es el siguiente:
    The dictionary format is as follows:
    {{"team_name": [
        "source_url_1": [
            "link_1",
            "link_2",
            ...
        ],
        "source_url_2": [
            ...
        ]
      ]
    }}
    
    Debes analizar cada enlace y **eliminar todos aquellos que no sean relevantes para managers de Biwenger**.

    Estamos buscando artículos que ofrezcan información sobre:
    - Lesiones de jugadores
    - Sanciones
    - Crónicas de partidos anteriores
    - Previas de partidos próximos
    - Posibles alineaciones para los próximos encuentros
    - Nuevos fichajes o salidas confirmadas
    - Ruedas de prensa del entrenador que afecten a la plantilla
    - Noticias o articulos sobre jugadores
    - Riesgos de rotación o cambios significativos en los minutos de juego
    
    Una vez identificados, debes devolver **la misma estructura del diccionario en Python**, pero con los enlaces irrelevantes eliminados.
    No añadas explicaciones ni resúmenes. No modifiques el formato.
    
    Aquí tienes un ejemplo de entrada y salida para que entiendas el formato esperado:
    ### Entrada de ejemplo:
    {{
        "https://www.superdeporte.es/valencia-cf/": [
            "https://www.superdeporte.es/valencia-cf/2025/08/21/yarek-gasiorowski-pre-lista-seleccion-absoluta-120822174.html",
            "https://www.superdeporte.es/ocio/gastronomia/",
            "https://www.superdeporte.es/valencia-cf/2025/08/20/yangel-herrera-clave-llegada-sadiq-valencia-cf-120801557.html"
        ],
        "https://plazadeportiva.valenciaplaza.com/valenciacf/": [
            "https://plazadeportiva.valenciaplaza.com/plazadeportiva/valenciacf/ron-gourlay-hay-muchas-vocesen-cuanto-a-la-posibilidad-de-incorporar-un-delantero-pero-veremos-como-va",
            "https://plazadeportiva.valenciaplaza.com/aviso-legal/"
        ]
    }}
    
    ### ### Salida de ejemplo:
    {{
        "https://www.superdeporte.es/valencia-cf/": [
            "https://www.superdeporte.es/valencia-cf/2025/08/21/yarek-gasiorowski-pre-lista-seleccion-absoluta-120822174.html",
            "https://www.superdeporte.es/valencia-cf/2025/08/20/yangel-herrera-clave-llegada-sadiq-valencia-cf-120801557.html"
        ],
        "https://plazadeportiva.valenciaplaza.com/valenciacf/": [
            "https://plazadeportiva.valenciaplaza.com/plazadeportiva/valenciacf/ron-gourlay-hay-muchas-vocesen-cuanto-a-la-posibilidad-de-incorporar-un-delantero-pero-veremos-como-va"
        ]
    }}
    
    Ahora aplica la misma lógica de filtrado a los siguientes enlaces para el equipo "{team}":
    {team_links_dict}
    """
    return system_prompt, user_prompt


def prompt_article_summary_and_tags(article_text: str, article_title: str = "") -> tuple[str, str]:
    system_prompt = \
        """
        Eres un asistente experto en análisis de artículos deportivos para managers de fantasy football en Biwenger.
        Tu tarea es resumir, clasificar y extraer información estructurada de un artículo.
    
        Eres preciso, conciso y coherente. Devuelves siempre una estructura JSON válida y no incluyes explicaciones ni texto adicional fuera del bloque JSON.
        """

    user_prompt = f"""
    A continuación tienes un artículo de prensa deportiva.
    Tu trabajo consiste en devolver un bloque JSON con la siguiente información:

    - "summary": Un resumen breve del contenido del artículo, en un parrafo de maximo 5 frases.
    - "tags_llm": Una lista de etiquetas relevantes del siguiente conjunto:
        ["cronica_partido", "previa_siguiente_partido", "lesiones_sanciones", "fichajes", "renovaciones", "rueda_prensa"]
    - "recognised_teams_llm": Lista de equipos mencionados en el texto.
    - "recognised_people_llm": Lista de nombres de personas mencionadas (jugadores, entrenadores, etc.).
    
    Contexto adicional:
    - Cada articulo se ha hecho un scraping con beautifulsoup4 y puede contener texto no relevante (menus, publicidad, etc.). Debes centrarte en el contenido principal.

    El resultado debe tener el siguiente formato:
    {{
        "summary": "...",
        "tags_llm": ["...", "..."],
        "recognised_teams_llm": ["...", "..."],
        "recognised_people_llm": ["...", "..."]
    }}

    No incluyas explicaciones ni comentarios fuera del bloque JSON.

    ### Título del artículo:
    {article_title}

    ### Contenido del artículo:
    {article_text}
    """

    return system_prompt.strip(), user_prompt.strip()



