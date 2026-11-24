"""Calculo del resumen de la sesion. Solo se reportan datos realmente calculados;
lo demas se registra explicitamente como no disponible."""
from datetime import datetime
from typing import Dict, Optional

import numpy as np

NOTES = [
    "Una 'deteccion' es una caja devuelta por el tracker (con ID) en un fotograma.",
    "Velocidad promedio/maxima: sobre muestras instantaneas suavizadas (ventana corta).",
    "Si hubo cambios de ID del tracker, 'objetos unicos' puede sobrestimar el total real.",
    "La compensacion de camara es una aproximacion 2D; no es odometria visual 3D.",
]


def objects_table(session):
    rows = []
    for tid, o in sorted(session.obj.items()):
        rows.append({
            "id": tid, "class": o["cls"], "first_timestamp": o["first_t"],
            "last_timestamp": o["last_t"], "frames": o["frames"],
            "mean_speed_px_s": (o["sum_px"] / o["n_px"]) if o["n_px"] else None,
            "max_speed_px_s": o["max_px"] if o["n_px"] else None,
            "max_speed_kmh": o["max_kmh"]})
    return rows


def flow_per_interval(session) -> Dict[int, Dict[str, int]]:
    """Cruces por intervalo de tiempo y sentido (analitica de transito)."""
    iv = session.cfg["interval_s"]
    out: Dict[int, Dict[str, int]] = {}
    for ev in session.line.events:
        d = out.setdefault(int(ev["timestamp"] // iv), {"A->B": 0, "B->A": 0})
        d[ev["direction"]] += 1
    return out


def crossings_by_hour(session):
    """Cruces unicos (los de ``session.line.events``) agrupados por hora.

    Archivo de video: hora transcurrida del video (0-1 h, 1-2 h...).
    Webcam: hora del reloj (inicio de sesion + timestamp).
    Devuelve ([(etiqueta, cruces)], descripcion). Incluye las horas intermedias sin cruces.
    """
    from datetime import timedelta
    webcam = session.info.kind == "webcam"
    offset = (session.started_at.minute * 60 + session.started_at.second) if webcam else 0
    counts: Dict[int, int] = {}
    for ev in session.line.events:
        h = int((ev["timestamp"] + offset) // 3600)
        counts[h] = counts.get(h, 0) + 1
    if not counts:
        return [], ""
    base = session.started_at.replace(minute=0, second=0, microsecond=0)
    rows = []
    for h in range(min(counts), max(counts) + 1):
        label = ((base + timedelta(hours=h)).strftime("%H:00") if webcam else f"{h}-{h + 1} h")
        rows.append((label, counts.get(h, 0)))
    basis = ("hora del reloj (webcam)" if webcam
             else "hora transcurrida del video (0-1 h = primera hora)")
    return rows, basis


def build_summary(session, status: str, wall_seconds: float,
                  ended_at: Optional[datetime] = None, files=None, unavailable=None) -> dict:
    ended_at = ended_at or datetime.now()
    snap = session.snapshot()
    na: Dict[str, str] = dict(unavailable or {})
    calibrated = snap["calibrated"]
    line_used = session.has("line") and session.line.defined

    if not calibrated:
        na["velocidad_real_kmh"] = "sin calibracion espacial valida"
    if not line_used:
        na["cruces"] = "linea virtual no definida o perfil sin linea"
    if session.mode == "moving" and not session.use_comp:
        na["movimiento_camara"] = "perfil sin compensacion de camara"
    if session.mode == "moving":
        na["mapa_de_calor"] = "no se genera en camara movil"
    if snap["avg_px"] is None:
        na["velocidad_px_s"] = "ningun objeto acumulo suficiente historial"

    summary = {
        "session": session.name, "status": status,
        "started_at": session.started_at.isoformat(timespec="seconds"),
        "ended_at": ended_at.isoformat(timespec="seconds"),
        "processing_wall_time_s": round(wall_seconds, 2),
        "video_time_processed_s": round(max(0.0, session.last_ts - (session.first_ts or 0.0)), 3),
        "video": session.info.as_dict(),
        "camera_mode": session.mode, "analysis_profile": session.profile,
        "model": session.cfg["model"], "tracker": session.cfg["tracker"],
        "conf_threshold": session.cfg["conf"], "iou_threshold": session.cfg["iou"],
        "classes_filter": session.cfg.get("classes"),
        "frames_processed": snap["frames"],
        "total_unique_objects": snap["unique"],
        "objects_by_class": session.classes_count(),
        "total_detections": snap["detections"],
        "speed": {
            "basis": session.speed_basis,
            "avg_px_s": snap["avg_px"], "max_px_s": snap["max_px"],
            "avg_kmh": snap["avg_kmh"], "max_kmh": snap["max_kmh"],
            "calibrated": calibrated,
        },
        "avg_fps_processing": round(snap["fps"], 2),
        "avg_inference_ms": round(snap["infer_ms"], 2),
        "crossings": ({"total": session.line.total, "A->B": session.line.count_ab,
                       "B->A": session.line.count_ba, "by_class": session.line.by_class,
                       "per_interval": {str(k): v for k, v in flow_per_interval(session).items()},
                       "interval_s": session.cfg["interval_s"]}
                      if line_used else None),
        "camera_motion": ({"frames_invalid": session.cam_invalid_frames,
                           "frames_total": len(session.cam_rows)}
                          if session.use_comp else None),
        "calibration": session.calib.to_dict() if calibrated else None,
        "not_available": na,
        "notes": NOTES,
        "files": files or [],
    }
    if summary["crossings"] is not None and session.has("traffic"):
        rows, basis = crossings_by_hour(session)
        summary["crossings"]["per_hour"] = {label: n for label, n in rows}
        summary["crossings"]["per_hour_basis"] = basis
    return summary
