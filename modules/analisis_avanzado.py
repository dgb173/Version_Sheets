from .utils import check_handicap_cover, parse_ah_to_number_of

def generar_analisis_comparativas_indirectas(indirect_comparison_data):
    """
    Genera una nota de análisis basada en los datos de las comparativas indirectas.
    """
    if not indirect_comparison_data or (not indirect_comparison_data.get("comp1") and not indirect_comparison_data.get("comp2")):
        return "<p>No hay suficientes datos para un análisis de comparativas indirectas.</p>"

    comp1 = indirect_comparison_data.get("comp1")
    comp2 = indirect_comparison_data.get("comp2")

    # Flags para identificar patrones clave
    ambos_cubren_handicap = False
    ambos_no_cubren_handicap = False
    favorito_cubre_underdog_no = False
    underdog_cubre_favorito_no = False

    # Analizar la cobertura del hándicap
    if comp1 and comp2:
        cover1, _ = check_handicap_cover(comp1['resultado_raw'], comp1['ah_num'], comp1['main_team'], comp1['main_team'], "Rival", comp1['main_team'])
        cover2, _ = check_handicap_cover(comp2['resultado_raw'], comp2['ah_num'], comp2['main_team'], comp2['main_team'], "Rival", comp2['main_team'])
        
        if "CUBIERTO" in cover1 and "CUBIERTO" in cover2:
            ambos_cubren_handicap = True
        elif "NO CUBIERTO" in cover1 and "NO CUBIERTO" in cover2:
            ambos_no_cubren_handicap = True
        
        # Determinar favorito y underdog
        if comp1['ah_num'] is not None and comp2['ah_num'] is not None:
            if abs(comp1['ah_num']) > abs(comp2['ah_num']):
                favorito = comp1
                underdog = comp2
            else:
                favorito = comp2
                underdog = comp1
            
            cover_fav, _ = check_handicap_cover(favorito['resultado_raw'], favorito['ah_num'], favorito['main_team'], favorito['main_team'], "Rival", favorito['main_team'])
            cover_under, _ = check_handicap_cover(underdog['resultado_raw'], underdog['ah_num'], underdog['main_team'], underdog['main_team'], "Rival", underdog['main_team'])

            if "CUBIERTO" in cover_fav and "NO CUBIERTO" in cover_under:
                favorito_cubre_underdog_no = True
            elif "NO CUBIERTO" in cover_fav and "CUBIERTO" in cover_under:
                underdog_cubre_favorito_no = True

    # Construir la nota de análisis
    analisis_html = "<div class='analysis-note'>"
    analisis_html += "<h5>Análisis Avanzado de Comparativas Indirectas</h5>"
    analisis_html += "<ul>"

    if ambos_cubren_handicap:
        analisis_html += "<li><strong style='color: green;'>Patrón Positivo:</strong> Ambos equipos cubrieron su hándicap contra su respectivo rival. Esto sugiere que ambos equipos llegan en buena forma y podrían superar las expectativas del mercado.</li>"
    elif ambos_no_cubren_handicap:
        analisis_html += "<li><strong style='color: red;'>Patrón Negativo:</strong> Ambos equipos fallaron en cubrir su hándicap. Esto podría indicar que ambos están sobrevalorados por el mercado o llegan en un momento de baja forma.</li>"
    
    if favorito_cubre_underdog_no:
        analisis_html += "<li><strong style='color: blue;'>Señal de Fortaleza del Favorito:</strong> El equipo más favorito cubrió su hándicap, mientras que el no favorito no lo hizo. Esto refuerza la idea de que el favorito tiene una ventaja real y podría ser una apuesta sólida.</li>"
    elif underdog_cubre_favorito_no:
        analisis_html += "<li><strong style='color: orange;'>Posible Sorpresa del No Favorito:</strong> El equipo no favorito cubrió su hándicap y el favorito no. Esta es una señal de alerta que podría indicar una posible sorpresa o un partido más igualado de lo que las cuotas sugieren.</li>"

    if not (ambos_cubren_handicap or ambos_no_cubren_handicap or favorito_cubre_underdog_no or underdog_cubre_favorito_no):
        analisis_html += "<li>No se han detectado patrones claros en la cobertura de hándicap de las comparativas indirectas.</li>"

    analisis_html += "</ul></div>"

    return analisis_html
