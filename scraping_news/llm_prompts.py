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


