"""Hilo de procesamiento (QThread): captura -> YOLO+tracker (1 vez) -> analisis -> render.

La interfaz nunca ejecuta trabajo pesado: recibe fotogramas ya dibujados y metricas
mediante senales. Los ajustes "en vivo" se actualizan con ``update_live``.
"""
import copy
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional

import cv2
from PySide6.QtCore import QMutex, QThread, Signal

from config.settings import RESULTS_DIR
from analytics.exporter import export_session, write_configuration, write_initial_summary
from core.calibration import Calibration
from core.renderer import render_frame
from core.session import Session
from core.video_capture import VideoSource
from odometry.camera_compensation import CameraCompensator


class ProcessingThread(QThread):
    frame_ready = Signal(object)        # np.ndarray BGR (tamano original, ya anotado)
    stats_ready = Signal(dict)          # tarjetas de estadisticas
    info_ready = Signal(dict)           # informacion del video
    events_ready = Signal(list)         # nuevos cruces de linea
    camera_ready = Signal(dict)         # movimiento de camara por fotograma
    views_ready = Signal(object, object)  # (imagen mapa de calor, paths de trayectorias)
    state_changed = Signal(str)         # "ejecutando" | "pausado" | "detenido" ...
    session_finished = Signal(str, str)  # (carpeta, estado)
    error = Signal(str)

    def __init__(self, run_cfg: dict, live_cfg: dict, calibration: Optional[Calibration] = None,
                 detector_factory: Optional[Callable] = None, parent=None):
        super().__init__(parent)
        self.run_cfg = dict(run_cfg)
        self._live = dict(live_cfg)
        self._calib = calibration
        self._detector_factory = detector_factory
        self._mutex = QMutex()
        self._stop = False
        self._paused = False
        self._step = False
        self._redraw = False
        self._pending = False           # hay un fotograma sin consumir por la UI
        self._speed = 1.0
        self._reset_counts = False
        self.session: Optional[Session] = None
        self.folder = ""

    # ---------- control desde la UI (hilo principal) ----------
    def update_live(self, live_cfg: dict):
        self._mutex.lock()
        self._live = dict(live_cfg)
        self._redraw = True
        self._mutex.unlock()

    def set_speed(self, factor: float):
        self._speed = factor

    def pause(self):
        self._paused = True
        self.state_changed.emit("pausado")

    def resume(self):
        self._paused = False
        self.state_changed.emit("ejecutando")

    def step(self):
        self._paused = True
        self._step = True

    def stop(self):
        self._stop = True

    def ack_frame(self):
        self._pending = False

    def request_reset_counts(self):
        self._reset_counts = True

    @property
    def paused(self) -> bool:
        return self._paused

    def _get_live(self) -> dict:
        self._mutex.lock()
        d = copy.deepcopy(self._live)
        self._mutex.unlock()
        return d

    # ---------- hilo ----------
    def run(self):
        try:
            self._run_loop_wrapper()
        except Exception as e:                              # nunca dejar caer la UI
            self.error.emit(f"{type(e).__name__}: {e}")
            if self.folder:
                self.session_finished.emit(self.folder, "error")
        finally:
            self.state_changed.emit("detenido")

    def _run_loop_wrapper(self) -> str:
        c = self.run_cfg
        src = VideoSource(c["source_kind"], c.get("path", ""), c.get("cam_index", 0))
        writer = None
        status = "completada"
        t_wall0 = time.perf_counter()
        sess = None
        try:
            info = src.open()
            self.info_ready.emit(info.as_dict())
            self.state_changed.emit("cargando modelo")
            det = (self._detector_factory(c) if self._detector_factory
                   else _default_detector(c))
            sess = self.session = Session(c, info, Path(c["results_dir"]) if c.get("results_dir") else RESULTS_DIR)
            self.folder = str(sess.folder)
            if self._calib is not None and self._calib.valid and sess.has("calibration"):
                sess.set_calibration(self._calib)
            comp = CameraCompensator() if sess.use_comp else None
            if comp is not None:
                sess.cfg["orb"] = "ORB+BFMatcher+RANSAC(similitud 2D)"
            write_configuration(sess)
            write_initial_summary(sess)
            extra = []

            live = self._get_live()
            self._apply_live(sess, live)
            fps_win = deque(maxlen=30)
            last_views = 0.0
            skip = max(1, int(c["frame_skip"]))
            last_render = None          # (frame, tracks, motion) para redibujar en pausa
            nev = 0
            self.state_changed.emit("ejecutando")
            t_prev_loop = time.perf_counter()

            while not self._stop:
                if self._paused and not self._step:
                    if self._redraw and last_render is not None:
                        self._redraw = False
                        live = self._get_live()
                        self._apply_live(sess, live)
                        self._emit_frame(last_render, sess, live, comp)
                    self.msleep(30)
                    continue
                self._step = False
                if self._reset_counts:
                    sess.reset_counts()
                    self._reset_counts = False

                ok, frame, ts, idx = src.read()
                if not ok:
                    if c["source_kind"] == "webcam":
                        self.error.emit("Se perdió la señal de la cámara.")
                        status = "error"
                    break
                if idx % skip != 0:
                    continue

                t0 = time.perf_counter()
                live = self._get_live()
                self._apply_live(sess, live)
                tracks = det.track(frame, live["conf"], live["iou"], c["imgsz"], c["classes"])
                infer_ms = (time.perf_counter() - t0) * 1000.0

                motion = None
                if comp is not None:
                    motion = comp.update(frame, [t.box for t in tracks])
                    self.camera_ready.emit({"t": ts, "dx": comp.cum_dx, "dy": comp.cum_dy,
                                            "valid": motion.valid, "inliers": motion.inliers,
                                            "matches": motion.matches, "reason": motion.reason})

                now = time.perf_counter()
                fps_win.append(now - t_prev_loop)
                t_prev_loop = now
                fps = len(fps_win) / sum(fps_win) if sum(fps_win) > 0 else 0.0
                sess.process(idx, ts, tracks, infer_ms, fps, comp, motion, frame)

                rendered = render_frame(frame, tracks, sess, live, comp, motion)
                last_render = (frame, tracks, motion)
                if not self._pending:
                    self._pending = True
                    self.frame_ready.emit(rendered)
                if live.get("save_video"):
                    if writer is None:
                        h, w = rendered.shape[:2]
                        out_fps = info.fps if info.fps > 0 else max(1.0, fps)
                        writer = cv2.VideoWriter(str(sess.folder / "processed.mp4"),
                                                 cv2.VideoWriter_fourcc(*"mp4v"), out_fps, (w, h))
                        extra.append("processed.mp4")
                    writer.write(rendered)

                snap = sess.snapshot()
                snap["fps"] = fps
                snap["infer_ms"] = infer_ms
                self.stats_ready.emit(snap)
                if len(sess.line.events) > nev:
                    self.events_ready.emit(sess.line.events[nev:])
                    nev = len(sess.line.events)
                if now - last_views > 1.0:
                    last_views = now
                    heat = (sess.heat.render(sess.ref_frame, "density")
                            if sess.has("heatmap") and sess.mode == "fixed" else None)
                    paths = {k: list(v) for k, v in sess.traj.paths.items()
                             if k in sess.active_ids}
                    self.views_ready.emit(heat, paths)

                # velocidad de reproduccion (solo archivos)
                if c["source_kind"] == "file" and self._speed > 0 and info.fps > 0:
                    target = (skip / info.fps) / self._speed
                    spent = time.perf_counter() - t0
                    if spent < target:
                        self.msleep(int((target - spent) * 1000))
            if self._stop:
                status = "detenida"
            if writer is not None:
                writer.release()
                writer = None
            sess_summary_files = extra
            if sess.frames_processed > 0:
                export_session(sess, status, time.perf_counter() - t_wall0,
                               bool(self._get_live().get("export_pdf")), sess_summary_files)
            self.session_finished.emit(self.folder, status)
        except Exception:
            status = "error"
            if sess is not None:
                try:
                    export_session(sess, "error", time.perf_counter() - t_wall0, False)
                except Exception:
                    pass
            raise
        finally:
            if writer is not None:
                writer.release()
            src.release()
        return status

    def _apply_live(self, sess: Session, live: dict):
        ln = live.get("line")
        if ln:
            cur = (sess.line.p1, sess.line.p2)
            new = (tuple(ln[0]), tuple(ln[1]))
            if cur != new:
                sess.line.set_line(*new)
        sess.line.enabled = bool(live.get("line_enabled", True))
        if sess.profile == "radar" and "speed_limit_kmh" in live:
            sess.cfg["speed_limit_kmh"] = live["speed_limit_kmh"]   # ultimo limite usado

    def _emit_frame(self, last, sess, live, comp):
        frame, tracks, motion = last
        self.frame_ready.emit(render_frame(frame, tracks, sess, live, comp, motion))


def _default_detector(c: dict):
    from core.detector import YoloTracker
    return YoloTracker(c["model"], c["tracker"]).load()
