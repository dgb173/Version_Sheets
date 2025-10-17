import re
import math

def _parse_number_clean(s: str):
    if s is None:
        return None
    txt = str(s).strip()
    txt = txt.replace('−', '-')  # unicode minus
    txt = txt.replace(',', '.')
    txt = txt.replace('+', '')
    txt = txt.replace(' ', '')
    m = re.search(r"^[+-]?\d+(?:\.\d+)?$", txt)
    if m:
        try:
            return float(m.group(0))
        except ValueError:
            return None
    return None

def _parse_handicap_to_float(text: str):
    if text is None:
        return None
    t = str(text).strip()
    if '/' in t:
        parts = [p for p in re.split(r"/", t) if p]
        nums = []
        for p in parts:
            v = _parse_number_clean(p)
            if v is None:
                return None
            nums.append(v)
        if not nums:
            return None
        return sum(nums) / len(nums)
    return _parse_number_clean(t.replace('+', ''))

def _bucket_to_half(value: float) -> float:
    if value is None:
        return None
    if value == 0:
        return 0.0
    sign = -1.0 if value < 0 else 1.0
    av = abs(value)
    base = math.floor(av + 1e-9)
    frac = av - base
    def close(a, b):
        return abs(a - b) < 1e-6
    if close(frac, 0.0):
        bucket = float(base)
    elif close(frac, 0.5) or close(frac, 0.25) or close(frac, 0.75):
        bucket = base + 0.5
    else:
        bucket = round(av * 2) / 2.0
        f = bucket - math.floor(bucket)
        if close(f, 0.0) and (abs(av - (math.floor(bucket) + 0.25)) < 0.26 or abs(av - (math.floor(bucket) + 0.75)) < 0.26):
            bucket = math.floor(bucket) + 0.5
    return sign * bucket

def normalize_handicap_to_half_bucket_str(text: str):
    v = _parse_handicap_to_float(text)
    if v is None:
        return None
    b = _bucket_to_half(v)
    if b is None:
        return None
    return f"{b:.1f}"

# --- Funciones movidas desde app.py para ser reutilizadas ---
import gspread
from gspread_dataframe import get_as_dataframe
import pandas as pd
import os
from datetime import datetime
import pytz

# Zona horaria para la comparación de partidos
MADRID_TZ = pytz.timezone('Europe/Madrid')

def load_data_from_sheets():
    """Carga los datos desde Google Sheets de forma segura para Render."""
    try:
        # Lógica de autenticación dual: para Render (con Secret File) y para local (con archivo)
        SECRET_FILE_PATH = '/etc/secrets/clave_sheets.json'
        if os.path.exists(SECRET_FILE_PATH):
            # Estamos en Render: usar el Secret File
            client = gspread.service_account(filename=SECRET_FILE_PATH)
            print("Autenticando con Google vía Secret File de Render.")
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