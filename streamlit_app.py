# Streamlit front-end for upcoming match insights backed by local JSON
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import streamlit as st
from zoneinfo import ZoneInfo

from muestra_sin_fallos.modules.estudio_scraper import (
    check_handicap_cover,
    format_ah_as_decimal_string_of,
    generar_analisis_mercado_simplificado,
    obtener_datos_completos_partido,
    obtener_datos_preview_ligero,
    parse_ah_to_number_of,
)

DATA_FILE_CANDIDATES: Tuple[Path, ...] = (
    Path(__file__).resolve().parent / "data.json",
    Path(__file__).resolve().parent / "muestra_sin_fallos" / "data.json",
)
MADRID_TZ = ZoneInfo("Europe/Madrid")


@dataclass
class MatchEntry:
    match_id: str
    home_team: str
    away_team: str
    handicap: str
    goal_line: str
    kickoff_madrid: Optional[datetime]
    kickoff_display: str

    @property
    def handicap_bucket(self) -> str:
        normalized = format_ah_as_decimal_string_of(self.handicap)
        return normalized if normalized not in {"-", "?"} else "Sin dato"


def _resolve_data_path() -> Path:
    for candidate in DATA_FILE_CANDIDATES:
        if candidate.exists():
            return candidate
    return DATA_FILE_CANDIDATES[0]


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        # Treat numbers as unix timestamps (seconds)
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
        return dt
    elif isinstance(value, str):
        for fmt in (
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
        ):
            try:
                dt = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
        else:
            try:
                dt = datetime.fromisoformat(value)
            except ValueError:
                return None
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def _ensure_kickoff_display(kickoff: Optional[datetime], fallback_time: str) -> str:
    if kickoff:
        return kickoff.astimezone(MADRID_TZ).strftime("%d/%m %H:%M")
    if fallback_time:
        return fallback_time
    return "Sin hora"


@st.cache_data(ttl=120, show_spinner=False)
def load_matches_from_json() -> List[MatchEntry]:
    path = _resolve_data_path()
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []

    matches: List[MatchEntry] = []
    raw_matches = payload.get("upcoming_matches", [])

    for item in raw_matches:
        if not isinstance(item, dict):
            continue
        match_id = str(item.get("id") or "").strip()
        if not match_id:
            continue
        kickoff_utc = _parse_datetime(item.get("time_obj"))
        kickoff_local = kickoff_utc.astimezone(MADRID_TZ) if kickoff_utc else None
        display_time = _ensure_kickoff_display(kickoff_local, str(item.get("time") or ""))
        matches.append(
            MatchEntry(
                match_id=match_id,
                home_team=str(item.get("home_team") or "Desconocido"),
                away_team=str(item.get("away_team") or "Desconocido"),
                handicap=str(item.get("handicap") or ""),
                goal_line=str(item.get("goal_line") or ""),
                kickoff_madrid=kickoff_local,
                kickoff_display=display_time,
            )
        )
    return matches


def filter_matches(
    matches: Iterable[MatchEntry],
    handicap_values: Iterable[str],
    search_text: str,
    hide_past: bool = True,
) -> List[MatchEntry]:
    handicap_set = {val.lower() for val in handicap_values}
    now_madrid = datetime.now(MADRID_TZ)
    text = search_text.strip().lower()

    filtered: List[MatchEntry] = []
    for match in matches:
        if hide_past and match.kickoff_madrid and match.kickoff_madrid < now_madrid:
            continue
        if handicap_set and "todos" not in handicap_set:
            if match.handicap_bucket.lower() not in handicap_set:
                continue
        if text and text not in match.home_team.lower() and text not in match.away_team.lower():
            continue
        filtered.append(match)

    def _sort_key(entry: MatchEntry) -> Tuple[datetime, str]:
        sort_dt = entry.kickoff_madrid or datetime.max.replace(tzinfo=MADRID_TZ)
        return sort_dt, entry.match_id

    filtered.sort(key=_sort_key)
    return filtered


@st.cache_data(ttl=900)
def fetch_preview_data(match_id: str) -> Dict[str, Any]:
    return obtener_datos_preview_ligero(match_id)


