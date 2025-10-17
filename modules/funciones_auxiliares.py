from .utils import check_handicap_cover, parse_ah_to_number_of

def _calcular_estadisticas_contra_rival(partidos, equipo_principal, rival_nombre):
    """
    Calcula estadísticas de enfrentamientos directos contra un rival específico.
    """
    victorias = empates = derrotas = 0
    for p in partidos:
        if p['rival'] == rival_nombre:
            if p['margen'] > 0:
                victorias += 1
            elif p['margen'] < 0:
                derrotas += 1
            else:
                empates += 1
    return {"victorias": victorias, "empates": empates, "derrotas": derrotas}

def _analizar_over_under(partidos, umbral=2.5):
    """
    Analiza el número de partidos que terminaron por encima o por debajo de un umbral de goles.
    """
    overs = unders = 0
    for p in partidos:
        try:
            goles = sum(map(int, re.split(r'[-:]', p['resultado'].split(' ')[1])))
            if goles > umbral:
                overs += 1
            elif goles < umbral:
                unders += 1
        except (ValueError, IndexError):
            continue
    return {"overs": overs, "unders": unders}

def _analizar_ah_cubierto(partidos, equipo_principal):
    """
    Analiza cuántas veces un equipo ha cubierto el hándicap en sus últimos partidos.
    """
    cubiertos = no_cubiertos = push = 0
    for p in partidos:
        if p.get('handicap') and p.get('resultado'):
            handicap_num = parse_ah_to_number_of(p['handicap'])
            if handicap_num is None:
                continue

            # Determinar si el equipo principal era local o visitante en el partido analizado
            equipo_es_local = equipo_principal.lower() in p['resultado'].split(' ')[0].lower()

            # Ajustar el hándicap según la perspectiva del equipo principal
            if not equipo_es_local:
                handicap_num = -handicap_num

            # Calcular margen de victoria desde la perspectiva del equipo principal
            try:
                goles = list(map(int, re.split(r'[-:]', p['resultado'].split(' ')[1])))
                margen = goles[0] - goles[1] if equipo_es_local else goles[1] - goles[0]
            except (ValueError, IndexError):
                continue

            # Comprobar si se cubrió el hándicap
            if margen + handicap_num > 0.1:
                cubiertos += 1
            elif margen + handicap_num < -0.1:
                no_cubiertos += 1
            else:
                push += 1
                
    return {"cubiertos": cubiertos, "no_cubiertos": no_cubiertos, "push": push}

def _analizar_desempeno_casa_fuera(partidos, es_local):
    """
    Analiza el desempeño de un equipo en casa o fuera, devolviendo V-E-D.
    """
    victorias = empates = derrotas = 0
    for p in partidos:
        try:
            goles = list(map(int, re.split(r'[-:]', p['resultado'].split(' ')[1])))
            margen = goles[0] - goles[1] if es_local else goles[1] - goles[0]
            if margen > 0:
                victorias += 1
            elif margen < 0:
                derrotas += 1
            else:
                empates += 1
        except (ValueError, IndexError):
            continue
    return f"{victorias}-{empates}-{derrotas}"

def _contar_victorias_h2h(h2h_data, home_team_name, away_team_name):
    home_wins = 0
    away_wins = 0
    draws = 0
    # Implementa la lógica para contar victorias, empates y derrotas
    return home_wins, away_wins, draws

def _analizar_over_under_h2h(h2h_data, umbral=2.5):
    overs = 0
    unders = 0
    # Implementa la lógica para contar overs y unders en H2H
    return overs, unders

def _contar_over_h2h(h2h_data, umbral=2.5):
    overs = 0
    # Implementa la lógica para contar overs en H2H
    return overs

def _contar_victorias_h2h_general(h2h_data, team_name):
    wins = 0
    # Implementa la lógica para contar victorias de un equipo en H2H general
    return wins
