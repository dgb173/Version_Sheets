#!/usr/bin/env python3
"""Herramienta de consola para sincronizar datos con Google Sheets.

Ejemplos:
    python upload_to_google_sheets.py --dataset datos.json
    python upload_to_google_sheets.py --upcoming proximos.json --finished finalizados.json

El script sobrescribe por completo la informacion de:
    - Hoja 1: proximos partidos.
    - Hoja 2: partidos finalizados.
    - Hoja 3: historico consolidado (se anaden las nuevas filas).
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import gspread
import pandas as pd
from gspread_dataframe import get_as_dataframe, set_with_dataframe


GOOGLE_SECRET_IN_RENDER = Path("/etc/secrets/clave_sheets.json")
DEFAULT_LOCAL_SECRET = Path(__file__).resolve().parent / "clave_sheets.json"


def resolve_credentials_path(explicit: Optional[str]) -> Path:
    """Determina la ruta al archivo de credenciales."""
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"No se encontro el archivo de credenciales: {candidate}")
        return candidate

    env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path:
        candidate = Path(env_path).expanduser().resolve()
        if candidate.exists():
            return candidate

    if GOOGLE_SECRET_IN_RENDER.exists():
        return GOOGLE_SECRET_IN_RENDER

    if DEFAULT_LOCAL_SECRET.exists():
        return DEFAULT_LOCAL_SECRET

    raise FileNotFoundError(
        "No se localizaron credenciales. Usa --credentials o configura GOOGLE_APPLICATION_CREDENTIALS."
    )


def load_json_file(path: Path) -> Any:
    """Carga un archivo JSON manejando errores comunes."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_records_from_file(path: Path) -> List[Dict[str, Any]]:
    """Soporta JSON o CSV y devuelve una lista de diccionarios."""
    suffix = path.suffix.lower()
    if suffix in {".json"}:
        payload = load_json_file(path)
        if isinstance(payload, list):
            return [dict(item) for item in payload]
        raise ValueError(f"El archivo {path} debe contener una lista JSON.")

    if suffix in {".csv"}:
        frame = pd.read_csv(path)
        frame = frame.fillna("")
        return frame.to_dict(orient="records")

    raise ValueError(f"Formato no soportado para {path}. Usa JSON o CSV.")


