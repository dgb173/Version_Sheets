from modules.estudio_scraper import obtener_datos_preview_ligero
import json
print(json.dumps(obtener_datos_preview_ligero('2887637'))[:1000])
