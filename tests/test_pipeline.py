"""Flujo completo (hilo + sesion + exportacion) con videos sinteticos. python -m tests.test_pipeline"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QCoreApplication

import config.settings as S
from config.settings import DEFAULT_RUN
from core.calibration import Calibration
from core.pipeline import ProcessingThread
from tests.fake_detector import factory
from tests.test_logic import _textured

app = QCoreApplication.instance() or QCoreApplication(sys.argv)
TMP = Path(tempfile.mkdtemp())


def make_fixed(path, w=640, h=480, fps=25, secs=6):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
    for i in range(fps * secs):
        t = i / fps
        f = np.full((h, w, 3), 90, np.uint8)
        x1 = int(60 + 90 * t)                  # rojo: 90 px/s hacia la derecha (cruza x=320)
        x2 = int(580 - 90 * t)                 # azul: 90 px/s hacia la izquierda
        cv2.rectangle(f, (x1, 100), (x1 + 50, 150), (0, 0, 255), -1)
        cv2.rectangle(f, (x2, 300), (x2 + 50, 350), (255, 0, 0), -1)
        vw.write(f)
    vw.release()


def make_moving(path, fps=25, secs=4):
    big = cv2.cvtColor(cv2.cvtColor(_textured(1500, 800, 3), cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (640, 480))
    truth = []
    for i in range(fps * secs):
        t = i / fps
        ox, oy = int(100 + 120 * t), int(80 + 40 * t)          # paneo de la camara
        f = big[oy:oy + 480, ox:ox + 640].copy()
        wx, wy = 500 + 30 * t, 350                              # objeto: 30 px/s REALES en x
        cv2.rectangle(f, (int(wx - ox), int(wy - oy)), (int(wx - ox) + 50, int(wy - oy) + 50),
                      (0, 255, 0), -1)
        vw.write(f)
    vw.release()


def run(cfg_over, live_over, path, calib=None):
    cfg = {"source_kind": "file", "path": str(path), "cam_index": 0, "model": "fake.pt",
           "tracker": "ByteTrack", "imgsz": 640, "frame_skip": 1, "classes": None, "results_dir": str(TMP / "results"),
           **{k: v for k, v in DEFAULT_RUN.items() if k not in ("imgsz", "frame_skip")}, **cfg_over}
    live = {"conf": 0.3, "iou": 0.5, "show_boxes": True, "show_ids": True, "show_conf": True,
            "show_traj": True, "traj_mode": "all", "traj_id": 0, "show_speed": True,
            "show_orb": True, "line": None, "line_enabled": True, "save_video": True,
            "export_pdf": True, **live_over}
    th = ProcessingThread(cfg, live, calib, factory)
    th.set_speed(0.0)                          # lo mas rapido posible
    got = {"frames": 0, "err": [], "fin": None}
    from PySide6.QtCore import Qt
    th.frame_ready.connect(lambda f: (got.__setitem__("frames", got["frames"] + 1), th.ack_frame()),
                           Qt.ConnectionType.DirectConnection)
    th.error.connect(lambda m: got["err"].append(m), Qt.ConnectionType.DirectConnection)
    th.session_finished.connect(lambda d, s: got.__setitem__("fin", (d, s)),
                                Qt.ConnectionType.DirectConnection)
    th.start()
    th.wait(120000)
    assert not got["err"], got["err"]
    assert got["fin"], "no hubo session_finished"
    return Path(got["fin"][0]), got


def test_fixed():
    v = TMP / "fixed.avi"
    make_fixed(v)
    cal = Calibration()   # rectangulo en el suelo: 640px de ancho ~ 16 m -> 40 px/m (plano frontal)
    cal.set([(0, 0), (640, 0), (640, 480), (0, 480)], 16.0, 12.0)
    folder, got = run({"mode": "fixed", "profile": "radar"},
                      {"line": ((320, 0), (320, 480))}, v, cal)
    s = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert s["status"] == "completada"
    assert s["total_unique_objects"] == 2, s["total_unique_objects"]
    assert s["crossings"]["total"] == 2 and s["crossings"]["A->B"] == 1 and s["crossings"]["B->A"] == 1, s["crossings"]
    assert abs(s["speed"]["avg_px_s"] - 90) < 8, s["speed"]
    assert abs(s["speed"]["avg_kmh"] - 90 / 40 * 3.6) < 1.0, s["speed"]      # 2.25 m/s = 8.1 km/h
    for f in ("trajectories.csv", "detections.csv", "crossings.csv", "configuration.json",
              "objects.csv", "heatmap_density.png", "heatmap_motion.png", "trajectories.png",
              "objects_by_class.png", "speed_distribution.png", "detections_over_time.png",
              "processed.mp4", "report.pdf"):
        assert (folder / f).exists() and (folder / f).stat().st_size > 0, f
    assert not (folder / "camera_motion.csv").exists()
    print("FIJA OK ->", got["frames"], "fotogramas a la UI;",
          "cruces", s["crossings"]["total"], "| vel prom", round(s["speed"]["avg_px_s"], 1), "px/s",
          round(s["speed"]["avg_kmh"], 2), "km/h")
    print("   no disponible:", s["not_available"])


def test_fixed_without_calibration():
    folder, _ = run({"mode": "fixed", "profile": "motion"}, {"line": ((320, 0), (320, 480))},
                    TMP / "fixed.avi")
    s = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert s["speed"]["avg_kmh"] is None and "velocidad_real_kmh" in s["not_available"]
    print("SIN CALIBRACION OK: velocidad real = null y registrada como no disponible")


def test_moving():
    v = TMP / "moving.avi"
    make_moving(v)
    folder, got = run({"mode": "moving", "profile": "compensation"}, {}, v)
    s = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    import pandas as pd
    cm = pd.read_csv(folder / "camera_motion.csv")
    tr = pd.read_csv(folder / "trajectories.csv")
    valid_ratio = cm["valid"].mean()
    t = tr.dropna(subset=["x_comp", "speed_px_s"])
    raw_speed = t["speed_px_s"].mean()
    # velocidad calculada sobre coordenadas compensadas debe aproximar los 30 px/s reales
    assert valid_ratio > 0.9, valid_ratio
    assert abs(raw_speed - 30) < 8, raw_speed
    # sin compensar, el objeto parece moverse ~120 px/s (la camara se mueve 120 px/s)
    raw = tr.sort_values("frame")
    nocomp = np.hypot(np.diff(raw["x"]), np.diff(raw["y"])).mean() * 25
    assert nocomp > 60, nocomp
    print(f"MOVIL OK -> validez {valid_ratio:.0%}; vel. compensada {raw_speed:.1f} px/s "
          f"(real 30); vel. aparente sin compensar {nocomp:.1f} px/s")


if __name__ == "__main__":
    try:
        test_fixed()
        test_fixed_without_calibration()
        test_moving()
        print("TODAS LAS PRUEBAS DE PIPELINE PASARON")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