def load_dataset(
    dataset_path: Optional[str],
    upcoming_path: Optional[str],
    finished_path: Optional[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Resuelve las fuentes de datos proporcionadas por la CLI."""
    if dataset_path:
        payload = load_json_file(Path(dataset_path))
        if not isinstance(payload, dict):
            raise ValueError("El JSON principal debe incluir claves 'upcoming' y 'finished'.")
        upcoming = payload.get("upcoming_matches") or payload.get("upcoming") or []
        finished = payload.get("finished_matches") or payload.get("finished") or []
        return (
            [dict(item) for item in upcoming],
            [dict(item) for item in finished],
        )

    upcoming_records: List[Dict[str, Any]] = []
    finished_records: List[Dict[str, Any]] = []

    if upcoming_path:
        upcoming_records = load_records_from_file(Path(upcoming_path))
    if finished_path:
        finished_records = load_records_from_file(Path(finished_path))

    if not upcoming_records and not finished_records:
        raise ValueError(
            "Debes proporcionar datos con --dataset o con la combinacion de --upcoming/--finished."
        )

    return upcoming_records, finished_records


def to_dataframe(records: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    """Convierte la coleccion en DataFrame, normalizando valores nulos."""
    records = list(records)
    if not records:
        return pd.DataFrame()
    frame = pd.DataFrame(records)
    frame.columns = [str(col) for col in frame.columns]
    frame = frame.fillna("")
    return frame


def overwrite_worksheet(worksheet: gspread.Worksheet, frame: pd.DataFrame) -> None:
    """Elimina contenido previo y escribe los datos nuevos."""
    worksheet.clear()
    if frame.empty:
        return
    set_with_dataframe(
        worksheet,
        frame,
        include_index=False,
        include_column_header=True,
        resize=True,
    )


def append_to_log(
    worksheet: gspread.Worksheet,
    upcoming_df: pd.DataFrame,
    finished_df: pd.DataFrame,
    deduplicate_column: Optional[str],
) -> None:
    """Actualiza la hoja historica consolidando registros anteriores."""
    frames: List[pd.DataFrame] = []
    timestamp = datetime.now(timezone.utc).isoformat()

    if not upcoming_df.empty:
        df = upcoming_df.copy()
        df["match_status"] = "upcoming"
        df["uploaded_at"] = timestamp
        frames.append(df)

    if not finished_df.empty:
        df = finished_df.copy()
        df["match_status"] = "finished"
        df["uploaded_at"] = timestamp
        frames.append(df)

    if not frames:
        return

    new_entries = pd.concat(frames, ignore_index=True)

    try:
        existing_df = get_as_dataframe(worksheet, evaluate_formulas=False)
    except Exception:
        existing_df = pd.DataFrame()

    existing_df.dropna(how="all", inplace=True)
    existing_df.columns = [str(col) for col in existing_df.columns]

    all_columns = list(
        dict.fromkeys(list(existing_df.columns) + list(new_entries.columns))
    )
    if existing_df.empty:
        combined = new_entries.reindex(columns=all_columns, fill_value="")
    else:
        existing_df = existing_df.reindex(columns=all_columns, fill_value="")
        new_entries = new_entries.reindex(columns=all_columns, fill_value="")
        combined = pd.concat([existing_df, new_entries], ignore_index=True)

    if deduplicate_column:
        col = deduplicate_column
        if col in combined.columns:
            combined[col] = combined[col].astype(str)
            combined = combined.drop_duplicates(subset=col, keep="last")

    combined = combined.fillna("")
    set_with_dataframe(
        worksheet,
        combined,
        include_index=False,
        include_column_header=True,
        resize=True,
    )


def build_gspread_client(credentials_path: Path) -> gspread.Client:
    """Autentica contra Google Sheets usando el archivo de servicio."""
    return gspread.service_account(filename=str(credentials_path))


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Define y procesa los argumentos de linea de comandos."""
    parser = argparse.ArgumentParser(
        description="Sincroniza los datos de partidos con la hoja 'Almacen_Stre'."
    )
    parser.add_argument(
        "--dataset",
        help="Archivo JSON con claves 'upcoming' y 'finished'.",
    )
    parser.add_argument(
        "--upcoming",
        help="Archivo JSON o CSV con los proximos partidos.",
    )
    parser.add_argument(
        "--finished",
        help="Archivo JSON o CSV con los partidos finalizados.",
    )
    parser.add_argument(
        "--credentials",
        help="Ruta al archivo de credenciales (por defecto se usa clave_sheets.json).",
    )
    parser.add_argument(
        "--sheet-name",
        default="Almacen_Stre",
        help="Nombre del documento de Google Sheets.",
    )
    parser.add_argument(
        "--worksheet-upcoming",
        default="Hoja 1",
        help="Pestaña para proximos partidos.",
    )
    parser.add_argument(
        "--worksheet-finished",
        default="Hoja 2",
        help="Pestaña para partidos finalizados.",
    )
    parser.add_argument(
        "--worksheet-log",
        default="Hoja 3",
        help="Pestaña historica donde se acumulan todos los registros.",
    )
    parser.add_argument(
        "--deduplicate-column",
        default="id",
        help="Columna usada para evitar duplicados en la hoja historica. Usa '' para desactivar.",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="No actualizar la hoja historica (Hoja 3).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    """Ejecuta el flujo completo de sincronizacion."""
    args = parse_args(argv)

    credentials_path = resolve_credentials_path(args.credentials)
    upcoming_records, finished_records = load_dataset(
        args.dataset,
        args.upcoming,
        args.finished,
    )
    upcoming_df = to_dataframe(upcoming_records)
    finished_df = to_dataframe(finished_records)

    client = build_gspread_client(credentials_path)
    spreadsheet = client.open(args.sheet_name)

    upcoming_ws = spreadsheet.worksheet(args.worksheet_upcoming)
    finished_ws = spreadsheet.worksheet(args.worksheet_finished)
    overwrite_worksheet(upcoming_ws, upcoming_df)
    overwrite_worksheet(finished_ws, finished_df)

    if not args.no_log:
        log_ws = spreadsheet.worksheet(args.worksheet_log)
        deduplicate_column = args.deduplicate_column.strip() or None
        append_to_log(log_ws, upcoming_df, finished_df, deduplicate_column)

    print("Sincronizacion completada correctamente.")


if __name__ == "__main__":
    main()
