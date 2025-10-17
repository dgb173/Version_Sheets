"""
optimizacion_preview.py
Implementación de las optimizaciones para la vista previa rápida
"""

import concurrent.futures
import requests
from bs4 import BeautifulSoup
import time
import re
import pandas as pd

# Importar las funciones necesarias desde estudio_scraper.py
from .estudio_scraper import (
    parse_ah_to_number_of,
    format_ah_as_decimal_string_of,
    check_handicap_cover,
    extract_bet365_initial_odds_of,
    extract_h2h_data_of,
    extract_last_match_in_league_of,
    get_match_progression_stats_data,
    extract_indirect_comparison_data,
    get_team_league_info_from_script_of,
    get_match_datetime_from_script_of,
    get_rival_a_for_original_h2h_of,
    get_rival_b_for_original_h2h_of,
    get_h2h_details_for_original_logic_of
)

# Constantes
BASE_URL_OF = "https://live18.nowgoal25.com"

# Diccionario simple para caché en memoria
preview_cache = {}
CACHE_DURATION = 300  # 5 minutos

def cached_preview(duration=CACHE_DURATION):
    """Decorador para caché de resultados de vista previa"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Crear una clave única para los argumentos
            cache_key = f"{func.__name__}_{args[0] if args else 'no_id'}"
            
            # Verificar si hay datos en caché y no han expirado
            if cache_key in preview_cache:
                result, timestamp = preview_cache[cache_key]
                if time.time() - timestamp < duration:
                    print(f"Usando caché para {cache_key}")
                    return result
            
            # Si no está en caché o ha expirado, ejecutar la función original
            result = func(*args, **kwargs)
            
            # Almacenar en caché
            preview_cache[cache_key] = (result, time.time())
            print(f"Resultados almacenados en caché para {cache_key}")
            return result
        return wrapper
    return decorator

@cached_preview()
def obtener_datos_preview_ultrarapido(match_id: str):
    """
    Scraper ultradevuelto y optimizado para obtener solo los datos de la vista previa.
    Reutiliza sesiones HTTP y procesa datos en paralelo donde sea posible.
    """
    # Registrar el tiempo de inicio
    inicio_total = time.time()
    
    if not match_id or not match_id.isdigit():
        return {"error": "ID de partido inválido."}

    url = f"{BASE_URL_OF}/match/h2h-{match_id}"
    
    try:
        # Reutilizar la sesión HTTP para todas las peticiones
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/116.0.0.0 Safari/537.36"
        })
        
        # Obtener la página principal
        inicio_solicitud = time.time()
        response = session.get(url, timeout=5)
        response.raise_for_status()
        tiempo_solicitud = time.time() - inicio_solicitud
        soup = BeautifulSoup(response.text, 'lxml')

        # Extracción de datos básicos (igual que antes)
        _, _, league_id, home_name, away_name, _ = get_team_league_info_from_script_of(soup)
        dt_info = get_match_datetime_from_script_of(soup)

        # Línea AH (Bet365 inicial)
        main_odds = extract_bet365_initial_odds_of(soup)
        ah_line_raw = main_odds.get('ah_linea_raw', '-')
        ah_line_num = parse_ah_to_number_of(ah_line_raw)
        favorito_actual = None
        if ah_line_num is not None:
            if ah_line_num > 0:
                favorito_actual = home_name
            elif ah_line_num < 0:
                favorito_actual = away_name

        # Procesamiento en paralelo de datos de rendimiento
        inicio_analisis = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            # Tareas concurrentes para rendimiento reciente
            future_home_form = executor.submit(analizar_rendimiento_optimizado, "table_v1", home_name, soup)
            future_away_form = executor.submit(analizar_rendimiento_optimizado, "table_v2", away_name, soup)
            future_h2h_stats = executor.submit(analizar_h2h_directo_optimizado, soup, home_name, away_name, ah_line_num, favorito_actual)
            
            # Obtener resultados
            rendimiento_local = future_home_form.result()
            rendimiento_visitante = future_away_form.result()
            h2h_stats, last_h2h_cover = future_h2h_stats.result()
        tiempo_analisis = time.time() - inicio_analisis

        # Obtención de datos indirectos con paralelización
        inicio_datos_indirectos = time.time()
        recent_indirect = obtener_datos_indirectos_optimizados(session, soup, home_name, away_name, league_id)
        tiempo_datos_indirectos = time.time() - inicio_datos_indirectos
        
        # Procesamiento de H2H indirecto
        inicio_h2h_indirecto = time.time()
        indirect = analizar_h2h_indirecto_optimizado(soup, home_name, away_name)
        tiempo_h2h_indirecto = time.time() - inicio_h2h_indirecto
        
        # Análisis de ataques peligrosos
        indirect_panels = extract_indirect_comparison_data(soup)
        inicio_ataques_peligrosos = time.time()
        ataques_peligrosos, favorite_da = analizar_ataques_peligrosos_optimizados(indirect_panels, favorito_actual)
        tiempo_ataques_peligrosos = time.time() - inicio_ataques_peligrosos

        # Calcular tiempo total
        tiempo_total = time.time() - inicio_total
        
        # Resultado final
        result = {
            "home_team": home_name,
            "away_team": away_name,
            "recent_form": {
                "home": rendimiento_local,
                "away": rendimiento_visitante,
            },
            "recent_indirect": recent_indirect,
            "handicap": {
                "ah_line": format_ah_as_decimal_string_of(ah_line_raw),
                "favorite": favorito_actual or "",
                "cover_on_last_h2h": last_h2h_cover
            },
            "dangerous_attacks": ataques_peligrosos,
            "favorite_dangerous_attacks": favorite_da,
            "h2h_indirect": indirect,
            "h2h_stats": h2h_stats
        }

        # Añadir campos de fecha/hora del partido
        result.update({
            "match_date": dt_info.get("match_date"),
            "match_time": dt_info.get("match_time"),
            "match_datetime": dt_info.get("match_datetime"),
        })

        # Añadir tiempos de ejecución
        result["performance"] = {
            "tiempo_total_segundos": round(tiempo_total, 3),
            "tiempo_solicitud_datos_segundos": round(tiempo_solicitud, 3),
            "tiempo_analisis_rendimiento_segundos": round(tiempo_analisis, 3),
            "tiempo_datos_indirectos_segundos": round(tiempo_datos_indirectos, 3),
            "tiempo_h2h_indirecto_segundos": round(tiempo_h2h_indirecto, 3),
            "tiempo_ataques_peligrosos_segundos": round(tiempo_ataques_peligrosos, 3),
            "modo": "ultra_rapido_paralelo_con_cache"
        }

        return result

    except requests.Timeout:
        return {"error": "La fuente de datos (Nowgoal) tardó demasiado en responder."}
    except Exception as e:
        print(f"ERROR en scraper preview ultrarrápido para {match_id}: {e}")
        import traceback
        traceback.print_exc()
        return {"error": f"No se pudieron obtener los datos de la vista previa: {type(e).__name__}"}
    finally:
        try:
            if 'session' in locals():
                session.close()
        except Exception:
            pass

def analizar_rendimiento_optimizado(tabla_id, equipo_nombre, soup):
    """
    Versión optimizada del análisis de rendimiento reciente
    """
    tabla = soup.find("table", id=tabla_id)
    if not tabla:
        return {"wins": 0, "draws": 0, "losses": 0, "total": 0}
    
    partidos = tabla.find_all("tr", id=re.compile(rf"tr{tabla_id[-1]}_\d+"), limit=8)
    wins = draws = losses = 0
    
    for r in partidos:
        celdas = r.find_all("td")
        if len(celdas) < 5:
            continue
            
        # Extraer información de resultado directamente
        resultado_span = celdas[5].find("span")
        classes = resultado_span.get('class', []) if resultado_span else []
        resultado_txt = resultado_span.get_text(strip=True).lower() if resultado_span else ''
        
        if 'win' in classes or resultado_txt in ('w', 'win', 'victoria'):
            wins += 1
            continue
        elif 'lose' in classes or resultado_txt in ('l', 'lose', 'derrota'):
            losses += 1
            continue
        elif 'draw' in classes or resultado_txt in ('d', 'draw', 'empate'):
            draws += 1
            continue
            
        # Si no hay clase definida, calcular resultado manualmente
        score_text = celdas[3].get_text(strip=True)
        try:
            goles_local, goles_visitante = map(int, re.split(r'[-:]', score_text))
        except Exception:
            continue
            
        home_t = celdas[2].get_text(strip=True)
        away_t = celdas[4].get_text(strip=True)
        equipo_es_local = equipo_nombre.lower() in home_t.lower()
        equipo_es_visitante = equipo_nombre.lower() in away_t.lower()
        
        if not equipo_es_local and not equipo_es_visitante:
            continue
            
        if equipo_es_local:
            if goles_local > goles_visitante:
                wins += 1
            elif goles_local < goles_visitante:
                losses += 1
            else:
                draws += 1
        else:
            if goles_visitante > goles_local:
                wins += 1
            elif goles_visitante < goles_local:
                losses += 1
            else:
                draws += 1
    
    return {"wins": wins, "draws": draws, "losses": losses, "total": len(partidos)}

def analizar_h2h_directo_optimizado(soup, home_name, away_name, ah_line_num, favorito_actual):
    """
    Versión optimizada del análisis H2H directo
    """
    h2h_stats = {"home_wins": 0, "away_wins": 0, "draws": 0}
    last_h2h_cover = "DESCONOCIDO"
    
    try:
        h2h_data = extract_h2h_data_of(soup, home_name, away_name, None)
        h2h_table = soup.find("table", id="table_v3")
        if h2h_table:
            partidos_h2h = h2h_table.find_all("tr", id=re.compile(r"tr3_\d+"), limit=8)
            for r in partidos_h2h:
                tds = r.find_all("td")
                if len(tds) < 5:
                    continue
                home_h2h = tds[2].get_text(strip=True)
                resultado_raw = tds[3].get_text(strip=True)
                try:
                    goles_h, goles_a = map(int, resultado_raw.split("-"))
                    es_local_en_h2h = home_name.lower() in home_h2h.lower()
                    if goles_h == goles_a:
                        h2h_stats["draws"] += 1
                    elif (es_local_en_h2h and goles_h > goles_a) or (not es_local_en_h2h and goles_a > goles_h):
                        h2h_stats["home_wins"] += 1
                    else:
                        h2h_stats["away_wins"] += 1
                except (ValueError, IndexError):
                    continue
        
        # Evaluar cobertura del favorito con el último H2H disponible
        res_raw = None
        h_home = None
        h_away = None
        if h2h_data.get('res1_raw') and h2h_data.get('res1_raw') != '?-':
            res_raw = h2h_data['res1_raw']
            h_home = home_name
            h_away = away_name
        elif h2h_data.get('res6_raw') and h2h_data.get('res6_raw') != '?-':
            res_raw = h2h_data['res6_raw']
            h_home = h2h_data.get('h2h_gen_home', home_name)
            h_away = h2h_data.get('h2h_gen_away', away_name)
        
        if favorito_actual and (ah_line_num is not None) and res_raw:
            ct, _ = check_handicap_cover(res_raw.replace(':', '-'), ah_line_num, favorito_actual, h_home, h_away, home_name)
            last_h2h_cover = ct
            
    except Exception as e:
        print(f"Error en análisis H2H directo: {e}")
    
    return h2h_stats, last_h2h_cover

def obtener_datos_indirectos_optimizados(session, soup, home_name, away_name, league_id):
    """
    Obtener datos indirectos (últimos partidos y H2H Col3) de forma optimizada
    """
    recent_indirect = {"last_home": None, "last_away": None, "h2h_col3": None}
    
    try:
        # Obtener información de los equipos en una sola pasada
        last_home = extract_last_match_in_league_of(soup, "table_v1", home_name, league_id, True)
        last_away = extract_last_match_in_league_of(soup, "table_v2", away_name, league_id, False)
        
        def _df_to_rows(df):
            rows = []
            try:
                if df is not None and not df.empty:
                    for idx, row in df.iterrows():
                        label = idx.replace('Shots on Goal', 'Tiros a Puerta').replace('Shots', 'Tiros').replace('Dangerous Attacks', 'Ataques Peligrosos').replace('Attacks', 'Ataques')
                        rows.append({"label": label, "home": row.get('Casa', ''), "away": row.get('Fuera', '')})
            except Exception:
                pass
            return rows

        # Procesar los últimos partidos de forma paralela
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_last_home_stats = executor.submit(get_match_progression_stats_data, str(last_home.get('match_id'))) if last_home and last_home.get('match_id') else None
            future_last_away_stats = executor.submit(get_match_progression_stats_data, str(last_away.get('match_id'))) if last_away and last_away.get('match_id') else None
            
            if last_home:
                last_home_stats = future_last_home_stats.result() if future_last_home_stats else None
                recent_indirect["last_home"] = {
                    "home": last_home.get('home_team'),
                    "away": last_home.get('away_team'),
                    "score": last_home.get('score'),
                    "ah": format_ah_as_decimal_string_of(last_home.get('handicap_line_raw', '-') or '-'),
                    "ou": "-",
                    "stats_rows": _df_to_rows(last_home_stats),
                    "date": last_home.get('date')
                }
            
            if last_away:
                last_away_stats = future_last_away_stats.result() if future_last_away_stats else None
                recent_indirect["last_away"] = {
                    "home": last_away.get('home_team'),
                    "away": last_away.get('away_team'),
                    "score": last_away.get('score'),
                    "ah": format_ah_as_decimal_string_of(last_away.get('handicap_line_raw', '-') or '-'),
                    "ou": "-",
                    "stats_rows": _df_to_rows(last_away_stats),
                    "date": last_away.get('date')
                }

        # Procesar H2H Col3
        key_id_a, rival_a_id, rival_a_name = get_rival_a_for_original_h2h_of(soup, league_id)
        _, rival_b_id, rival_b_name = get_rival_b_for_original_h2h_of(soup, league_id)
        
        if key_id_a and rival_a_id and rival_b_id:
            # Hacer la solicitud para H2H Col3 reutilizando la sesión
            key_url = f"{BASE_URL_OF}/match/h2h-{key_id_a}"
            key_resp = session.get(key_url, timeout=6)
            key_resp.raise_for_status()
            soup_key = BeautifulSoup(key_resp.text, 'lxml')
            
            table = soup_key.find("table", id="table_v2")
            if table:
                for row in table.find_all("tr", id=re.compile(r"tr2_\d+")):
                    links = row.find_all("a", onclick=True)
                    if len(links) < 2:
                        continue
                    m_h = re.search(r"team\((\d+)\)", links[0].get("onclick", ""))
                    m_a = re.search(r"team\((\d+)\)", links[1].get("onclick", ""))
                    if not (m_h and m_a):
                        continue
                    if {m_h.group(1), m_a.group(1)} == {str(rival_a_id), str(rival_b_id)}:
                        score_span = row.find("span", class_="fscore_2")
                        if not score_span or '-' not in score_span.text:
                            break
                        score_txt = score_span.text.strip().split("(")[0].strip()
                        try:
                            g_h, g_a = score_txt.split('-', 1)
                        except Exception:
                            break
                        tds = row.find_all("td")
                        ah_raw = "-"
                        if len(tds) > 11:
                            cell = tds[11]
                            ah_raw = (cell.get("data-o") or cell.text).strip() or "-"
                        match_id_col3 = row.get('index')
                        score_line = f"{links[0].text.strip()} {g_h}:{g_a} {links[1].text.strip()}"
                        col3_stats = get_match_progression_stats_data(str(match_id_col3))
                        # Fecha si existe
                        date_txt = None
                        try:
                            date_span = tds[1].find('span', attrs={'name': 'timeData'}) if len(tds) > 1 else None
                            date_txt = date_span.get_text(strip=True) if date_span else None
                        except Exception:
                            date_txt = None
                        recent_indirect["h2h_col3"] = {
                            "score_line": score_line,
                            "ah": format_ah_as_decimal_string_of(ah_raw or '-'),
                            "ou": "-",
                            "stats_rows": _df_to_rows(col3_stats),
                            "date": date_txt
                        }
                        break
    except Exception as e:
        print(f"Error en datos indirectos: {e}")
        import traceback
        traceback.print_exc()
    
    return recent_indirect

def analizar_h2h_indirecto_optimizado(soup, home_name, away_name):
    """
    Optimización del análisis de H2H indirecto
    """
    indirect = {"home_better": 0, "away_better": 0, "draws": 0, "samples": []}
    
    try:
        table_v1 = soup.find("table", id="table_v1")
        table_v2 = soup.find("table", id="table_v2")

        def _parse_score_to_tuple(score_text):
            try:
                gh, ga = map(int, score_text.strip().split("-"))
                return gh, ga
            except Exception:
                return None

        def _find_match_info(table, rival_name_lower, team_name_ref):
            if not table:
                return None
            rows = table.find_all("tr", id=re.compile(r"tr[12]_\d+"))
            for r in rows:
                tds = r.find_all("td")
                if len(tds) < 5:
                    continue
                home_t = tds[2].get_text(strip=True)
                away_t = tds[4].get_text(strip=True)
                if away_t.lower() == rival_name_lower or home_t.lower() == rival_name_lower:
                    score_text = tds[3].get_text(strip=True)
                    score = _parse_score_to_tuple(score_text)
                    if not score:
                        continue
                    gh, ga = score
                    if home_t.lower() == team_name_ref.lower():
                        margin = gh - ga
                    elif away_t.lower() == team_name_ref.lower():
                        margin = ga - gh
                    else:
                        margin = gh - ga
                    return {"rival": rival_name_lower, "margin": margin}
            return None

        if table_v1 and table_v2:
            # Obtener rivales de forma más eficiente
            rivals_home = {tds[4].get_text(strip=True).lower() 
                          for r in table_v1.find_all("tr", id=re.compile(r"tr1_\d+"))
                          for tds in [r.find_all("td")] if len(tds) >= 5 and tds[4].get_text(strip=True).lower() != '?'}
            
            rivals_away = {tds[2].get_text(strip=True).lower() 
                          for r in table_v2.find_all("tr", id=re.compile(r"tr2_\d+"))
                          for tds in [r.find_all("td")] if len(tds) >= 5 and tds[2].get_text(strip=True).lower() != '?'}

            common = [rv for rv in rivals_home.intersection(rivals_away) if rv]
            common = common[:3]
            
            for rv in common:
                home_info = _find_match_info(table_v1, rv, home_name)
                away_info = _find_match_info(table_v2, rv, away_name)
                
                if not home_info or not away_info:
                    continue
                
                if home_info["margin"] > away_info["margin"]:
                    indirect["home_better"] += 1
                    verdict = "home"
                elif home_info["margin"] < away_info["margin"]:
                    indirect["away_better"] += 1
                    verdict = "away"
                else:
                    indirect["draws"] += 1
                    verdict = "draw"
                
                indirect["samples"].append({
                    "rival": rv,
                    "home_margin": home_info["margin"],
                    "away_margin": away_info["margin"],
                    "verdict": verdict
                })
    except Exception as e:
        print(f"Error en análisis H2H indirecto: {e}")
    
    return indirect

def analizar_ataques_peligrosos_optimizados(indirect_panels, favorito_actual):
    """
    Análisis optimizado de ataques peligrosos
    """
    ataques_peligrosos = {}
    favorite_da = None
    
    try:
        if indirect_panels and indirect_panels.get("comp1"):
            c1 = indirect_panels["comp1"]
            ap_home = int(c1['stats'].get('ataques_peligrosos_casa', 0) or 0)
            ap_away = int(c1['stats'].get('ataques_peligrosos_fuera', 0) or 0)
            own_ap, rival_ap = (ap_away, ap_home) if c1.get('localia') == 'A' else (ap_home, ap_away)
            ataques_peligrosos['team1'] = {
                "name": c1['main_team'],
                "own": own_ap,
                "rival": rival_ap,
                "very_superior": bool((own_ap - rival_ap) >= 5)
            }
        
        if indirect_panels and indirect_panels.get("comp2"):
            c2 = indirect_panels["comp2"]
            ap_home = int(c2['stats'].get('ataques_peligrosos_casa', 0) or 0)
            ap_away = int(c2['stats'].get('ataques_peligrosos_fuera', 0) or 0)
            own_ap, rival_ap = (ap_away, ap_home) if c2.get('localia') == 'A' else (ap_home, ap_away)
            ataques_peligrosos['team2'] = {
                "name": c2['main_team'],
                "own": own_ap,
                "rival": rival_ap,
                "very_superior": bool((own_ap - rival_ap) >= 5)
            }
        
        # Identificar el bloque correspondiente al favorito
        fav_name = (favorito_actual or '').lower()
        for key in ['team1', 'team2']:
            if key in ataques_peligrosos and ataques_peligrosos[key]['name'].lower() == fav_name:
                favorite_da = {
                    "name": ataques_peligrosos[key]['name'],
                    "very_superior": ataques_peligrosos[key]['very_superior'],
                    "own": ataques_peligrosos[key]['own'],
                    "rival": ataques_peligrosos[key]['rival']
                }
                break
    except Exception as e:
        print(f"Error en análisis de ataques peligrosos: {e}")
    
    return ataques_peligrosos, favorite_da
