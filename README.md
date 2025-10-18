# Streamlit Version

Aplicacion Streamlit que reproduce al 100% la experiencia del servidor Flask original (`app.py`). Incluye:
- Conmutador entre proximos y finalizados, con filtros por handicap y paginacion incremental.
- Botones para estudio completo y vista previa con cache y modos Ultra/Ligero/Completo.
- Panel lateral para analisis manual con almacenamiento en la sesion.
- Lectura directa desde `data.json` (ruta personalizable desde la barra lateral).
- Script CLI opcional para subir informacion a Google Sheets si se necesita mantener esa integracion.

La captura `Caputra_Sheets.jpg` sirve como referencia visual para revisar la estructura de las hojas.

## Requisitos

Instala las dependencias dentro del entorno virtual correspondiente:

```bash
pip install -r requirements.txt
```

Debes tener un archivo de credenciales de servicio de Google (`clave_sheets.json`) o configurar la variable de entorno `GOOGLE_APPLICATION_CREDENTIALS`. El script y la app respetan tambien la ruta de Render (`/etc/secrets/clave_sheets.json`).

## Ejecutar la app Streamlit

```bash
cd app_google_sheets/Version_Sheets
streamlit run streamlit_app.py
```

Funciones destacadas:
- `Filtros` para handicap con normalizacion identica al Flask (`normalize_handicap_to_half_bucket_str`).
- `Vista previa` con modos Ultra/Ligero/Completo y resumen (rendimiento, H2H directo/indirecto, tiempos de ejecucion).
- `Estudio completo` con pestanas Resumen, Mercado, Analisis avanzado y JSON, reutilizando todo `modules.estudio_scraper`.
- Panel de `analisis manual` que guarda estudios y vistas previas lanzados desde la barra lateral.
- Paginacion con `Cargar mas partidos` que amplia en bloques constantes `PAGE_SIZE`.

## Generar `data.json` (Colab)

Ubicacion: `colab_generar_datos.py`

- Descarga hasta 1000 partidos proximos y finalizados usando el scraper del proyecto.
- Permite filtrar por rango horario (`--start-hour`, `--end-hour`) en la zona horaria deseada.
- Muestra el ID de cada partido en el resumen HTML generado (`--html`), listo para copiar/pegar en Colab.
- Deja el archivo en el directorio que le indiques (`--output`, por defecto `../data.json`).

Ejemplo rapido en Colab:

```python
!python colab_generar_datos.py --limit 1000 --start-hour 4 --end-hour 23 --output datos.json --html preview.html
from IPython.display import HTML
HTML(open("preview.html").read())
```

El JSON resultante mantiene las claves `upcoming_matches` y `finished_matches`, por lo que se puede cargar directamente en `streamlit_app.py` o pasarse a `estudio.py`/la funcion del “ojito”.

## Script de subida a Google Sheets (opcional)

Ubicacion: `upload_to_google_sheets.py`

### Formato de entrada

JSON unico (`--dataset`) con claves `upcoming_matches` y `finished_matches`:

```json
{
  "upcoming_matches": [
    {"id": "123", "time": "2025-10-20 18:00", "home_team": "Local", "away_team": "Visitante", "handicap": "0"}
  ],
  "finished_matches": [
    {"id": "456", "time": "2025-10-19 20:00", "home_team": "Local 2", "away_team": "Visitante 2", "score": "2-1"}
  ]
}
```

Tambien puedes usar archivos separados (`--upcoming`, `--finished`) en CSV o JSON. Las claves adicionales en cada registro se respetan tal cual.

### Ejemplos de uso

```bash
# JSON combinado
python upload_to_google_sheets.py --dataset datos.json

# Archivos por separado y credenciales personalizadas
python upload_to_google_sheets.py \
  --upcoming proximos.csv \
  --finished finalizados.json \
  --credentials "C:/ruta/mi_servicio.json"
```

Opciones relevantes:
- `--sheet-name`: nombre del documento (por defecto `Almacen_Stre`).
- `--worksheet-upcoming`, `--worksheet-finished`, `--worksheet-log`: pestanas a actualizar.
- `--deduplicate-column`: columna utilizada para evitar duplicados al consolidar en `Hoja 3` (por defecto `id`). Establece `''` para desactivar.
- `--no-log`: omite la actualizacion de `Hoja 3`.

El script limpia completamente `Hoja 1` y `Hoja 2` antes de escribir. Para `Hoja 3` fusiona el contenido previo con el nuevo y anade columnas `match_status` y `uploaded_at` (ISO UTC). Si la columna de deduplicacion existe, conserva la version mas reciente de cada partido.

## Preparar repositorio y despliegue en Streamlit Cloud

1. **Inicializa Git** (si no existe): `git init` dentro de `app_google_sheets` o en el raiz del proyecto actual.
2. **Crea un repositorio** en GitHub y agrega el remoto: `git remote add origin https://github.com/usuario/repositorio.git`.
3. **Incluye solo lo necesario**: en el commit deben estar `Version_Sheets/streamlit_app.py`, `upload_to_google_sheets.py`, `app_utils.py`, `modules/`, `requirements.txt`, las plantillas y la captura (si la quieres de referencia). No subas `clave_sheets.json`.
4. **Commit y push**: `git add . && git commit -m "Deploy streamlit version" && git push origin main`.
5. **Configura secrets** en GitHub o Streamlit Cloud (`GOOGLE_APPLICATION_CREDENTIALS` apuntando a un secret file o `GCP_SERVICE_ACCOUNT` segun tu estrategia).
6. **Streamlit Cloud**: en https://share.streamlit.io crea una app nueva apuntando al repositorio y selecciona `Version_Sheets/streamlit_app.py` como entrypoint. En la seccion “Advanced settings” declara las variables de entorno necesarias y, si usas secrets, pega el JSON de la cuenta de servicio.
7. **Tareas posteriores**: valida que la app se cargue sin errores, ejecuta un analisis manual y revisa la hoja actualizada tras usar el script.

Con estas instrucciones puedes replicar localmente, subir los datos y desplegar la aplicacion en la nube con la misma funcionalidad que el backend Flask original.
