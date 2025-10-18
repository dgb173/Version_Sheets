"""Script reutilizable para Google Colab que genera `data.json` con 1000 partidos.

Uso rápido en Colab:

```python
!python colab_generar_datos.py --limit 1000 --output datos.json --html datos_preview.html
```

Si la celda ya tiene un bucle de eventos activo (Colab/IPython), el script aplica
`nest_asyncio` automáticamente para poder ejecutar `asyncio`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import pytz

# Aseguramos que el directorio raiz del proyecto esté en sys.path
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scraping_logic import (  # noqa: E402  (importación tardía tras ajustar sys.path)
    get_main_page_finished_matches_async,
    get_main_page_matches_async,
)

MADRID_TZ = pytz.timezone("Europe/Madrid")
DEFAULT_LIMIT = 1000
DEFAULT_OUTPUT = ROOT_DIR / "data.json"


def _parse_time(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    parsers = (
        lambda v: datetime.fromisoformat(v.replace("Z", "+00:00")),
        lambda v: datetime.strptime(v, "%Y-%m-%d %H:%M"),
        lambda v: datetime.strptime(v, "%d/%m %H:%M"),
        lambda v: datetime.strptime(v, "%H:%M"),
    )
    for parser in parsers:
        try:
            dt = parser(value)
            if dt.year == 1900:
                today = datetime.now(MADRID_TZ).date()
                dt = datetime.combine(today, dt.time())
            return dt
        except (ValueError, TypeError):
            continue
    return None


def filter_by_hour_window(
    matches: Iterable[Dict[str, object]],
    start_hour: Optional[int],
    end_hour: Optional[int],
    timezone: str = "Europe/Madrid",
) -> List[Dict[str, object]]:
    tz = pytz.timezone(timezone)
    filtered: List[Dict[str, object]] = []
    for match in matches:
        base = match.get("time_obj") or match.get("time")
        match_dt = _parse_time(str(base) if base is not None else None)
        if match_dt is None:
            continue
        if match_dt.tzinfo is None:
            match_dt = tz.localize(match_dt)
        else:
            match_dt = match_dt.astimezone(tz)
        hour = match_dt.hour
        if start_hour is not None and hour < start_hour:
            continue
        if end_hour is not None and hour > end_hour:
            continue
        filtered.append(match)
    return filtered


async def _scrape_matches(limit: int) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    proximos, finalizados = await asyncio.gather(
        get_main_page_matches_async(limit=limit),
        get_main_page_finished_matches_async(limit=limit),
    )
    return list(proximos), list(finalizados)


def run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError as exc:
        if "already running" in str(exc):
            try:
                import nest_asyncio

                nest_asyncio.apply()
            except ModuleNotFoundError as nest_exc:
                raise RuntimeError(
                    "El bucle de eventos ya está en ejecución. "
                    "Instala nest_asyncio (`pip install nest_asyncio`) para usar este script en Colab."
                ) from nest_exc
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro)
        raise


def build_html_overview(
    upcoming: List[Dict[str, object]],
    finished: List[Dict[str, object]],
    max_rows: int = 50,
) -> str:
    def _prepare_df(data: List[Dict[str, object]]) -> pd.DataFrame:
        if not data:
            return pd.DataFrame()
        columns = [
            "time_obj",
            "time",
            "id",
            "home_team",
            "away_team",
            "handicap",
            "goal_line",
            "score",
        ]
        df = pd.DataFrame(data)
        for col in columns:
            if col not in df.columns:
                df[col] = ""
        df = df[columns]
        df["time_obj"] = df["time_obj"].fillna(df["time"])
        return df.head(max_rows)

    upcoming_df = _prepare_df(upcoming)
    finished_df = _prepare_df(finished)

    html_parts = [
        "<html><head><meta charset='utf-8'><title>Resumen de partidos</title>",
        "<style>body{font-family:Arial, sans-serif;} table{border-collapse:collapse;width:100%;margin-bottom:2rem;} "
        "th,td{border:1px solid #ccc;padding:6px;text-align:left;} th{background:#f5f5f5;}</style>",
        "</head><body>",
        "<h1>Resumen de partidos desde datos.json</h1>",
        "<h2>Próximos partidos (primeros {0})</h2>".format(len(upcoming_df)),
    ]
    if not upcoming_df.empty:
        html_parts.append(upcoming_df.to_html(index=False))
    else:
        html_parts.append("<p>No hay partidos próximos en el rango seleccionado.</p>")

    html_parts.append("<h2>Partidos finalizados (primeros {0})</h2>".format(len(finished_df)))
    if not finished_df.empty:
        html_parts.append(finished_df.to_html(index=False))
    else:
        html_parts.append("<p>No hay partidos finalizados en el rango seleccionado.</p>")

    html_parts.append("</body></html>")
    return "\n".join(html_parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera un archivo data.json con los datos de NowGoal listo para usarse en streamlit_app."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Número máximo de partidos a descargar por lista (próximos/finalizados).",
    )
    parser.add_argument(
        "--start-hour",
        type=int,
        default=None,
        help="Hora mínima (0-23) para filtrar partidos por hora local.",
    )
    parser.add_argument(
        "--end-hour",
        type=int,
        default=None,
        help="Hora máxima (0-23) para filtrar partidos por hora local.",
    )
    parser.add_argument(
        "--timezone",
        default="Europe/Madrid",
        help="Zona horaria utilizada para el filtrado por horas (por defecto Europe/Madrid).",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"Ruta del archivo JSON de salida (por defecto {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--html",
        default=None,
        help="Ruta opcional para guardar un resumen HTML con los primeros partidos (útil en Colab).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Descargando datos con límite {args.limit} por lista...")
    proximos, finalizados = run_async(_scrape_matches(args.limit))
    print(f"Total antes de filtrar: {len(proximos)} próximos · {len(finalizados)} finalizados.")

    if args.start_hour is not None or args.end_hour is not None:
        proximos = filter_by_hour_window(proximos, args.start_hour, args.end_hour, args.timezone)
        finalizados = filter_by_hour_window(finalizados, args.start_hour, args.end_hour, args.timezone)
        print(
            "Tras filtrar por horas "
            f"[{args.start_hour if args.start_hour is not None else '-'} - "
            f"{args.end_hour if args.end_hour is not None else '-'}]: "
            f"{len(proximos)} próximos · {len(finalizados)} finalizados."
        )

    dataset = {
        "generated_at": datetime.now(pytz.UTC).isoformat(),
        "upcoming_matches": proximos,
        "finished_matches": finalizados,
    }

    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(dataset, fh, ensure_ascii=False, indent=2)

    print(f"Archivo JSON guardado en: {output_path}")

    if args.html:
        html_path = Path(args.html).expanduser().resolve()
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_content = build_html_overview(proximos, finalizados)
        html_path.write_text(html_content, encoding="utf-8")
        print(f"Resumen HTML generado en: {html_path}")
        print("En Colab puedes visualizarlo con: from IPython.display import HTML; HTML(open(html_path).read())")


if __name__ == "__main__":
    main()
