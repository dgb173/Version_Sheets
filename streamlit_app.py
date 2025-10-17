
import streamlit as st
import pandas as pd
import os
import time
from datetime import datetime
import pytz
import json

# --- Importaciones de la lógica de la aplicación original ---
# Asumimos que app.py y los módulos están en el mismo directorio
from app_utils import load_data_from_sheets, filter_upcoming_matches, normalize_handicap_to_half_bucket_str
from modules.estudio_scraper import (
    obtener_datos_completos_partido,
    format_ah_as_decimal_string_of,
    obtener_datos_preview_ultrarapido,
)

# --- Configuración de la página de Streamlit ---
st.set_page_config(page_title="Análisis de Partidos", layout="wide")

st.title("Visor de Partidos y Análisis")

# --- Caching de datos ---

# Cache para los datos principales de Google Sheets
@st.cache_data(ttl=300) # Cache por 5 minutos
def cached_load_data():
    print("Cargando datos frescos desde Google Sheets...")
    return load_data_from_sheets()

# Cache para los análisis detallados (scraping pesado)
@st.cache_data(ttl=3600) # Cache por 1 hora
def cached_get_full_analysis(match_id):
    print(f"Ejecutando análisis completo para el partido {match_id}...")
    return obtener_datos_completos_partido(match_id)

# Cache para las vistas previas (scraping ligero)
@st.cache_data(ttl=600) # Cache por 10 minutos
def cached_get_preview(match_id):
    print(f"Ejecutando vista previa para el partido {match_id}...")
    return obtener_datos_preview_ultrarapido(match_id)

# --- Lógica de la Interfaz ---

# Cargar datos iniciales
all_data = cached_load_data()

if all_data.get("error"):
    st.error(f"No se pudieron cargar los datos desde Google Sheets: {all_data.get('error')}")
    st.stop()

# --- Barra Lateral (Sidebar) ---
st.sidebar.header("Navegación y Filtros")

page_mode = st.sidebar.radio(
    "Selecciona una vista",
    ('Próximos Partidos', 'Resultados Finalizados')
)

# Lógica para seleccionar los datos a mostrar
if page_mode == 'Próximos Partidos':
    matches_raw = all_data.get('upcoming_matches', [])
    matches_processed = filter_upcoming_matches(matches_raw)
    page_title = 'Próximos Partidos'
else:
    matches_processed = all_data.get('finished_matches', [])
    page_title = 'Resultados Finalizados'

st.header(page_title)

# Filtro por Hándicap
if matches_processed:
    handicap_options = sorted({
        normalize_handicap_to_half_bucket_str(m.get('handicap'))
        for m in matches_processed if m and normalize_handicap_to_half_bucket_str(m.get('handicap')) is not None
    }, key=lambda x: float(x))
    
    handicap_options.insert(0, "Todos")
    
    hf = st.sidebar.selectbox(
        'Filtrar por hándicap',
        options=handicap_options,
        index=0
    )

    if hf and hf != "Todos":
        target = normalize_handicap_to_half_bucket_str(hf)
        if target is not None:
            matches_processed = [m for m in matches_processed if m and normalize_handicap_to_half_bucket_str(m.get('handicap', '')) == target]

# --- Sección de Análisis por ID ---
st.sidebar.header("Análisis Manual")
manual_match_id = st.sidebar.text_input("Introduce ID de partido para analizar")
if st.sidebar.button("Analizar ID"):
    if manual_match_id:
        with st.spinner(f"Obteniendo análisis para el partido {manual_match_id}..."): 
            analysis_data = cached_get_full_analysis(manual_match_id)
            st.subheader(f"Análisis del Partido: {manual_match_id}")
            if "error" in analysis_data:
                st.error(analysis_data["error"])
            else:
                st.success(f"Análisis para {analysis_data.get('home_name', '')} vs {analysis_data.get('away_name', '')} completado.")
                # Mostrar el análisis en un expander
                with st.expander("Ver detalles del análisis manual", expanded=True):
                    st.json(analysis_data)
    else:
        st.sidebar.warning("Por favor, introduce un ID.")


# --- Visualización de Partidos ---
if not matches_processed:
    st.warning("No se encontraron partidos para los filtros seleccionados.")
