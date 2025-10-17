# app.py - Servidor web principal (Flask) - Versión Google Sheets para Render
from flask import Flask, render_template, abort, request, jsonify
import gspread
from gspread_dataframe import get_as_dataframe
import pandas as pd
import os
import time
from datetime import datetime
import pytz
import json

# La lógica de normalización de handicap está en su propio módulo
from app_utils import normalize_handicap_to_half_bucket_str

# --- IMPORTACIONES PARA VISTA PREVIA Y ESTUDIO ---
from modules.estudio_scraper import (
    obtener_datos_completos_partido, 
    format_ah_as_decimal_string_of, 
    obtener_datos_preview_rapido, 
    obtener_datos_preview_ligero, 
    generar_analisis_mercado_simplificado,
)
from modules.optimizacion_preview import obtener_datos_preview_ultrarapido


app = Flask(__name__)

# --- CONFIGURACIÓN DE GOOGLE SHEETS (MODIFICADO PARA RENDER) ---
# La ruta al archivo de credenciales ya no es una constante global.
# Se determina dentro de la función load_data_from_sheets.

# Zona horaria para la comparación de partidos
MADRID_TZ = pytz.timezone('Europe/Madrid')

def load_data_from_sheets():
    """Carga los datos desde Google Sheets de forma segura para Render."""
    try:
        # Lógica de autenticación dual: para Render (con variable de entorno) y para local (con archivo)
        if 'GOOGLE_CREDS_JSON' in os.environ:
            # Estamos en Render: usar la variable de entorno
            creds_json_str = os.environ.get('GOOGLE_CREDS_JSON')
            creds_dict = json.loads(creds_json_str)
            client = gspread.service_account_from_dict(creds_dict)
            print("Autenticando con Google vía variable de entorno.")
        else:
            # Estamos en local: usar el archivo clave_sheets.json
            KEY_FILE_PATH = os.path.join(os.path.dirname(__file__), 'clave_sheets.json')
            if not os.path.exists(KEY_FILE_PATH):
                print("ERROR: No se encontró 'clave_sheets.json' para ejecución local.")
                return {"upcoming_matches": [], "finished_matches": [], "error": "No se encontró el archivo de credenciales 'clave_sheets.json'."}
            client = gspread.service_account(filename=KEY_FILE_PATH)
            print("Autenticando con Google vía archivo local 'clave_sheets.json'.")
        spreadsheet = client.open("Almacen_Stre")

        # Cargar hojas de cálculo usando los nombres correctos: 'Hoja 1' y 'Hoja 2'
        upcoming_ws = spreadsheet.worksheet('Hoja 1')
        finished_ws = spreadsheet.worksheet('Hoja 2')

        # Convertir a DataFrames de Pandas
        # Usamos `evaluate_formulas=True` para obtener los valores calculados si los hubiera
        df_upcoming = get_as_dataframe(upcoming_ws, evaluate_formulas=True)
        df_finished = get_as_dataframe(finished_ws, evaluate_formulas=True)

        # Limpiar DataFrames: eliminar filas donde todos los valores son nulos
        df_upcoming.dropna(how='all', inplace=True)
        df_finished.dropna(how='all', inplace=True)

        # Convertir DataFrames a listas de diccionarios para ser usadas en las plantillas
        upcoming_matches = df_upcoming.to_dict('records')
        finished_matches = df_finished.to_dict('records')
        
        print(f"Datos cargados desde Google Sheet 'Almacen_Stre': {len(upcoming_matches)} próximos, {len(finished_matches)} finalizados.")
        return {"upcoming_matches": upcoming_matches, "finished_matches": finished_matches}

    except gspread.exceptions.SpreadsheetNotFound:
        print(f"ERROR: No se encontró el Google Sheet con el nombre 'Almacen_Stre'. Verifica el nombre y los permisos.")
        return {"upcoming_matches": [], "finished_matches": [], "error": "Spreadsheet 'Almacen_Stre' no encontrado."}
    except gspread.exceptions.WorksheetNotFound as e:
        print(f"ERROR: No se encontró una de las pestañas requeridas ('Hoja 1' o 'Hoja 2'): {e}")
        return {"upcoming_matches": [], "finished_matches": [], "error": f"Pestaña no encontrada: {e}"}
    except Exception as e:
        print(f"ERROR al cargar datos desde Google Sheets: {e}")
        return {"upcoming_matches": [], "finished_matches": [], "error": str(e)}

