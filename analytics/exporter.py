"""Exportacion de una sesion: CSV, JSON, PNG y PDF opcional."""
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from analytics import charts
from analytics.report_pdf import build_pdf
from analytics.statistics import build_summary, objects_table


def _csv(path: Path, rows, columns):
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False, encoding="utf-8-sig")


def write_configuration(session):
    cfg = dict(session.cfg)
    cfg["video"] = session.info.as_dict()
    cfg["line"] = ({"p1": session.line.p1, "p2": session.line.p2, "enabled": session.line.enabled}
                   if session.line.defined else None)
    cfg["calibration"] = session.calib.to_dict()
    (session.folder / "configuration.json").write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return cfg


def write_initial_summary(session):
    """Se escribe al iniciar para que el historial muestre 'en ejecucion' aunque falle."""
    s = build_summary(session, "en_ejecucion", 0.0)
    (session.folder / "summary.json").write_text(
        json.dumps(s, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def export_session(session, status: str, wall_seconds: float, make_pdf: bool = False,
                   extra_files=None) -> dict:
    f = session.folder
    files = list(extra_files or [])
    na = {}
    cfg = write_configuration(session)
    files.append("configuration.json")

    _csv(f / "trajectories.csv", session.traj_rows,
         ["id", "class", "frame", "timestamp", "x", "y", "x_comp", "y_comp", "speed_px_s",
          "speed_kmh", "direction", "direction_deg", "comp_valid"])
    _csv(f / "detections.csv", session.det_rows,
         ["frame", "timestamp", "id", "class", "confidence", "x1", "y1", "x2", "y2"])
    _csv(f / "objects.csv", objects_table(session),
         ["id", "class", "first_timestamp", "last_timestamp", "frames", "mean_speed_px_s",
          "max_speed_px_s", "max_speed_kmh"])
    files += ["trajectories.csv", "detections.csv", "objects.csv"]

    if session.has("line") and session.line.defined:
        _csv(f / "crossings.csv", session.line.events,
             ["id", "direction", "timestamp", "class", "frame"])
        files.append("crossings.csv")
    if session.use_comp:
        _csv(f / "camera_motion.csv", session.cam_rows,
             ["frame", "timestamp", "dx", "dy", "rotation_deg", "scale", "matches", "inliers",
              "inlier_ratio", "reproj_err", "valid", "reason", "cum_dx", "cum_dy"])
        files.append("camera_motion.csv")

    images = []
    jobs = [("mapa_de_calor_densidad", lambda: charts.save_heatmap(session, f, "density")),
            ("mapa_de_calor_movimiento", lambda: charts.save_heatmap(session, f, "motion")),
            ("trayectorias", lambda: charts.save_trajectories(session, f)),
            ("objetos_por_clase", lambda: charts.save_objects_by_class(session, f)),
            ("distribucion_velocidades", lambda: charts.save_speed_distribution(session, f)),
            ("detecciones_por_intervalo", lambda: charts.save_detections_over_time(session, f)),
            ("flujo_vehicular", lambda: charts.save_traffic_flow(session, f)),
            ("cruces_por_hora", lambda: charts.save_crossings_by_hour(session, f))]
    for key, job in jobs:
        try:
            ok, reason, name = job()
        except Exception as e:                       # una grafica fallida no aborta el resto
            ok, reason, name = False, f"error: {e}", None
        if ok:
            images.append(name)
        elif not (key.startswith("mapa") and session.mode != "fixed"):
            na[f"grafica_{key}"] = reason
    files += images

    summary = build_summary(session, status, wall_seconds, datetime.now(), files, na)
    if make_pdf:
        try:
            files.append(build_pdf(f, summary, cfg, images))
        except Exception as e:
            summary["not_available"]["reporte_pdf"] = f"error: {e}"
    summary["files"] = files + ["summary.json"]
    (f / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str),
                                    encoding="utf-8")
    return summary