else:
    # Cabecera de la tabla
    cols = st.columns([2, 4, 2, 2, 2, 2])
    cols[0].write("**Hora**")
    cols[1].write("**Partido**")
    if page_mode == 'Resultados Finalizados':
        cols[2].write("**Resultado**")
        cols[3].write("**Hándicap**")
        cols[4].write("**Línea Goles**")
        cols[5].write("**Análisis**")
    else:
        cols[2].write("**Hándicap**")
        cols[3].write("**Línea Goles**")
        cols[4].write("**Análisis**")
        cols[5].write("**Vista Previa**")


    # Filas de partidos
    for match in matches_processed:
        match_id = match.get('id')
        if not match_id:
            continue

        col_map = {
            'time': 0,
            'teams': 1,
            'score_or_handicap': 2,
            'goal_line_or_handicap': 3,
            'analysis': 4,
            'preview': 5
        }

        cols = st.columns([2, 4, 2, 2, 2, 2])
        
        cols[col_map['time']].write(match.get('time', 'N/A'))
        cols[col_map['teams']].write(f"{match.get('home_team', 'N/A')} vs {match.get('away_team', 'N/A')}")

        if page_mode == 'Resultados Finalizados':
            cols[col_map['score_or_handicap']].write(match.get('score', 'N/A'))
            cols[col_map['goal_line_or_handicap']].write(match.get('handicap', 'N/A'))
            analysis_col_idx = 4
            preview_col_idx = -1 # No hay preview en resultados
        else: # Próximos
            cols[col_map['score_or_handicap']].write(match.get('handicap', 'N/A'))
            cols[col_map['goal_line_or_handicap']].write(match.get('goal_line', 'N/A'))
            analysis_col_idx = 4
            preview_col_idx = 5

        # Botón de Análisis Avanzado
        if cols[analysis_col_idx].button("Avanzado", key=f"full_{match_id}"):
            with st.spinner(f"Cargando análisis avanzado para {match_id}..."): 
                full_data = cached_get_full_analysis(match_id)
                expander_title = f"Análisis Avanzado: {full_data.get('home_name', '')} vs {full_data.get('away_name', '')}"
                with st.expander(expander_title, expanded=True):
                    if "error" in full_data:
                        st.error(full_data["error"])
                    else:
                        st.json(full_data)

        # Botón de Vista Previa
        if preview_col_idx != -1 and cols[preview_col_idx].button("Rápida", key=f"preview_{match_id}"):
            with st.spinner(f"Cargando vista previa para {match_id}..."): 
                preview_data = cached_get_preview(match_id)
                expander_title = f"Vista Previa: {preview_data.get('home_team', '')} vs {preview_data.get('away_team', '')}"
                with st.expander(expander_title, expanded=True):
                    if "error" in preview_data:
                        st.error(preview_data["error"])
                    else:
                        # Recrear la vista previa de forma similar a la original
                        st.subheader("Resumen")
                        
                        # Rendimiento Reciente
                        if 'recent_form' in preview_data:
                            st.write("**Rendimiento Reciente (V-E-D)**")
                            col1, col2 = st.columns(2)
                            home = preview_data['recent_form']['home']
                            away = preview_data['recent_form']['away']
                            col1.metric(label=preview_data.get('home_team', 'Local'), value=f"{home['wins']}-{home['draws']}-{home['losses']}")
                            col2.metric(label=preview_data.get('away_team', 'Visitante'), value=f"{away['wins']}-{away['draws']}-{away['losses']}")

                        # H2H
                        if 'h2h_stats' in preview_data:
                            st.write("**H2H Directo**")
                            h2h = preview_data['h2h_stats']
                            st.text(f"{preview_data.get('home_team', 'Local')}: {h2h['home_wins']} | Empates: {h2h['draws']} | {preview_data.get('away_team', 'Visitante')}: {h2h['away_wins']}")

                        # H2H Indirecto
                        if 'h2h_indirect' in preview_data:
                            st.write("**H2H Indirecto (Rival Común)**")
                            indirect = preview_data['h2h_indirect']
                            st.text(f"Mejor {preview_data.get('home_team', 'Local')}: {indirect['home_better']} | Empates: {indirect['draws']} | Mejor {preview_data.get('away_team', 'Visitante')}: {indirect['away_better']}")
        
        st.markdown("---")
