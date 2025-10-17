from bs4 import BeautifulSoup
import re

def analizar_rivales_comunes(soup, home_team_name, away_team_name):
    """
    Encuentra rivales comunes en los últimos partidos y compara los resultados.
    """
    home_matches = _extraer_partidos(soup, "table_v1", home_team_name)
    away_matches = _extraer_partidos(soup, "table_v2", away_team_name)

    rivales_home = {match['rival']: match for match in home_matches}
    rivales_away = {match['rival']: match for match in away_matches}

    rivales_comunes_nombres = set(rivales_home.keys()) & set(rivales_away.keys())

    analisis = []
    for rival in rivales_comunes_nombres:
        match_home = rivales_home[rival]
        match_away = rivales_away[rival]

        if match_home['margen'] > match_away['margen']:
            conclusion = f"<strong style='color: green;'>{home_team_name} tuvo un mejor rendimiento</strong> contra {rival}.
        elif match_home['margen'] < match_away['margen']:
            conclusion = f"<strong style='color: red;'>{away_team_name} tuvo un mejor rendimiento</strong> contra {rival}.
        else:
            conclusion = f"Ambos equipos tuvieron un rendimiento similar contra {rival}."
        
        analisis.append({
            "rival": rival,
            "resultado_home": match_home['resultado'],
            "resultado_away": match_away['resultado'],
            "conclusion": conclusion
        })

    return analisis

def _extraer_partidos(soup, table_id, team_name):
    tabla = soup.find("table", id=table_id)
    if not tabla:
        return []

    partidos = []
    for r in tabla.find_all("tr", id=re.compile(rf"tr{table_id[-1]}_\d+"), limit=8):
        celdas = r.find_all("td")
        if len(celdas) < 5:
            continue

        try:
            home_team_in_match = celdas[2].get_text(strip=True)
            away_team_in_match = celdas[4].get_text(strip=True)
            resultado_raw = celdas[3].get_text(strip=True)
            goles_local, goles_visitante = map(int, re.split(r'[-:]', resultado_raw))

            if team_name.lower() in home_team_in_match.lower():
                rival = away_team_in_match
                margen = goles_local - goles_visitante
            else:
                rival = home_team_in_match
                margen = goles_visitante - goles_local
            
            partidos.append({
                "rival": rival,
                "resultado": f"{home_team_in_match} {goles_local}-{goles_visitante} {away_team_in_match}",
                "margen": margen
            })
        except (ValueError, IndexError):
            continue
    
    return partidos

def analizar_contra_rival_del_rival(soup, home_team_name, away_team_name, rival_del_local, rival_del_visitante):
    """
    Analiza cómo le fue a cada equipo contra el último rival del otro.
    """
    analisis = {"home_vs_rival_away": None, "away_vs_rival_home": None}

    # Cómo le fue a home_team_name contra rival_del_visitante
    analisis["home_vs_rival_away"] = _buscar_enfrentamiento(soup, "table_v1", home_team_name, rival_del_visitante)
    
    # Cómo le fue a away_team_name contra rival_del_local
    analisis["away_vs_rival_home"] = _buscar_enfrentamiento(soup, "table_v2", away_team_name, rival_del_local)

    return analisis


def _buscar_enfrentamiento(soup, table_id, team_name, rival_name):
    tabla = soup.find("table", id=table_id)
    if not tabla:
        return None

    for r in tabla.find_all("tr", id=re.compile(rf"tr{table_id[-1]}_\d+")):
        celdas = r.find_all("td")
        if len(celdas) < 5:
            continue

        home_team_in_match = celdas[2].get_text(strip=True)
        away_team_in_match = celdas[4].get_text(strip=True)

        if (team_name.lower() in home_team_in_match.lower() and rival_name.lower() in away_team_in_match.lower()) or \
           (team_name.lower() in away_team_in_match.lower() and rival_name.lower() in home_team_in_match.lower()):
            
            return {
                "resultado": celdas[3].get_text(strip=True),
                "fecha": celdas[1].get_text(strip=True)
            }
            
    return None