def df_to_rows(df: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if df is None or not hasattr(df, "iterrows"):
        return rows
    try:
        for idx, row in df.iterrows():
            label = str(idx)
            label = (
                label.replace("Shots on Goal", "Tiros a Puerta")
                .replace("Shots", "Tiros")
                .replace("Dangerous Attacks", "Ataques Peligrosos")
                .replace("Attacks", "Ataques")
            )
            home_val = row.get("Casa", "")
            away_val = row.get("Fuera", "")
            rows.append({"label": label, "home": home_val or "", "away": away_val or ""})
    except Exception:
        return rows
    return rows


def _build_cover_status_helper(ah_actual_num: Optional[float], home_name: str, favorito: str):
    favorito_actual_name = "Ninguno (línea en 0)"
    if ah_actual_num is not None:
        if ah_actual_num > 0:
            favorito_actual_name = home_name
        elif ah_actual_num < 0:
            favorito_actual_name = favorito
    return favorito_actual_name


def build_full_analysis_payload(match_id: str, datos: Dict[str, Any]) -> Dict[str, Any]:
    if not datos or (isinstance(datos, dict) and datos.get("error")):
        return {"error": (datos or {}).get("error", "No se pudieron obtener datos.")}

    payload: Dict[str, Any] = {
        "match_id": match_id,
        "home_team": datos.get("home_name", ""),
        "away_team": datos.get("away_name", ""),
        "final_score": datos.get("score"),
        "match_date": datos.get("match_date"),
        "match_time": datos.get("match_time"),
        "match_datetime": datos.get("match_datetime"),
        "recent_indirect_full": {"last_home": None, "last_away": None, "h2h_col3": None, "h2h_general": None},
        "comparativas_indirectas": {"left": None, "right": None},
        "simplified_html": "",
    }

    main_odds = datos.get("main_match_odds_data", {})
    home_name = payload["home_team"]
    away_name = payload["away_team"]
    ah_actual_num = parse_ah_to_number_of(main_odds.get("ah_linea_raw", ""))
    favorito_actual_name = _build_cover_status_helper(ah_actual_num, home_name, away_name)

    def get_cover_status_vs_current(details: Optional[Dict[str, Any]]) -> str:
        if not details or ah_actual_num is None:
            return "NEUTRO"
        try:
            score_str = (details.get("score") or "").replace(" ", "").replace(":", "-")
            if not score_str or "?" in score_str:
                return "NEUTRO"
            status, _ = check_handicap_cover(
                score_str,
                ah_actual_num,
                favorito_actual_name,
                details.get("home_team"),
                details.get("away_team"),
                home_name,
            )
            return status
        except Exception:
            return "NEUTRO"

    def analyze_h2h_rivals(home_result: Optional[Dict[str, Any]], away_result: Optional[Dict[str, Any]]) -> Optional[str]:
        if not home_result or not away_result:
            return None
        try:
            home_goals = list(map(int, (home_result.get("score") or "0-0").split("-")))
            away_goals = list(map(int, (away_result.get("score") or "0-0").split("-")))
            home_diff = home_goals[0] - home_goals[1]
            away_diff = away_goals[0] - away_goals[1]
            if home_diff > away_diff:
                return "Contra rivales comunes, el Equipo Local ha obtenido mejores resultados"
            if away_diff > home_diff:
                return "Contra rivales comunes, el Equipo Visitante ha obtenido mejores resultados"
            return "Los rivales han tenido resultados similares"
        except Exception:
            return None

    def analyze_indirect_comparison(result: Optional[Dict[str, Any]], team_name: str) -> Optional[str]:
        if not result:
            return None
        try:
            status = get_cover_status_vs_current(result)
            if status == "CUBIERTO":
                return f"Contra este rival, {team_name} habría cubierto el handicap"
            if status == "NO CUBIERTO":
                return f"Contra este rival, {team_name} no habría cubierto el handicap"
            return f"Contra este rival, el resultado para {team_name} sería indeterminado"
        except Exception:
            return None

    last_home = (datos.get("last_home_match") or {})
    last_home_details = last_home.get("details") or {}
    if last_home_details:
        payload["recent_indirect_full"]["last_home"] = {
            "home": last_home_details.get("home_team"),
            "away": last_home_details.get("away_team"),
            "score": (last_home_details.get("score") or "").replace(":", " : "),
            "ah": format_ah_as_decimal_string_of(last_home_details.get("handicap_line_raw")),
            "ou": last_home_details.get("ouLine") or "-",
            "stats_rows": df_to_rows(last_home.get("stats")),
            "date": last_home_details.get("date"),
            "cover_status": get_cover_status_vs_current(last_home_details),
        }

    last_away = (datos.get("last_away_match") or {})
    last_away_details = last_away.get("details") or {}
    if last_away_details:
        payload["recent_indirect_full"]["last_away"] = {
            "home": last_away_details.get("home_team"),
            "away": last_away_details.get("away_team"),
            "score": (last_away_details.get("score") or "").replace(":", " : "),
            "ah": format_ah_as_decimal_string_of(last_away_details.get("handicap_line_raw")),
            "ou": last_away_details.get("ouLine") or "-",
            "stats_rows": df_to_rows(last_away.get("stats")),
            "date": last_away_details.get("date"),
            "cover_status": get_cover_status_vs_current(last_away_details),
        }

    h2h_col3 = (datos.get("h2h_col3") or {})
    h2h_col3_details = h2h_col3.get("details") or {}
    if h2h_col3_details and h2h_col3_details.get("status") == "found":
        adapted = {
            "score": f"{h2h_col3_details.get('goles_home')}:{h2h_col3_details.get('goles_away')}",
            "home_team": h2h_col3_details.get("h2h_home_team_name"),
            "away_team": h2h_col3_details.get("h2h_away_team_name"),
        }
        payload["recent_indirect_full"]["h2h_col3"] = {
            "home": h2h_col3_details.get("h2h_home_team_name"),
            "away": h2h_col3_details.get("h2h_away_team_name"),
            "score": f"{h2h_col3_details.get('goles_home')} : {h2h_col3_details.get('goles_away')}",
            "ah": format_ah_as_decimal_string_of(h2h_col3_details.get("handicap_line_raw")),
            "ou": h2h_col3_details.get("ou_result") or "-",
            "stats_rows": df_to_rows(h2h_col3.get("stats")),
            "date": h2h_col3_details.get("date"),
            "cover_status": get_cover_status_vs_current(adapted),
            "analysis": analyze_h2h_rivals(last_home_details, last_away_details),
        }

    h2h_general = (datos.get("h2h_general") or {})
    h2h_general_details = h2h_general.get("details") or {}
    if h2h_general_details:
        score_text = h2h_general_details.get("res6") or ""
        cover_input = {
            "score": score_text,
            "home_team": h2h_general_details.get("h2h_gen_home"),
            "away_team": h2h_general_details.get("h2h_gen_away"),
        }
        payload["recent_indirect_full"]["h2h_general"] = {
            "home": h2h_general_details.get("h2h_gen_home"),
            "away": h2h_general_details.get("h2h_gen_away"),
            "score": score_text.replace(":", " : "),
            "ah": h2h_general_details.get("ah6") or "-",
            "ou": h2h_general_details.get("ou_result6") or "-",
            "stats_rows": df_to_rows(h2h_general.get("stats")),
            "date": h2h_general_details.get("date"),
            "cover_status": get_cover_status_vs_current(cover_input) if score_text else "NEUTRO",
        }

    comp_left = (datos.get("comp_L_vs_UV_A") or {})
    comp_left_details = comp_left.get("details") or {}
    if comp_left_details:
        payload["comparativas_indirectas"]["left"] = {
            "title_home_name": payload["home_team"],
            "title_away_name": payload["away_team"],
            "home_team": comp_left_details.get("home_team"),
            "away_team": comp_left_details.get("away_team"),
            "score": (comp_left_details.get("score") or "").replace(":", " : "),
            "ah": format_ah_as_decimal_string_of(comp_left_details.get("ah_line")),
            "ou": comp_left_details.get("ou_line") or "-",
            "localia": comp_left_details.get("localia") or "",
            "stats_rows": df_to_rows(comp_left.get("stats")),
            "cover_status": get_cover_status_vs_current(comp_left_details),
            "analysis": analyze_indirect_comparison(comp_left_details, payload["home_team"]),
        }

    comp_right = (datos.get("comp_V_vs_UL_H") or {})
    comp_right_details = comp_right.get("details") or {}
    if comp_right_details:
        payload["comparativas_indirectas"]["right"] = {
            "title_home_name": payload["home_team"],
            "title_away_name": payload["away_team"],
            "home_team": comp_right_details.get("home_team"),
            "away_team": comp_right_details.get("away_team"),
            "score": (comp_right_details.get("score") or "").replace(":", " : "),
            "ah": format_ah_as_decimal_string_of(comp_right_details.get("ah_line")),
            "ou": comp_right_details.get("ou_line") or "-",
            "localia": comp_right_details.get("localia") or "",
            "stats_rows": df_to_rows(comp_right.get("stats")),
            "cover_status": get_cover_status_vs_current(comp_right_details),
            "analysis": analyze_indirect_comparison(comp_right_details, payload["away_team"]),
        }

    h2h_data = datos.get("h2h_data")
    if all([main_odds, h2h_data, home_name, away_name]):
        payload["simplified_html"] = generar_analisis_mercado_simplificado(main_odds, h2h_data, home_name, away_name)

    return payload


@st.cache_data(ttl=1800)
def fetch_full_analysis(match_id: str) -> Dict[str, Any]:
    datos = obtener_datos_completos_partido(match_id)
    return build_full_analysis_payload(match_id, datos)


def render_recent_indirect(reference: Dict[str, Any], title: str) -> None:
    if not reference:
        return
    with st.container(border=True):
        st.markdown(f"**{title}**")
        score = reference.get("score", "-")
        st.markdown(f"{reference.get('home', '')} vs {reference.get('away', '')} — **{score}**")
        meta = []
        if reference.get("date"):
            meta.append(f"Fecha: {reference['date']}")
        if reference.get("ah"):
            meta.append(f"AH: {reference['ah']}")
        if reference.get("cover_status"):
            meta.append(f"Cobertura: {reference['cover_status']}")
        if meta:
            st.caption(" | ".join(meta))
        if reference.get("analysis"):
            st.info(reference["analysis"])
        stats = reference.get("stats_rows") or []
        if stats:
            st.table(pd.DataFrame(stats))


def render_preview_section(preview: Dict[str, Any]) -> None:
    if not preview:
        st.warning("Sin datos para la vista previa seleccionada.")
        return
    if preview.get("error"):
        st.error(preview["error"])
        return

    st.subheader("Vista previa rápida")
    st.markdown(f"**{preview.get('home_team', '')}** vs **{preview.get('away_team', '')}**")

    handicap = preview.get("handicap", {})
    col1, col2, col3 = st.columns(3)
    col1.metric("Línea AH", handicap.get("ah_line", "-"))
    col2.metric("Favorito", handicap.get("favorite") or "Sin favorito")
    col3.metric("Cobertura último H2H", handicap.get("cover_on_last_h2h", "-"))

    with st.expander("Rendimiento reciente"):
        recent_form = preview.get("recent_form", {})
        st.markdown("**Local (últimos 8)**")
        st.json(recent_form.get("home") or {})
        st.markdown("**Visitante (últimos 8)**")
        st.json(recent_form.get("away") or {})

    recent_indirect = preview.get("recent_indirect", {})
    if any(recent_indirect.values()):
        st.markdown("### Rivales recientes")
        if recent_indirect.get("last_home"):
            render_recent_indirect(recent_indirect["last_home"], "Último del local")
        if recent_indirect.get("last_away"):
            render_recent_indirect(recent_indirect["last_away"], "Último del visitante")
        if recent_indirect.get("h2h_col3"):
            render_recent_indirect(recent_indirect["h2h_col3"], "Rivales comunes")

    with st.expander("Estadísticas adicionales"):
        st.markdown("**Ataques peligrosos**")
        st.json(preview.get("dangerous_attacks") or {})
        st.markdown("**H2H indirecto**")
        st.json(preview.get("h2h_indirect") or {})
        st.markdown("**H2H directo (conteo)**")
        st.json(preview.get("h2h_stats") or {})


def render_analysis_section(payload: Dict[str, Any]) -> None:
    if not payload:
        st.warning("Sin datos de análisis disponibles.")
        return
    if payload.get("error"):
        st.error(payload["error"])
        return

    st.subheader("Estudio completo")
    st.markdown(f"**{payload.get('home_team', '')}** vs **{payload.get('away_team', '')}**")

    meta_caption = []
    if payload.get("match_date"):
        meta_caption.append(f"Fecha: {payload['match_date']}")
    if payload.get("match_time"):
        meta_caption.append(f"Hora: {payload['match_time']}")
    if meta_caption:
        st.caption(" | ".join(meta_caption))

    if payload.get("simplified_html"):
        st.markdown(payload["simplified_html"], unsafe_allow_html=True)

    st.markdown("### Rendimiento reciente")
    ri = payload.get("recent_indirect_full", {})
    render_recent_indirect(ri.get("last_home"), "Último partido local")
    render_recent_indirect(ri.get("last_away"), "Último partido visitante")
    render_recent_indirect(ri.get("h2h_col3"), "Rivales comunes (columna 3)")
    render_recent_indirect(ri.get("h2h_general"), "H2H general en el estadio")

    comparativas = payload.get("comparativas_indirectas", {})
    if comparativas.get("left") or comparativas.get("right"):
        st.markdown("### Comparativas indirectas")
        if comparativas.get("left"):
            render_recent_indirect(comparativas["left"], "Local vs rival del visitante")
        if comparativas.get("right"):
            render_recent_indirect(comparativas["right"], "Visitante vs rival del local")

    with st.expander("Payload completo"):
        st.json(payload)


def main() -> None:
    st.set_page_config(page_title="Analizador AH Streamlit", layout="wide")
    st.title("Analizador de partidos (Streamlit)")

    matches = load_matches_from_json()
    if not matches:
        st.error("No se encontraron partidos en data.json. Asegúrate de actualizar el fichero antes de usar la aplicación.")
        return

    handicap_options = sorted({match.handicap_bucket for match in matches})
    handicap_display = ["Todos"] + handicap_options
    with st.sidebar:
        st.header("Filtros")
        current_time = datetime.now(MADRID_TZ)
        st.caption(f"Hora actual en Madrid: {current_time:%d/%m %H:%M}")
        selected_handicaps = st.multiselect(
            "Handicap asiático",
            handicap_display,
            default=["Todos"],
            help="Selecciona uno o más handicaps para acotar los partidos.",
        )
        search_text = st.text_input("Buscar equipo", placeholder="Nombre del equipo...")

    filtered_matches = filter_matches(matches, selected_handicaps, search_text)

    st.markdown(f"### Próximos partidos ({len(filtered_matches)})")
    if not filtered_matches:
        st.info("No hay partidos disponibles con los filtros aplicados. Ajusta el hándicap o la búsqueda.")
    else:
        for match in filtered_matches:
            with st.container(border=True):
                col_time, col_matchup, col_handicap, col_goal, col_prev, col_analysis = st.columns([1.2, 3, 1, 1, 1, 1])
                col_time.caption(match.kickoff_display)
                col_matchup.markdown(f"**{match.home_team}** vs **{match.away_team}**")
                col_handicap.metric("AH", match.handicap_bucket)
                goal_line = format_ah_as_decimal_string_of(match.goal_line)
                col_goal.metric("O/U", goal_line if goal_line not in {"-", "?"} else "-")

                if col_prev.button("👁 Vista previa", key=f"preview_{match.match_id}"):
                    st.session_state["selected_preview_id"] = match.match_id
                    st.session_state["selected_analysis_id"] = None

                if col_analysis.button("📊 Estudio", key=f"analysis_{match.match_id}"):
                    st.session_state["selected_analysis_id"] = match.match_id
                    st.session_state["selected_preview_id"] = None

    st.divider()

    preview_id = st.session_state.get("selected_preview_id")
    analysis_id = st.session_state.get("selected_analysis_id")

    if preview_id:
        with st.spinner("Cargando vista previa..."):
            preview_data = fetch_preview_data(preview_id)
        render_preview_section(preview_data)
    elif analysis_id:
        with st.spinner("Calculando estudio completo..."):
            analysis_payload = fetch_full_analysis(analysis_id)
        render_analysis_section(analysis_payload)
    else:
        st.info("Selecciona un partido para ver la vista previa o el estudio completo.")


if __name__ == "__main__":
    main()