def filter_upcoming_matches(matches):
    """Filtra la lista de partidos para devolver solo los que no han comenzado."""
    now_madrid = datetime.now(MADRID_TZ)
    today_date = now_madrid.date()
    upcoming = []
    for match in matches:
        try:
            match_time_obj = match.get('time')
            if match_time_obj is None or pd.isna(match_time_obj):
                continue

            # Manejo robusto de fechas: string, datetime nativo o Timestamp de Pandas
            if isinstance(match_time_obj, str):
                # INTENTAR PARSEAR FECHA Y HORA
                try:
                    match_time = datetime.strptime(match_time_obj, '%Y-%m-%d %H:%M')
                except ValueError:
                    # SI FALLA, INTENTAR PARSEAR SOLO HORA Y USAR FECHA DE HOY
                    try:
                        time_only = datetime.strptime(match_time_obj, '%H:%M').time()
                        match_time = datetime.combine(today_date, time_only)
                    except ValueError:
                        # SI AMBOS FALLAN, SALTAR ESTE PARTIDO
                        print(f"ADVERTENCIA: Formato de fecha/hora no reconocido para el partido {match.get('id', 'N/A')}. Valor: '{match_time_obj}'")
                        continue

            elif isinstance(match_time_obj, datetime):
                match_time = match_time_obj
            else:
                # Conversión forzada desde otros tipos (ej. Timestamp)
                match_time = pd.to_datetime(match_time_obj).to_pydatetime()

            # Localizar la hora para una comparación correcta
            if match_time.tzinfo is None:
                match_time_madrid = MADRID_TZ.localize(match_time, is_dst=None)
            else:
                match_time_madrid = match_time.astimezone(MADRID_TZ)

            if match_time_madrid > now_madrid:
                upcoming.append(match)
        except (ValueError, KeyError, TypeError) as e:
            print(f"ADVERTENCIA: No se pudo procesar la fecha para el partido {match.get('id', 'N/A')}. Valor: '{match.get('time')}'. Error: {e}")
            continue
    return upcoming

@app.route('/')
def index():
    """Muestra los próximos partidos desde Google Sheets."""
    try:
        hf = request.args.get('handicap')
        all_data = load_data_from_sheets()
        
        if all_data.get("error"):
            return render_template('index.html', matches=[], error=f"No se pudieron cargar los partidos: {all_data.get('error')}"), 500

        matches = all_data.get('upcoming_matches', [])
        matches = filter_upcoming_matches(matches)
        
        opts = sorted({
            normalize_handicap_to_half_bucket_str(m.get('handicap'))
            for m in matches if m and normalize_handicap_to_half_bucket_str(m.get('handicap')) is not None
        }, key=lambda x: float(x))

        if hf:
            target = normalize_handicap_to_half_bucket_str(hf)
            if target is not None:
                matches = [m for m in matches if m and normalize_handicap_to_half_bucket_str(m.get('handicap', '')) == target]

        return render_template('index.html', matches=matches, handicap_filter=hf, handicap_options=opts, page_mode='upcoming', page_title='Próximos Partidos')
    except Exception as e:
        print(f"ERROR en la ruta principal: {e}")
        return render_template('index.html', matches=[], error=f"No se pudieron cargar los partidos: {e}", page_mode='upcoming', page_title='Próximos Partidos')

