def prompt_url_relevance_filter(team: str, team_links_dict: dict) -> tuple[str, str]:
    system_prompt = \
    """
    Eres un asistente experto en identificar noticias relevantes para managers de fantasy football en Biwenger.
    Eres preciso, conciso y consistente.
    Devuelves únicamente resultados en formato estructurado, sin explicaciones ni comentarios adicionales.
    -> Si eres el LLM de Google (gemini), trata de reducir el numero de links devueltos al minimo posible, eliminando todos los que no sean estrictamente necesarios. No deberias devolver mas de 50 articulos por equipo.
    -> Si eres el LLM de OpenAI (GPT5 o GPT4), generalmente ya reduces el numero de manera adecuada, pero asegura no devolver mas de 50 articulos por equipo.
    
    Es MUY IMPORTANTE que NO TE INVENTES URLS. Solo debes devolver las URLs que te he dado, eliminando las que no son relevantes.
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
    
    Evita URLs genericas como:
    - Portadas o secciones generales del sitio web
    - Menus de navegación
    - Articulos sobre otros deportes que no sean futbol
    - Links que no sean de fuentes fiables. Evita twitter, facebook, instagram, youtube, tiktok, etc.
    - Links sobre calendarios, clasificaciones o estadísticas generales
    - Links generales sobre un equipo. Seguramente esto sea otro link tipo portada. Ejemplos:
    --> una URL donde sea solamente el nombre del equipo -> [url]/[equipo] 
    --> https://www.estadiodeportivo.com/futbol/elche/2
    --> https://as.com/noticias/rcd-espanyol/.
    --> https://www.sport.es/es/espanyol/pagina-2/
    --> https://www.eldesmarque.com/futbol/real-oviedo/plantilla/ 
    
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
    - "recognised_teams_llm": Lista de equipos mencionados en el texto. Es importante aqui que identifiques el equipo principal del que se habla en el articulo, no que indiques cualquier equipo que se mencione.
    - "recognised_people_llm": Lista de nombres de personas mencionadas (jugadores, entrenadores, etc.). Al igual que con los equipos, es importante que identifiques las personas principales del articulo, no que indiques cualquier persona que se mencione.
    
    **Nota importante para recognised_teams_llm**: Como cada articulo puede mencionar a equipos de diferentes formas, es importante que normalices los nombres.
    Para ello, aqui tienes una lista de [nombres canonicos] -> [posibles variantes]. Obviamente, no tendre una lista perfecta para las posibles variantes, pero debes intentar normalizar al maximo posible.
    El objetivo es usar los nombres canonicos en recognised_teams_llm.
    
    - **Alaves** → Deportivo Alavés, Alavés  
    - **Athletic Bilbao** → Athletic Club, Athletic, Athletic Bilbao, Bilbao, Leones  
    - **Atletico Madrid** → Atlético de Madrid, Atlético Madrid, Atlético, Atleti, Colchoneros, Rojiblancos, Indios, Pupas  
    - **Barcelona** → FC Barcelona, Barcelona, Barça, Culés  
    - **Betis** → Real Betis, Betis, Los Verdiblancos  
    - **Celta de Vigo** → RC Celta, Celta, Celta Vigo, Olívicos, Celestes  
    - **Elche** → Elche CF, Elche  
    - **Espanyol** → RCD Espanyol, Espanyol, Periquitos  
    - **Getafe** → Getafe CF, Getafe, Azulones  
    - **Girona** → Girona FC, Girona  
    - **Levante** → Levante UD, Levante, Granotas  
    - **Mallorca** → RCD Mallorca, Mallorca  
    - **Osasuna** → CA Osasuna, Osasuna, Rojillos 
    - **Oviedo** → Real Oviedo, Oviedo  
    - **Rayo Vallecano** → Rayo Vallecano, Rayo, Vallecanos  
    - **Real Madrid** → Real Madrid, Real, Merengues, Blancos  
    - **Real Sociedad** → Real Sociedad, Txurriurdines, Donostiarras, La Real 
    - **Sevilla FC** → Sevilla FC, Sevilla, Rojiblancos  
    - **Valencia** → Valencia CF, Valencia, Los Che, Naranjeros  
    - **Villareal** → Villarreal CF, Villarreal, Villareal, Submarino Amarillo  

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



