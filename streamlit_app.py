"""Aplicacion Streamlit que replica la funcionalidad del servidor Flask original."""

from __future__ import annotations

import copy
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from datetime import datetime
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from app_utils import (
    DEFAULT_DATA_JSON,
    filter_upcoming_matches,
    load_data_from_sheets,
    normalize_handicap_to_half_bucket_str,
)
from modules.estudio_scraper import (
    generar_analisis_mercado_simplificado,
    obtener_datos_completos_partido,
    obtener_datos_preview_ligero,
    obtener_datos_preview_rapido,
)
from modules.optimizacion_preview import obtener_datos_preview_ultrarapido


PAGE_SIZE = 10
PREVIEW_MODE_LABELS = {
    "ultra": "Ultra (recomendado)",
    "light": "Ligero",
    "full": "Completo",
}
PAGE_OPTIONS: List[Tuple[str, str]] = [
    ("Proximos partidos", "upcoming"),
    ("Resultados finalizados", "finished"),
]
SUMMARY_BASE_KEYS = {
    "home_name",
    "away_name",
    "home_team",
    "away_team",
    "home_standings",
    "away_standings",
    "rendimiento_local_handicap",
    "rendimiento_visitante_handicap",
    "main_match_odds_data",
    "h2h_data",
    "advanced_analysis_html",
}


st.set_page_config(page_title="Monitor de partidos", layout="wide")


