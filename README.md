# Vision Tracker

Aplicación de escritorio (PySide6) para detección YOLO, tracking 2D (ByteTrack / BoT-SORT),
conteo por línea virtual, trayectorias, velocidad, mapas de calor y compensación de
movimiento de cámara (ORB + RANSAC). Proyecto académico de Visión Artificial (ejercicios 2B, 2C, 2D; N1 y N2).

## Instalación
```bash
python -m venv .venv && .venv\Scripts\activate        # Windows (Linux/Mac: source .venv/bin/activate)
# Sin GPU conviene instalar antes PyTorch CPU:
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python main.py
```
Python 3.10 o 3.11. El modelo `yolo11n.pt` se descarga automáticamente la primera vez (requiere internet)
o puede copiarse manualmente a `models/`. Ultralytics usa licencia AGPL-3.0 (mencionarlo en el informe).

## Uso rápido
1. **Fuente**: «Abrir video…» o Webcam (use «Vista previa» para ver un fotograma antes de definir línea/calibración).
2. **Cámara y perfil** (se bloquean mientras corre una sesión):

| Perfil | Modo | Activa |
|---|---|---|
| Tracking general (2B) | fija / móvil | cajas, IDs, confianza, trayectorias |
| Análisis de movimiento (2C) | fija | + línea virtual, velocidad px/s, mapa de calor |
| Compensación de cámara (2D) | móvil | + ORB, RANSAC, trayectorias y velocidades compensadas |
| Radar de velocidad (N1) | fija | + calibración (homografía) y velocidad en km/h |
| Analítica de tránsito (N2) | fija | + conteo por clase/sentido y flujo por intervalo |

3. **Línea virtual**: «Definir línea» y 2 clics sobre el video. Se puede mover arrastrando sus extremos. «A→B» significa del lado A al lado B (las letras se dibujan junto a la línea).
4. **Calibración** (antes de iniciar): «Calibrar escena», ingrese ancho×largo reales y haga clic en 4 puntos del **suelo** (sup-izq, sup-der, inf-der, inf-izq).
5. **Iniciar**. Pausar/Reanudar, Fotograma a fotograma, Detener y Reiniciar (crea una sesión nueva).
6. Los resultados se guardan en `results/<fecha>_<video>/`. La pestaña **Sesiones** lista ejecuciones anteriores.

Atajos: F11 pantalla completa, Esc salir, rueda del ratón = zoom, clic derecho arrastrando = desplazar.

## Archivos exportados (`results/<sesion>/`)
`summary.json`, `configuration.json`, `trajectories.csv`, `detections.csv`, `objects.csv`, `crossings.csv` (si hay línea),
`camera_motion.csv` (cámara móvil con compensación), PNG (`heatmap_density`, `heatmap_motion`, `trajectories`, `objects_by_class`,
`speed_distribution`, `detections_over_time`, `traffic_flow`), y opcionalmente `processed.mp4` y `report.pdf`.
Lo que no se pudo calcular aparece como `null`/vacío y se lista en `summary.json → not_available`.

## Decisiones técnicas y limitaciones (importantes para el informe)
* **YOLO se ejecuta una sola vez por fotograma** (`model.track(persist=True)`); todos los módulos reutilizan ese resultado.
* **Velocidad**: usa timestamps reales (no supone FPS constante), ventana de 0,5 s y suavizado EMA. En archivos el timestamp sale de `CAP_PROP_POS_MSEC`; si el backend lo da mal se usa índice/FPS.
* **Velocidad real**: homografía de 4 puntos del plano del suelo; se calcula con el *punto de contacto* (centro inferior de la caja) y solo dentro de la zona calibrada (± 20 px). Fuera de ella o sin calibración no se muestra velocidad real.
* **Línea virtual**: cambio de lado con estado por ID, zona muerta de 6 px y enfriamiento de 1 s por ID, y solo cruces dentro del segmento. Un cambio de ID del tracker puede producir un conteo extra.
* **Cámara móvil**: ORB sobre el fondo (las cajas se enmascaran) → BFMatcher + ratio test → `estimateAffinePartial2D` con RANSAC. Es una **compensación 2D** (traslación+rotación+escala) respecto al primer fotograma, **no odometría visual 3D**; es razonable con fondo plano/lejano y falla con desenfoque, poca textura, cambios de luz o mucha parte dinámica. Si la estimación no pasa la validación (correspondencias, inliers, proporción, escala, error de reproyección) se muestra «COMPENSACIÓN NO CONFIABLE», no se aplica la corrección, se conserva la última transformación válida y **no se calcula velocidad** en ese fotograma.
* **BoT-SORT** ya incluye su propia compensación global de movimiento (`gmc_method`) dentro del tracker; la compensación de este proyecto se aplica aparte, sobre trayectorias y velocidades. Conviene comparar ambos casos en el informe.
* El mapa de calor no se genera en cámara móvil. El fondo del mapa es el primer fotograma.
* Calibración y definición de línea no están disponibles con la webcam en marcha hasta tener una vista previa.

## Pruebas incluidas
```bash
python -m tests.test_logic       # línea, velocidad, calibración, compensación de cámara
python -m tests.test_pipeline    # sesión completa con videos sintéticos y detector simulado
QT_QPA_PLATFORM=offscreen python -m tests.test_gui   # interfaz sin pantalla
```
Los tests usan un detector simulado (`tests/fake_detector.py`) para no depender de YOLO.

## Estructura
```
main.py  config/{settings,classes}.py
interface/{main_window,video_panel,control_panel,analytics_panel,session_history,calibration_dialog}.py  styles.qss
core/{video_capture,detector,tracker,session,pipeline,trajectory,speed_estimator,line_counter,calibration,heatmap,renderer}.py
odometry/{feature_extractor,feature_matcher,motion_estimator,camera_compensation}.py
analytics/{statistics,charts,exporter,report_pdf}.py
models/  data/exports/  results/  tests/
```
