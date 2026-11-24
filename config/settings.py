"""Configuracion global y constantes de Vision Tracker."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"
RESULTS_DIR = BASE_DIR / "results"
EXPORTS_DIR = BASE_DIR / "data" / "exports"
STYLES_PATH = BASE_DIR / "interface" / "styles.qss"

APP_NAME = "Vision Tracker"
DEFAULT_MODEL = "yolo11n.pt"
MODEL_CHOICES = ["yolo11n.pt", "yolov8n.pt", "yolo11s.pt", "yolov8s.pt"]
TRACKERS = {"ByteTrack": "bytetrack.yaml", "BoT-SORT": "botsort.yaml"}

MODES = {"fixed": "Cámara fija", "moving": "Cámara móvil"}

# features: funcionalidades que activa cada perfil
PROFILES = {
    "general": {"label": "Tracking general (2B)", "modes": ["fixed", "moving"],
                "features": set()},
    "motion": {"label": "Análisis de movimiento (2C)", "modes": ["fixed"],
               "features": {"line", "speed", "heatmap", "calibration"}},
    "compensation": {"label": "Compensación de cámara (2D)", "modes": ["moving"],
                     "features": {"compensation", "speed"}},
    "radar": {"label": "Radar de velocidad (N1)", "modes": ["fixed"],
              "features": {"line", "speed", "heatmap", "calibration"}},
    "traffic": {"label": "Analítica de tránsito (N2)", "modes": ["fixed"],
                "features": {"line", "speed", "heatmap", "calibration", "traffic"}},
}

DEFAULT_RUN = {
    "conf": 0.35, "iou": 0.5, "imgsz": 640, "frame_skip": 1,
    "tail_length": 60,          # puntos de cola de trayectoria dibujados
    "speed_window_s": 0.5,      # ventana temporal para calcular velocidad
    "speed_min_dt_s": 0.2,
    "line_margin_px": 6.0,      # zona muerta (histeresis) de la linea
    "line_cooldown_s": 1.0,     # tiempo minimo entre cruces del mismo ID
    "interval_s": 10.0,         # intervalo para estadisticas temporales
    "heatmap_scale": 0.25,      # resolucion de la rejilla del mapa de calor
    "calib_tolerance_px": 20.0,
}

# Odometria visual (compensacion 2D)
ORB = {
    "n_features": 1500, "proc_width": 640, "ratio": 0.75,
    "min_matches": 25, "min_inliers": 15, "min_inlier_ratio": 0.4,
    "ransac_thresh": 3.0, "max_scale_dev": 0.10, "max_reproj_err": 2.5,
    "box_padding": 0.08,
}

PLAYBACK_SPEEDS = [("0.25x", 0.25), ("0.5x", 0.5), ("1x", 1.0), ("2x", 2.0), ("Máximo", 0.0)]
