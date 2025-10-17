from .utils import parse_ah_to_number_of, format_ah_as_decimal_string_of
import re

def generar_resumen_rendimiento_reciente(soup, home_team_name, away_team_name, current_ah_line):
    """
    Genera un resumen gráfico del rendimiento reciente y comparativas indirectas.
    """
    home_matches = _extraer_partidos_para_resumen(soup, "table_v1", home_team_name)
    away_matches = _extraer_partidos_para_resumen(soup, "table_v2", away_team_name)

    resumen_html = "<div class='resumen-rendimiento'>"
    resumen_html += "<h5>Resumen Gráfico de Rendimiento Reciente</h5>"
    resumen_html += "<table class='table table-sm table-bordered'>"
    resumen_html += "<thead class='table-dark'><tr><th>Equipo</th><th>Últimos 5 Partidos (Resultado y Cobertura AH)</th></tr></thead>"
    resumen_html += "<tbody>"
    resumen_html += f"<tr><td>{home_team_name}</td><td>{_generar_grafico_partidos(home_matches, current_ah_line, home_team_name, True)}</td></tr>"
    resumen_html += f"<tr><td>{away_team_name}</td><td>{_generar_grafico_partidos(away_matches, current_ah_line, away_team_name, False)}</td></tr>"
    resumen_html += "</tbody></table></div>"

    return resumen_html

def _extraer_partidos_para_resumen(soup, table_id, team_name):
    tabla = soup.find("table", id=table_id)
    if not tabla:
        return []

    partidos = []
    for r in tabla.find_all("tr", id=re.compile(rf"tr{table_id[-1]}_\d+"), limit=5):
        celdas = r.find_all("td")
        if len(celdas) < 12:
            continue

        try:
            resultado_raw = celdas[3].get_text(strip=True)
            handicap_raw = celdas[11].get("data-o", celdas[11].get_text(strip=True)).strip()
            home_team_in_match = celdas[2].get_text(strip=True)
            
            partidos.append({
                "resultado": resultado_raw,
                "handicap": handicap_raw,
                "es_local": team_name.lower() in home_team_in_match.lower()
            })
        except (ValueError, IndexError):
            continue
    
    return partidos

def _generar_grafico_partidos(partidos, current_ah_line, team_name, is_home_team):
    grafico_html = "<div class='d-flex'>"
    for p in reversed(partidos): # Para mostrar del más antiguo al más reciente
        try:
            goles = list(map(int, re.split(r'[-:]', p['resultado'])))
            margen = goles[0] - goles[1] if p['es_local'] else goles[1] - goles[0]

            resultado_letra = 'E'
            if margen > 0:
                resultado_letra = 'V'
            elif margen < 0:
                resultado_letra = 'D'

            # Análisis de cobertura de AH
            handicap_num = parse_ah_to_number_of(p['handicap'])
            cobertura_clase = 'text-muted' # Gris para push/error
            if handicap_num is not None:
                # Ajustar handicap si el equipo no era local
                if not p['es_local']:
                    handicap_num = -handicap_num
                
                if margen + handicap_num > 0.1:
                    cobertura_clase = 'text-success' # Verde si cubierto
                elif margen + handicap_num < -0.1:
                    cobertura_clase = 'text-danger' # Rojo si no cubierto

            grafico_html += f"<div class='text-center p-1 border mx-1 rounded'><strong class='{cobertura_clase}'>{resultado_letra}</strong></div>"

        except (ValueError, IndexError):
            continue
            
    grafico_html += "</div>"
    return grafico_html
