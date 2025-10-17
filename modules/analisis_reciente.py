from bs4 import BeautifulSoup
import re
from .utils import parse_ah_to_number_of, format_ah_as_decimal_string_of

def analizar_rendimiento_reciente_con_handicap(soup, team_name, is_home):
    """
    Analiza los últimos 8 partidos de un equipo y devuelve una lista de diccionarios con el análisis de hándicap.
    """
    table_id = "table_v1" if is_home else "table_v2"
    tabla = soup.find("table", id=table_id)
    if not tabla:
        return []

    partidos = tabla.find_all("tr", id=re.compile(rf"tr{table_id[-1]}_\d+"), limit=8)
    rendimiento = []

    for r in partidos:
        celdas = r.find_all("td")
        if len(celdas) < 12:
            continue

        try:
            resultado_raw = celdas[3].get_text(strip=True)
            goles_local, goles_visitante = map(int, re.split(r'[-:]', resultado_raw))
            
            handicap_raw = celdas[11].get("data-o", celdas[11].get_text(strip=True)).strip()
            handicap_num = parse_ah_to_number_of(handicap_raw)

            if handicap_num is None:
                continue

            home_team_in_match = celdas[2].get_text(strip=True)
            away_team_in_match = celdas[4].get_text(strip=True)

            equipo_es_local = team_name.lower() in home_team_in_match.lower()

            if equipo_es_local:
                margen = goles_local - goles_visitante
                favorito_num = 1 if handicap_num > 0 else (-1 if handicap_num < 0 else 0)
            else:
                margen = goles_visitante - goles_local
                favorito_num = -1 if handicap_num > 0 else (1 if handicap_num < 0 else 0)

            cubierto = "PUSH"
            if margen + handicap_num > 0.1:
                cubierto = "CUBIERTO"
            elif margen + handicap_num < -0.1:
                cubierto = "NO CUBIERTO"

            rendimiento.append({
                "resultado": resultado_raw,
                "handicap": format_ah_as_decimal_string_of(handicap_raw),
                "cubierto": cubierto
            })
        except (ValueError, IndexError):
            continue

    return rendimiento

def comparar_lineas_handicap_recientes(soup, team_name, current_ah_line, is_home):
    """
    Compara la línea de hándicap actual con las de los últimos partidos del equipo.
    """
    table_id = "table_v1" if is_home else "table_v2"
    tabla = soup.find("table", id=table_id)
    if not tabla:
        return "<p>No se pudieron analizar las líneas de hándicap recientes.</p>"

    partidos = tabla.find_all("tr", id=re.compile(rf"tr{table_id[-1]}_\d+"), limit=5)
    comparaciones = []

    for r in partidos:
        celdas = r.find_all("td")
        if len(celdas) < 12:
            continue

        handicap_raw = celdas[11].get("data-o", celdas[11].get_text(strip=True)).strip()
        handicap_num = parse_ah_to_number_of(handicap_raw)

        if handicap_num is None:
            continue

        diferencia = current_ah_line - handicap_num
        
        if abs(diferencia) > 0.25:
            if diferencia > 0:
                comparacion = f"La línea actual ({format_ah_as_decimal_string_of(str(current_ah_line))}) es <strong style='color: green;'>más favorable</strong> que en este partido ({format_ah_as_decimal_string_of(handicap_raw)})."
            else:
                comparacion = f"La línea actual ({format_ah_as_decimal_string_of(str(current_ah_line))}) es <strong style='color: red;'>menos favorable</strong> que en este partido ({format_ah_as_decimal_string_of(handicap_raw)})."
            comparaciones.append(f"<li>{comparacion}</li>")

    if not comparaciones:
        return "<p>No se encontraron diferencias significativas en las líneas de hándicap recientes.</p>"

    return f"<ul>{' '.join(comparaciones)}</ul>"
