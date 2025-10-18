import streamlit as st
import json
import os
import pandas as pd
from app_utils import normalize_handicap_to_half_bucket_str
from modules.estudio_scraper import obtener_datos_preview_ligero, obtener_datos_completos_partido

DATA_FILE = 'data.json'

# Función para cargar datos, cacheada para mejorar rendimiento
@st.cache_data
def load_data_from_file():
    """Carga los datos desde el archivo JSON."""
    if not os.path.exists(DATA_FILE):
        return {"upcoming_matches": [], "finished_matches": []}
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"upcoming_matches": [], "finished_matches": []}

# Título de la aplicación
st.title("Panel de Partidos")

# Inicializar el estado de la sesión para controlar la vista
if 'page_mode' not in st.session_state:
    st.session_state.page_mode = 'upcoming'

# Botones para cambiar de vista
col1, col2 = st.columns(2)
with col1:
    if st.button("Ver Próximos Partidos", use_container_width=True):
        st.session_state.page_mode = 'upcoming'
with col2:
    if st.button("Analizar Resultados", use_container_width=True):
        st.session_state.page_mode = 'finished'

# Cargar datos
all_data = load_data_from_file()

# Determinar qué datos mostrar
if st.session_state.page_mode == 'upcoming':
    st.header("Próximos Partidos")
    matches = all_data.get('upcoming_matches', [])
else:
    st.header("Resultados Finalizados")
    matches = all_data.get('finished_matches', [])

# Placeholder para la tabla de datos
st.subheader("Filtros")
handicap_filter = st.text_input("Filtrar por hándicap", placeholder="Ej: 0, 0.25, 0.5, 1")

col_filter1, col_filter2 = st.columns(2)
with col_filter1:
    if st.button("Aplicar filtro", use_container_width=True):
        st.session_state.handicap_filter = handicap_filter
with col_filter2:
    if st.button("Limpiar", use_container_width=True):
        st.session_state.handicap_filter = ""
        # This will clear the text in the input box as well in the next rerun
        st.experimental_rerun()

# Aplicar filtro si existe
if 'handicap_filter' in st.session_state and st.session_state.handicap_filter:
    target = normalize_handicap_to_half_bucket_str(st.session_state.handicap_filter)
    if target is not None:
        matches = [m for m in matches if m and normalize_handicap_to_half_bucket_str(m.get('handicap', '')) == target]

if matches:
    # Crear una cabecera para la tabla
    header_cols = st.columns((1, 3, 1, 1, 1, 1))
    headers = ["Hora", "Partido", "Hándicap", "Línea de Goles", "Análisis Avanzado", "Vista Previa Rápida"]
    for col, header in zip(header_cols, headers):
        col.markdown(f"**{header}**")

    # Iterar sobre cada partido para crear una fila interactiva
    for match in matches:
        match_id = match.get('id')
        cols = st.columns((1, 3, 1, 1, 1, 1))
        cols[0].write(match.get('time', 'N/A'))
        cols[1].write(f"{match.get('home_team', 'N/A')} vs {match.get('away_team', 'N/A')}")
        cols[2].write(match.get('handicap', 'N/A'))
        cols[3].write(match.get('goal_line', 'N/A'))
        
        # Botón de Análisis Avanzado
        if cols[4].button("📊", key=f"analisis_{match_id}"):
            with st.spinner(f"Realizando análisis avanzado para el partido {match_id}..."):
                analisis_data = obtener_datos_completos_partido(match_id)
                st.session_state.last_analysis = analisis_data

        # Botón de Vista Previa Rápida
        if cols[5].button("👁️", key=f"preview_{match_id}"):
            with st.spinner(f"Obteniendo vista previa para el partido {match_id}..."):
                preview_data = obtener_datos_preview_ligero(match_id)
                st.session_state.last_preview = preview_data
                st.session_state.last_preview_match_name = f"{match.get('home_team', '?')} vs {match.get('away_team', '?')}"

    st.markdown("---_---") # Separador

    # Mostrar los resultados de la vista previa si existen
    if 'last_preview' in st.session_state and st.session_state.last_preview:
        with st.expander(f"Vista Previa Rápida para: {st.session_state.get('last_preview_match_name', '')}", expanded=True):
            st.json(st.session_state.last_preview)

    # Mostrar los resultados del análisis si existen
    if 'last_analysis' in st.session_state and st.session_state.last_analysis:
        st.subheader("Resultado del Análisis Avanzado")
        st.json(st.session_state.last_analysis)

else:
    st.warning("No se encontraron partidos.")


