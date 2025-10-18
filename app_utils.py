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
import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytz

# Zona horaria para la comparación de partidos
MADRID_TZ = pytz.timezone('Europe/Madrid')

DATA_JSON_ENV_VAR = "DATA_JSON_PATH"
_DEFAULT_DATASET_CANDIDATES = ("datos.json", "data.json")


def _discover_default_dataset() -> Path:
    base_dir = Path(__file__).resolve().parents[2]
    for name in _DEFAULT_DATASET_CANDIDATES:
        candidate = base_dir / name
        if candidate.exists():
            return candidate
    return base_dir / _DEFAULT_DATASET_CANDIDATES[0]


DEFAULT_DATA_JSON = _discover_default_dataset()


def _resolve_data_json_path(explicit_path: str | None = None) -> Path:
    if explicit_path:
        candidate = Path(explicit_path).expanduser().resolve()
        if candidate.exists():
            return candidate
    env_path = os.environ.get(DATA_JSON_ENV_VAR)
    if env_path:
        candidate = Path(env_path).expanduser().resolve()
        if candidate.exists():
            return candidate
    return DEFAULT_DATA_JSON


def load_data_from_sheets(data_path: str | None = None):
    """Carga los datos desde data.json, conservando la interfaz original."""
    try:
        data_file = _resolve_data_json_path(data_path)
        if not data_file.exists():
            msg = f"No se encontró el archivo de datos en {data_file}"
            print(f"ERROR: {msg}")
            return {"upcoming_matches": [], "finished_matches": [], "error": msg}

        with data_file.open("r", encoding="utf-8") as fh:
            raw_data = json.load(fh)

        upcoming_matches = raw_data.get("upcoming_matches", []) or []
        finished_matches = raw_data.get("finished_matches", []) or []

        print(
            f"Datos cargados desde '{data_file}': "
            f"{len(upcoming_matches)} próximos, {len(finished_matches)} finalizados."
        )
        return {
            "upcoming_matches": upcoming_matches,
            "finished_matches": finished_matches,
            "source_path": str(data_file),
        }
    except Exception as e:
        print(f"ERROR al cargar datos locales: {e}")
        return {
            "upcoming_matches": [],
            "finished_matches": [],
            "error": str(e),
            "source_path": str(_resolve_data_json_path(data_path)),
        }

def filter_upcoming_matches(matches):
    """Filtra la lista de partidos para devolver solo los que no han comenzado."""
    now_madrid = datetime.now(MADRID_TZ)
    today_date = now_madrid.date()
    upcoming = []
    for match in matches:
        try:
            match_time_obj = match.get('time_obj') or match.get('time')
            if match_time_obj is None or (isinstance(match_time_obj, float) and pd.isna(match_time_obj)):
                continue

            # Manejo robusto de fechas: string, datetime nativo o Timestamp de Pandas
            if isinstance(match_time_obj, str):
                parsed_dt = None
                parsers = (
                    lambda v: datetime.fromisoformat(v.replace("Z", "+00:00")),
                    lambda v: datetime.strptime(v, "%Y-%m-%d %H:%M"),
                    lambda v: datetime.strptime(v, "%d/%m %H:%M").replace(year=now_madrid.year),
                    lambda v: datetime.combine(today_date, datetime.strptime(v, "%H:%M").time()),
                )
                for parser in parsers:
                    try:
                        parsed_dt = parser(match_time_obj)
                        break
                    except (ValueError, TypeError):
                        continue
                if parsed_dt is None:
                    print(
                        f"ADVERTENCIA: Formato de fecha/hora no reconocido para el partido "
                        f"{match.get('id', 'N/A')}. Valor: '{match_time_obj}'"
                    )
                    continue
                match_time = parsed_dt

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
            print(
                f"ADVERTENCIA: No se pudo procesar la fecha para el partido {match.get('id', 'N/A')}."
                f" Valor: '{match.get('time')}'. Error: {e}"
            )
            continue
    return upcoming