@app.route('/resultados')
def resultados():
    """Muestra los partidos finalizados desde Google Sheets."""
    try:
        hf = request.args.get('handicap')
        all_data = load_data_from_sheets()

        if all_data.get("error"):
            return render_template('index.html', matches=[], error=f"No se pudieron cargar los partidos: {all_data.get('error')}"), 500

        matches = all_data.get('finished_matches', [])

        opts = sorted({
            normalize_handicap_to_half_bucket_str(m.get('handicap'))
            for m in matches if m and normalize_handicap_to_half_bucket_str(m.get('handicap')) is not None
        }, key=lambda x: float(x))

        if hf:
            target = normalize_handicap_to_half_bucket_str(hf)
            if target is not None:
                matches = [m for m in matches if m and normalize_handicap_to_half_bucket_str(m.get('handicap', '')) == target]

        return render_template('index.html', matches=matches, handicap_filter=hf, handicap_options=opts, page_mode='finished', page_title='Resultados Finalizados')
    except Exception as e:
        print(f"ERROR en la ruta de resultados: {e}")
        return render_template('index.html', matches=[], error=f"No se pudieron cargar los partidos: {e}", page_mode='finished', page_title='Resultados Finalizados')

@app.route('/api/matches')
def api_matches():
    try:
        offset = int(request.args.get('offset', 0))
        limit = int(request.args.get('limit', 10))
        hf = request.args.get('handicap')
        
        all_data = load_data_from_sheets()
        if all_data.get("error"):
            return jsonify({'error': all_data.get('error')}), 500

        matches = all_data.get('upcoming_matches', [])
        matches = filter_upcoming_matches(matches)

        if hf:
            target = normalize_handicap_to_half_bucket_str(hf)
            if target is not None:
                matches = [m for m in matches if m and normalize_handicap_to_half_bucket_str(m.get('handicap', '')) == target]

        paginated_matches = matches[offset:offset+limit]
        return jsonify({'matches': paginated_matches})
    except Exception as e:
        print(f"Error en la ruta /api/matches: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/finished_matches')
def api_finished_matches():
    try:
        offset = int(request.args.get('offset', 0))
        limit = int(request.args.get('limit', 10))
        hf = request.args.get('handicap')
        
        all_data = load_data_from_sheets()
        if all_data.get("error"):
            return jsonify({'error': all_data.get('error')}), 500
            
        matches = all_data.get('finished_matches', [])

        if hf:
            target = normalize_handicap_to_half_bucket_str(hf)
            if target is not None:
                matches = [m for m in matches if m and normalize_handicap_to_half_bucket_str(m.get('handicap', '')) == target]

        paginated_matches = matches[offset:offset+limit]
        return jsonify({'matches': paginated_matches})
    except Exception as e:
        print(f"Error en la ruta /api/finished_matches: {e}")
        return jsonify({'error': str(e)}), 500

# --- RUTAS DE ESTUDIO Y VISTA PREVIA (SCRAPING EN TIEMPO REAL) ---

def _get_preview_cache_dir():
    static_root = os.path.join(os.path.dirname(__file__), 'static')
    return os.path.join(static_root, 'cached_previews')

def load_preview_from_cache(match_id: str):
    cache_dir = _get_preview_cache_dir()
    cache_file = os.path.join(cache_dir, f'{match_id}.json')
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None

def save_preview_to_cache(match_id: str, data: dict):
    cache_dir = _get_preview_cache_dir()
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f'{match_id}.json')
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except OSError:
        pass

@app.route('/api/analisis/<string:match_id>')
def api_analisis(match_id):
    """Servicio de analisis profundo bajo demanda con cache."""
    cached_data = load_preview_from_cache(match_id)
    if cached_data:
        print(f"Devolviendo analisis cacheado para {match_id}")
        return jsonify(cached_data)

    print(f"No hay cache para {match_id}. Ejecutando scraping en tiempo real...")
    # Usamos la función más rápida como fuente para la caché
    live_data = obtener_datos_preview_ultrarapido(match_id)
    
    if isinstance(live_data, dict) and not live_data.get("error"):
        save_preview_to_cache(match_id, live_data)
        
    return jsonify(live_data)