def init_session_state() -> None:
    """Inicializa todos los valores usados en session_state."""
    defaults = {
        "visible_counts": {"upcoming": PAGE_SIZE, "finished": PAGE_SIZE},
        "handicap_filter": "",
        "handicap_input": "",
        "analysis_per_match": {},
        "preview_per_match": {},
        "manual_results": None,
        "manual_preview": None,
        "current_mode": "upcoming",
        "preview_mode": "ultra",
        "include_performance": True,
        "manual_match_id": "",
        "data_json_path": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            if isinstance(value, (dict, list)):
                st.session_state[key] = copy.deepcopy(value)
            else:
                st.session_state[key] = value


@st.cache_data(ttl=300)
def cached_load_data(data_path: Optional[str]) -> Dict[str, Any]:
    """Carga datos desde el archivo JSON local aplicando una capa de caché."""
    try:
        return load_data_from_sheets(data_path=data_path)
    except Exception as exc:  # pragma: no cover - defensivo
        return {"upcoming_matches": [], "finished_matches": [], "error": str(exc)}


@st.cache_data(ttl=3600)
def cached_get_full_analysis(match_id: str) -> Dict[str, Any]:
    """Obtiene el estudio completo de un partido con cache."""
    try:
        return obtener_datos_completos_partido(match_id)
    except Exception as exc:  # pragma: no cover - defensivo
        return {"error": str(exc)}


@st.cache_data(ttl=900)
def cached_get_preview(match_id: str, mode: str) -> Dict[str, Any]:
    """Obtiene la vista previa de un partido usando el modo deseado."""
    try:
        start = time.perf_counter()
        if mode == "full":
            data = obtener_datos_preview_rapido(match_id)
        elif mode == "light":
            data = obtener_datos_preview_ligero(match_id)
        else:
            data = obtener_datos_preview_ultrarapido(match_id)
        duration = round(time.perf_counter() - start, 3)
        if isinstance(data, dict):
            payload = copy.deepcopy(data)
            performance = payload.get("performance") or {}
            if not isinstance(performance, dict):
                performance = {}
            performance.update(
                {"tiempo_total_segundos": duration, "modo": mode}
            )
            payload["performance"] = performance
            return payload
        return {"error": "Estructura inesperada en la vista previa."}
    except Exception as exc:  # pragma: no cover - defensivo
        return {"error": str(exc)}


def format_match_time(match: Dict[str, Any]) -> str:
    """Convierte la información de tiempo de un partido en una cadena legible."""
    raw_time = match.get("time_obj") or match.get("time")
    if raw_time in (None, "", "nan"):
        return "-"
    if isinstance(raw_time, str):
        try:
            dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            return dt.strftime("%d/%m %H:%M")
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M", "%d/%m %H:%M", "%H:%M"):
            try:
                dt = datetime.strptime(raw_time, fmt)
                if fmt == "%H:%M":
                    today = datetime.now().date()
                    dt = datetime.combine(today, dt.time())
                return dt.strftime("%d/%m %H:%M")
            except ValueError:
                continue
        return raw_time
    try:
        ts = pd.to_datetime(raw_time)
        if pd.isna(ts):
            return "-"
        return ts.strftime("%Y-%m-%d %H:%M")
    except Exception:  # pragma: no cover - defensivo
        return str(raw_time)


def safe_str(value: Any, default: str = "-") -> str:
    """Convierte valores potencialmente NaN en texto amigable."""
    if value is None:
        return default
    if isinstance(value, str):
        txt = value.strip()
        return txt or default
    try:
        if pd.isna(value):
            return default
    except Exception:  # pragma: no cover - defensivo
        return str(value)
    return str(value)


def collect_handicap_options(matches: Iterable[Dict[str, Any]]) -> List[str]:
    """Obtiene una lista ordenada de handicaps disponibles."""
    options = set()
    for match in matches:
        target = normalize_handicap_to_half_bucket_str(match.get("handicap"))
        if target is not None:
            options.add(target)

    def sort_key(value: str) -> Tuple[int, float, str]:
        try:
            return (0, float(value), value)
        except (TypeError, ValueError):
            return (1, float("inf"), value)

    return sorted(options, key=sort_key)


def apply_handicap_filter(
    matches: List[Dict[str, Any]],
    raw_filter: str,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Aplica el filtro de handicap devolviendo posibles errores."""
    if not raw_filter:
        return matches, None

    normalized = normalize_handicap_to_half_bucket_str(raw_filter)
    if normalized is None:
        return matches, f"No se reconoce el handicap '{raw_filter}'."

    filtered = [
        match
        for match in matches
        if normalize_handicap_to_half_bucket_str(match.get("handicap")) == normalized
    ]
    return filtered, None


def get_match_label(match: Dict[str, Any]) -> str:
    """Devuelve un texto Local vs Visitante para la fila de la tabla."""
    home = match.get("home_team") or match.get("home_name") or "Local"
    away = match.get("away_team") or match.get("away_name") or "Visitante"
    return f"{home} vs {away}"


def build_label_from_payload(payload: Dict[str, Any], fallback: str) -> str:
    """Determina el nombre del partido a partir de un payload de datos."""
    home = payload.get("home_team") or payload.get("home_name")
    away = payload.get("away_team") or payload.get("away_name")
    if home and away:
        return f"{home} vs {away}"
    return fallback


def render_preview_section(
    match_id: str,
    match_label: str,
    record: Dict[str, Any],
    include_performance: bool,
) -> None:
    """Muestra el bloque de vista previa."""
    data = record.get("data") if isinstance(record, dict) else None
    mode = record.get("mode") if isinstance(record, dict) else "ultra"
    header = f"Vista previa ({PREVIEW_MODE_LABELS.get(mode, mode)}): {match_label}"
    with st.expander(header, expanded=False):
        if not isinstance(data, dict):
            st.info("No hay datos disponibles para la vista previa.")
            return
        if data.get("error"):
            st.error(data["error"])
            return
        resumen_tab, raw_tab = st.tabs(["Resumen", "JSON"])
        with resumen_tab:
            _render_preview_summary(data, include_performance)
        with raw_tab:
            st.json(data)


def render_full_analysis(
    match_id: str,
    match_label: str,
    data: Dict[str, Any],
) -> None:
    """Muestra el bloque de estudio completo del partido."""
    header = f"Estudio completo: {match_label}"
    with st.expander(header, expanded=False):
        if not isinstance(data, dict):
            st.info("No hay datos disponibles para el estudio completo.")
            return
        if data.get("error"):
            st.error(data["error"])
            return
        resumen_tab, mercado_tab, avanzado_tab, raw_tab = st.tabs(
            ["Resumen", "Mercado", "Analisis avanzado", "JSON"]
        )
        with resumen_tab:
            _render_analysis_summary(data)
        with mercado_tab:
            _render_market_summary(data, match_label)
        with avanzado_tab:
            _render_advanced_sections(data)
        with raw_tab:
            st.json(data)


def _render_preview_summary(data: Dict[str, Any], include_performance: bool) -> None:
    """Dibuja un resumen amigable de la vista previa."""
    home = data.get("home_team") or data.get("home_name") or "Local"
    away = data.get("away_team") or data.get("away_name") or "Visitante"
    blocks_rendered = False

    if include_performance and isinstance(data.get("performance"), dict):
        perf = data["performance"]
        tiempo = perf.get("tiempo_total_segundos", "?")
        modo = perf.get("modo", "?")
        st.caption(f"Tiempo total: {tiempo}s | modo: {modo}")
        blocks_rendered = True

    if isinstance(data.get("recent_form"), dict):
        form = data["recent_form"]
        home_form = form.get("home", {})
        away_form = form.get("away", {})
        st.subheader("Rendimiento reciente (V-E-D)")
        form_df = pd.DataFrame(
            [
                {
                    "Equipo": home,
                    "V": home_form.get("wins"),
                    "E": home_form.get("draws"),
                    "D": home_form.get("losses"),
                },
                {
                    "Equipo": away,
                    "V": away_form.get("wins"),
                    "E": away_form.get("draws"),
                    "D": away_form.get("losses"),
                },
            ]
        )
        st.table(form_df)
        blocks_rendered = True

    if isinstance(data.get("h2h_stats"), dict):
        h2h = data["h2h_stats"]
        st.subheader("H2H directo")
        h2h_df = pd.DataFrame(
            [
                {"Equipo": home, "Victorias": h2h.get("home_wins")},
                {"Equipo": "Empates", "Victorias": h2h.get("draws")},
                {"Equipo": away, "Victorias": h2h.get("away_wins")},
            ]
        )
        st.table(h2h_df)
        blocks_rendered = True

    if isinstance(data.get("h2h_indirect"), dict):
        indirect = data["h2h_indirect"]
        st.subheader("H2H indirecto (rival comun)")
        indirect_df = pd.DataFrame(
            [
                {"Equipo": home, "Mejor": indirect.get("home_better")},
                {"Equipo": "Empates", "Mejor": indirect.get("draws")},
                {"Equipo": away, "Mejor": indirect.get("away_better")},
            ]
        )
        st.table(indirect_df)
        blocks_rendered = True

    if not blocks_rendered:
        st.info("No hay resumen estructurado disponible para esta vista previa.")


def _render_analysis_summary(data: Dict[str, Any]) -> None:
    """Dibuja la informacion principal del estudio completo."""
    home = data.get("home_name") or data.get("home_team") or "Local"
    away = data.get("away_name") or data.get("away_team") or "Visitante"
    summary_rendered = False

    col_home, col_away = st.columns(2)
    home_stats = data.get("home_standings")
    away_stats = data.get("away_standings")

    if isinstance(home_stats, dict):
        summary_rendered = True
        col_home.metric("Posicion", home_stats.get("ranking", "N/D"))
        if home_stats.get("points") is not None:
            col_home.caption(f"Puntos: {home_stats.get('points')}")
    else:
        col_home.write(home)

    if isinstance(away_stats, dict):
        summary_rendered = True
        col_away.metric("Posicion", away_stats.get("ranking", "N/D"))
        if away_stats.get("points") is not None:
            col_away.caption(f"Puntos: {away_stats.get('points')}")
    else:
        col_away.write(away)

    if isinstance(data.get("rendimiento_local_handicap"), list):
        summary_rendered = True
        col_home.write(
            "Serie handicap: "
            + ", ".join(map(str, data["rendimiento_local_handicap"]))
        )

    if isinstance(data.get("rendimiento_visitante_handicap"), list):
        summary_rendered = True
        col_away.write(
            "Serie handicap: "
            + ", ".join(map(str, data["rendimiento_visitante_handicap"]))
        )

    if isinstance(data.get("h2h_data"), dict):
        summary_rendered = True
        st.subheader("Historial H2H detallado")
        st.json(data["h2h_data"])

    if not summary_rendered:
        st.info("No hay resumen estructurado disponible para este estudio.")


def _render_market_summary(data: Dict[str, Any], match_label: str) -> None:
    """Muestra el analisis de mercado simplificado si esta disponible."""
    main_odds = data.get("main_match_odds_data")
    h2h_data = data.get("h2h_data")
    home = data.get("home_name") or data.get("home_team")
    away = data.get("away_name") or data.get("away_team")

    if all([main_odds, h2h_data, home, away]):
        try:
            html = generar_analisis_mercado_simplificado(main_odds, h2h_data, home, away)
            components.html(html, height=420, scrolling=True)
        except Exception as exc:  # pragma: no cover - defensivo
            st.warning(f"No se pudo generar el analisis de mercado: {exc}")
    else:
        st.info("Analisis de mercado no disponible para este partido.")


def _render_advanced_sections(data: Dict[str, Any]) -> None:
    """Despliega los bloques avanzados del estudio completo."""
    html_block = data.get("advanced_analysis_html")
    if html_block:
        components.html(html_block, height=500, scrolling=True)

    special_keys = [
        "comparacion_lineas_local",
        "comparacion_lineas_visitante",
        "rivales_comunes",
        "comp_L_vs_UV_A",
        "comp_V_vs_UL_H",
        "h2h_col3",
        "h2h_stadium",
        "h2h_general",
        "last_home_match",
        "last_away_match",
    ]

    for key in special_keys:
        if key in data:
            st.subheader(key.replace("_", " ").title())
            st.json(data[key])

    remaining_keys = [
        key
        for key in data.keys()
        if key not in SUMMARY_BASE_KEYS
        and key not in special_keys
        and isinstance(data[key], (dict, list))
    ]

    if remaining_keys:
        st.subheader("Bloques adicionales")
        for key in remaining_keys:
            st.markdown(f"- `{key}`")
        st.caption("Revisa la pestaña JSON para ver el detalle completo.")


def render_match_row(
    match: Dict[str, Any],
    page_mode: str,
    preview_mode: str,
    include_performance: bool,
) -> None:
    """Pinta la fila de un partido con sus acciones asociadas."""
    match_id = safe_str(match.get("id") or match.get("match_id"), "").strip()
    match_label = get_match_label(match)
    score_text = safe_str(match.get("score"), "-") if page_mode == "finished" else "-"
    handicap_text = safe_str(match.get("handicap"), "-")
    goal_line_text = safe_str(match.get("goal_line"), "-")

    container = st.container()
    with container:
        cols = st.columns([1.2, 3.2, 1.2, 1.0, 1.0, 1.2, 1.2])
        cols[0].markdown(f"**{format_match_time(match)}**")
        if match_id:
            cols[1].markdown(f"{match_label}\n\n`{match_id}`")
        else:
            cols[1].markdown(match_label)
        cols[2].markdown(score_text)
        cols[3].markdown(handicap_text)
        cols[4].markdown(goal_line_text)

        analysis_store = dict(st.session_state.get("analysis_per_match", {}))
        preview_store = dict(st.session_state.get("preview_per_match", {}))

        if match_id:
            if cols[5].button("Estudio", key=f"study_{page_mode}_{match_id}"):
                with st.spinner(f"Cargando estudio completo para {match_id}..."):
                    analysis_data = cached_get_full_analysis(match_id)
                analysis_store[match_id] = analysis_data
                st.session_state["analysis_per_match"] = analysis_store
            if cols[6].button(
                f"Vista {PREVIEW_MODE_LABELS.get(preview_mode, preview_mode)}",
                key=f"preview_{page_mode}_{match_id}",
            ):
                with st.spinner(f"Cargando vista previa ({preview_mode}) para {match_id}..."):
                    preview_data = cached_get_preview(match_id, preview_mode)
                preview_store[match_id] = {"mode": preview_mode, "data": preview_data}
                st.session_state["preview_per_match"] = preview_store
        else:
            cols[5].info("Sin ID")
            cols[6].empty()

        analysis_data = analysis_store.get(match_id) if match_id else None
        preview_data = preview_store.get(match_id) if match_id else None

        if analysis_data:
            render_full_analysis(match_id, match_label, analysis_data)
        if preview_data:
            render_preview_section(
                match_id,
                match_label,
                preview_data,
                include_performance,
            )

    st.divider()


def main() -> None:
    """Punto de entrada principal de la aplicacion."""
    init_session_state()

    st.sidebar.divider()
    st.sidebar.header("Fuente de datos")
    st.sidebar.caption(
        "La app utiliza `data.json` (puedes sobrescribir la ruta abajo). "
        "Pulsa recargar tras cambiarla."
    )
    data_path_input = st.sidebar.text_input(
        "Ruta personalizada de data.json",
        value=st.session_state.get("data_json_path", ""),
        placeholder="Ej: C:/ruta/mi_datos.json",
    )
    recargar = st.sidebar.button("Recargar data.json", key="reload_data_btn")
    if recargar or data_path_input != st.session_state.get("data_json_path", ""):
        st.session_state["data_json_path"] = data_path_input.strip()
        cached_load_data.clear()
        st.experimental_rerun()

    with st.spinner("Cargando datos desde data.json..."):
        all_data = cached_load_data(st.session_state.get("data_json_path") or None)

    if all_data.get("error"):
        st.error(f"No se pudieron cargar los datos desde data.json: {all_data.get('error')}")
        st.stop()

    data_source = all_data.get("source_path") or (
        st.session_state.get("data_json_path") or str(DEFAULT_DATA_JSON)
    )

    label_to_mode = {label: mode for label, mode in PAGE_OPTIONS}
    current_index = (
        0 if st.session_state.get("current_mode") == "upcoming" else 1
    )
    selected_label = st.sidebar.radio(
        "Selecciona la vista",
        [label for label, _ in PAGE_OPTIONS],
        index=current_index,
    )
    page_mode = label_to_mode[selected_label]
    if page_mode != st.session_state.get("current_mode"):
        st.session_state["current_mode"] = page_mode
        st.session_state["visible_counts"][page_mode] = PAGE_SIZE

    if page_mode == "upcoming":
        matches_base = all_data.get("upcoming_matches", [])
        matches_base = filter_upcoming_matches(matches_base)
        page_title = "Proximos partidos"
    else:
        matches_base = all_data.get("finished_matches", [])
        page_title = "Resultados finalizados"

    matches_base = [m for m in matches_base if isinstance(m, dict)]
    handicap_options = collect_handicap_options(matches_base)

    st.sidebar.divider()
    st.sidebar.header("Filtros")
    st.sidebar.text_input(
        "Filtrar por handicap",
        key="handicap_input",
        placeholder="Ej: 0, 0.25, -0.5",
    )
    if st.sidebar.button("Aplicar filtro", key="apply_handicap_btn"):
        st.session_state["handicap_filter"] = st.session_state["handicap_input"].strip()
        st.session_state["visible_counts"][page_mode] = PAGE_SIZE
    if st.sidebar.button("Quitar filtro", key="clear_handicap_btn"):
        st.session_state["handicap_filter"] = ""
        st.session_state["handicap_input"] = ""
        st.session_state["visible_counts"][page_mode] = PAGE_SIZE

    if handicap_options:
        st.sidebar.caption(
            "Handicaps disponibles: " + ", ".join(handicap_options)
        )

    st.sidebar.divider()
    st.sidebar.header("Vista previa")
    preview_mode = st.sidebar.selectbox(
        "Modo de vista previa",
        list(PREVIEW_MODE_LABELS.keys()),
        format_func=lambda mode: PREVIEW_MODE_LABELS[mode],
        key="preview_mode",
    )
    include_performance = st.sidebar.checkbox(
        "Incluir informacion de rendimiento",
        key="include_performance",
        value=st.session_state.get("include_performance", True),
    )

    st.sidebar.divider()
    st.sidebar.header("Analisis manual")
    st.sidebar.text_input(
        "ID de partido",
        key="manual_match_id",
        placeholder="Ej: 123456",
    )
    if st.sidebar.button("Ejecutar estudio completo", key="manual_full_btn"):
        match_id = st.session_state["manual_match_id"].strip()
        if match_id:
            with st.spinner(f"Cargando estudio completo para {match_id}..."):
                data = cached_get_full_analysis(match_id)
            st.session_state["manual_results"] = {
                "match_id": match_id,
                "data": data,
            }
        else:
            st.sidebar.warning("Introduce un ID valido.")
    if st.sidebar.button("Vista previa rapida", key="manual_preview_btn"):
        match_id = st.session_state["manual_match_id"].strip()
        if match_id:
            with st.spinner(f"Cargando vista previa ({preview_mode}) para {match_id}..."):
                data = cached_get_preview(match_id, preview_mode)
            st.session_state["manual_preview"] = {
                "match_id": match_id,
                "mode": preview_mode,
                "data": data,
            }
        else:
            st.sidebar.warning("Introduce un ID valido.")
    if st.sidebar.button("Limpiar panel manual", key="manual_clear_btn"):
        st.session_state["manual_results"] = None
        st.session_state["manual_preview"] = None

    matches_filtered, filter_error = apply_handicap_filter(
        matches_base,
        st.session_state.get("handicap_filter", ""),
    )

    visible_count = st.session_state["visible_counts"].get(page_mode, PAGE_SIZE)
    visible_matches = matches_filtered[:visible_count]

    st.title(page_title)
    st.caption(
        f"Fuente: `{data_source}` · {len(matches_filtered)} partidos (total sin filtro: {len(matches_base)}). "
        f"Mostrando {len(visible_matches)}."
    )

    manual_result = st.session_state.get("manual_results")
    if isinstance(manual_result, dict):
        match_id = manual_result.get("match_id", "")
        data = manual_result.get("data") or {}
        label = build_label_from_payload(data, match_id)
        render_full_analysis(match_id, label, data)

    manual_preview = st.session_state.get("manual_preview")
    if isinstance(manual_preview, dict):
        match_id = manual_preview.get("match_id", "")
        data = manual_preview.get("data") or {}
        label = build_label_from_payload(data, match_id)
        render_preview_section(
            match_id,
            label,
            {
                "mode": manual_preview.get("mode", "ultra"),
                "data": data,
            },
            include_performance,
        )

    if filter_error:
        st.warning(filter_error)

    if not visible_matches:
        st.info("No hay partidos para los criterios actuales.")
    else:
        for match in visible_matches:
            render_match_row(match, page_mode, preview_mode, include_performance)

        if len(matches_filtered) > visible_count:
            if st.button("Cargar mas partidos", key=f"load_more_{page_mode}"):
                st.session_state["visible_counts"][page_mode] = visible_count + PAGE_SIZE
                st.experimental_rerun()


if __name__ == "__main__":
    main()
