"""Graficas finales (matplotlib, backend Agg). Cada funcion devuelve (ok, motivo)."""
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import numpy as np

from analytics.statistics import crossings_by_hour, flow_per_interval


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _rgb(frame):
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def save_heatmap(session, folder: Path, kind: str = "density"):
    name = f"heatmap_{kind}.png"
    if session.mode != "fixed" or not session.has("heatmap"):
        return False, "mapa de calor solo en camara fija con perfil que lo incluya", None
    if kind == "motion" and not session.heat.has_motion:
        return False, "sin datos de velocidad para intensidad de movimiento", None
    if session.heat.density.sum() == 0 or session.ref_frame is None:
        return False, "sin posiciones registradas", None
    norm = session.heat.normalized(kind)
    h, w = session.ref_frame.shape[:2]
    fig, ax = plt.subplots(figsize=(8, 8 * h / w))
    ax.imshow(_rgb(session.ref_frame))
    big = cv2.resize(norm, (w, h), interpolation=cv2.INTER_CUBIC)
    im = ax.imshow(np.ma.masked_less(big, 0.03), cmap="jet", alpha=0.6, vmin=0, vmax=1)
    ax.set_title("Mapa de calor - " + ("densidad de posiciones" if kind == "density"
                                        else "intensidad de movimiento"))
    ax.axis("off")
    fig.colorbar(im, ax=ax, fraction=0.046, label="intensidad relativa")
    _save(fig, folder / name)
    return True, "", name


def save_trajectories(session, folder: Path):
    name = "trajectories.png"
    paths = {k: v for k, v in session.traj.paths.items() if len(v) >= 2}
    if not paths:
        return False, "sin trayectorias de al menos 2 puntos", None
    longest = sorted(paths.items(), key=lambda kv: -len(kv[1]))[:150]
    fig, ax = plt.subplots(figsize=(8, 6))
    if session.mode == "fixed" and session.ref_frame is not None:
        h, w = session.ref_frame.shape[:2]
        ax.imshow(_rgb(session.ref_frame), alpha=0.5)
        ax.set_xlim(0, w)
        ax.set_ylim(h, 0)
        ax.set_title("Trayectorias (coordenadas de imagen)")
    else:
        ax.invert_yaxis()
        ax.set_aspect("equal")
        ax.set_title("Trayectorias (" + ("compensadas, marco de referencia" if session.use_comp
                                          else "SIN compensar camara") + ")")
        ax.grid(alpha=0.3)
    cmap = plt.get_cmap("tab20")
    for tid, pts in longest:
        a = np.array(pts)
        ax.plot(a[:, 1], a[:, 2], color=cmap(tid % 20), lw=1.4)
        ax.scatter(a[-1, 1], a[-1, 2], color=cmap(tid % 20), s=10)
    ax.set_xlabel("X (px)")
    ax.set_ylabel("Y (px)")
    _save(fig, folder / name)
    return True, "", name


def save_objects_by_class(session, folder: Path):
    name = "objects_by_class.png"
    counts = session.classes_count()
    if not counts:
        return False, "sin objetos", None
    items = sorted(counts.items(), key=lambda kv: -kv[1])
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar([k for k, _ in items], [v for _, v in items], color="#3b82f6")
    ax.set_title("Objetos unicos por clase")
    ax.set_ylabel("objetos")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    _save(fig, folder / name)
    return True, "", name


def save_speed_distribution(session, folder: Path):
    name = "speed_distribution.png"
    calibrated = session.calib.valid and session.has("calibration")
    col = "speed_kmh" if calibrated else "speed_px_s"
    vals = [r[col] for r in session.traj_rows if r[col] is not None]
    if not vals:
        return False, "sin muestras de velocidad", None
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(vals, bins=30, color="#10b981", edgecolor="white")
    ax.set_xlabel("velocidad (km/h)" if calibrated else "velocidad (px/s)")
    ax.set_ylabel("muestras")
    ax.set_title("Distribucion de velocidades")
    _save(fig, folder / name)
    return True, "", name


def save_detections_over_time(session, folder: Path):
    name = "detections_over_time.png"
    if not session.intervals:
        return False, "sin datos", None
    iv = session.cfg["interval_s"]
    ks = sorted(session.intervals)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar([k * iv for k in ks], [len(session.intervals[k]["ids"]) for k in ks],
           width=iv * 0.9, align="edge", color="#f59e0b", label="objetos distintos")
    ax.plot([k * iv + iv / 2 for k in ks], [session.intervals[k]["detections"] for k in ks],
            color="#ef4444", marker="o", label="detecciones")
    ax.set_xlabel(f"tiempo (s) - intervalos de {iv:g} s")
    ax.set_title("Objetos detectados por intervalo de tiempo")
    ax.legend()
    _save(fig, folder / name)
    return True, "", name


def save_traffic_flow(session, folder: Path):
    name = "traffic_flow.png"
    flow = flow_per_interval(session)
    if not (session.has("traffic") and flow):
        return False, "sin cruces o perfil sin analitica de transito", None
    iv = session.cfg["interval_s"]
    ks = sorted(flow)
    x = np.arange(len(ks))
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(x - 0.2, [flow[k]["A->B"] for k in ks], 0.4, label="A->B", color="#3b82f6")
    ax.bar(x + 0.2, [flow[k]["B->A"] for k in ks], 0.4, label="B->A", color="#f97316")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{k * iv:g}-{(k + 1) * iv:g}" for k in ks], rotation=30)
    ax.set_xlabel("intervalo (s)")
    ax.set_ylabel("cruces")
    ax.set_title("Flujo vehicular por sentido")
    ax.legend()
    _save(fig, folder / name)
    return True, "", name


def save_crossings_by_hour(session, folder: Path):
    """Cruces unicos de la linea por hora; resalta la(s) hora(s) de mayor transito."""
    name = "crossings_by_hour.png"
    rows, basis = crossings_by_hour(session)
    if not (session.has("traffic") and rows):
        return False, "sin cruces o perfil sin analitica de transito", None
    labels, counts = [r[0] for r in rows], [r[1] for r in rows]
    peak = max(counts)
    colors = ["#ef4444" if c == peak else "#3b82f6" for c in counts]
    fig, ax = plt.subplots(figsize=(max(6, 1.2 * len(rows) + 3), 4.5))
    bars = ax.bar(labels, counts, color=colors)
    for b, c in zip(bars, counts):
        ax.text(b.get_x() + b.get_width() / 2, c, str(c), ha="center", va="bottom")
    ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    ax.set_ylim(0, peak * 1.15)
    ax.set_xlabel(f"Hora - {basis}")
    ax.set_ylabel("cruces unicos de la linea")
    ax.set_title(f"Cruces por hora (total {sum(counts)}; hora pico en rojo)")
    _save(fig, folder / name)
    return True, "", name