@app.route('/estudio/<string:match_id>')
def mostrar_estudio(match_id):
    print(f"Recibida petición para el estudio del partido ID: {match_id}")
    datos_partido = obtener_datos_completos_partido(match_id)
    if not datos_partido or "error" in datos_partido:
        print(f"Error al obtener datos para {match_id}: {datos_partido.get('error')}")
        abort(500, description=datos_partido.get('error', 'Error desconocido'))
    print(f"Datos obtenidos para {datos_partido['home_name']} vs {datos_partido['away_name']}. Renderizando plantilla...")
    return render_template('estudio.html', data=datos_partido, format_ah=format_ah_as_decimal_string_of)

@app.route('/analizar_partido', methods=['GET', 'POST'])
def analizar_partido():
    if request.method == 'POST':
        match_id = request.form.get('match_id')
        if match_id:
            print(f"Recibida petición para analizar partido finalizado ID: {match_id}")
            datos_partido = obtener_datos_completos_partido(match_id)
            if not datos_partido or "error" in datos_partido:
                return render_template('analizar_partido.html', error=datos_partido.get('error', 'Error desconocido'))
            
            main_odds = datos_partido.get("main_match_odds_data")
            h2h_data = datos_partido.get("h2h_data")
            home_name = datos_partido.get("home_name")
            away_name = datos_partido.get("away_name")

            analisis_simplificado_html = ""
            if all([main_odds, h2h_data, home_name, away_name]):
                analisis_simplificado_html = generar_analisis_mercado_simplificado(main_odds, h2h_data, home_name, away_name)

            print(f"Datos obtenidos para {datos_partido['home_name']} vs {datos_partido['away_name']}. Renderizando plantilla...")
            return render_template('estudio.html', 
                                   data=datos_partido, 
                                   format_ah=format_ah_as_decimal_string_of,
                                   analisis_simplificado_html=analisis_simplificado_html)
        else:
            return render_template('analizar_partido.html', error="Por favor, introduce un ID de partido válido.")
    return render_template('analizar_partido.html')

@app.route('/api/preview/<string:match_id>')
def api_preview(match_id):
    try:
        mode = request.args.get('mode', 'ultra').lower()
        include_performance = request.args.get('perf', 'false').lower() == 'true'
        
        if mode in ['full', 'selenium']:
            inicio = time.time()
            preview_data = obtener_datos_preview_rapido(match_id)
            tiempo_total = time.time() - inicio
        elif mode == 'light':
            inicio = time.time()
            preview_data = obtener_datos_preview_ligero(match_id)
            tiempo_total = time.time() - inicio
        else: # ultra
            inicio = time.time()
            preview_data = obtener_datos_preview_ultrarapido(match_id)
            tiempo_total = time.time() - inicio
            if not include_performance and 'performance' in preview_data and preview_data['performance']['modo'] == 'ultra_rapido_paralelo_con_cache':
                include_performance = True
        
        if isinstance(preview_data, dict) and "error" in preview_data:
            return jsonify(preview_data), 500
        
        if include_performance and 'performance' not in preview_data:
            preview_data['performance'] = {
                'tiempo_total_segundos': round(tiempo_total, 3),
                'modo': mode,
                'tiempo_carga_datos': 'no medido'
            }
        
        return jsonify(preview_data)

    except Exception as e:
        error_message = f"Ocurrió una excepción inesperada: {str(e)}"
        print(f"Error en la ruta /api/preview/{match_id}: {error_message}")
        return jsonify({'error': error_message}), 500

if __name__ == '__main__':
    # Render usará un servidor WSGI como Gunicorn, por lo que este bloque no se ejecutará en producción.
    # Es útil para pruebas locales.
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)), debug=True)
