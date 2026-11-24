"""Estado de UNA ejecucion. Se crea al iniciar y se descarta al terminar, de modo que
IDs, trayectorias, contadores y metricas nunca se mezclan entre experimentos."""
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config.settings import PROFILES, RESULTS_DIR
from core.calibration import Calibration
from core.heatmap import HeatMap
from core.line_counter import LineCounter
from core.speed_estimator import SpeedEstimator, SpeedSample
from core.trajectory import TrajectoryStore
from core.video_capture import VideoInfo


class Session:
    def __init__(self, run_cfg: dict, info: VideoInfo, results_dir: Path = RESULTS_DIR):
        self.cfg = dict(run_cfg)
        self.info = info
        self.started_at = datetime.now()
        stem = re.sub(r"[^\w\-]+", "_", Path(info.name).stem or "webcam")[:40]
        self.name = f"{self.started_at.strftime('%Y%m%d_%H%M%S')}_{stem}"
        self.folder = Path(results_dir) / self.name
        self.folder.mkdir(parents=True, exist_ok=True)

        self.mode = run_cfg["mode"]
        self.profile = run_cfg["profile"]
        self.features = PROFILES[self.profile]["features"]
        c = run_cfg
        self.line = LineCounter(c["line_margin_px"], c["line_cooldown_s"])
        self.calib = Calibration()
        self.heat = HeatMap(info.width, info.height, c["heatmap_scale"])
        self.traj = TrajectoryStore(c["tail_length"])
        self.speed = SpeedEstimator(c["speed_window_s"], c["speed_min_dt_s"])

        self.traj_rows: List[dict] = []
        self.det_rows: List[dict] = []
        self.cam_rows: List[dict] = []
        self.obj: Dict[int, dict] = {}
        self.last_sample: Dict[int, SpeedSample] = {}
        self.intervals: Dict[int, dict] = {}
        self.series: List[tuple] = []          # (timestamp, activos, fps)
        self.total_dets = 0
        self.frames_processed = 0
        self.infer_ms_sum = 0.0
        self.fps_sum = 0.0
        self.sum_px = self.max_px = 0.0
        self.n_px = 0
        self.sum_kmh = self.max_kmh = 0.0
        self.n_kmh = 0
        self.active_ids: set = set()
        self.first_ts: Optional[float] = None
        self.last_ts = 0.0
        self.ref_frame = None
        self.cam_invalid_frames = 0
        self._last_seen: Dict[int, float] = {}

    def has(self, feature: str) -> bool:
        return feature in self.features

    @property
    def use_comp(self) -> bool:
        return self.mode == "moving" and self.has("compensation")

    @property
    def speed_basis(self) -> str:
        if self.use_comp:
            return "coordenadas compensadas (marco del fotograma de referencia)"
        if self.mode == "moving":
            return "coordenadas de imagen SIN compensar (incluyen movimiento de camara)"
        return "coordenadas de imagen"

    def set_calibration(self, calib: Calibration):
        self.calib = calib

    # ------------------------------------------------------------------
    def process(self, frame_idx: int, ts: float, tracks: list, infer_ms: float,
                proc_fps: float, comp=None, motion=None, frame=None):
        """Actualiza todos los modulos de analisis con los resultados del tracker."""
        if self.ref_frame is None and frame is not None:
            self.ref_frame = frame.copy()
        if self.first_ts is None:
            self.first_ts = ts
        self.last_ts = ts
        self.frames_processed += 1
        self.total_dets += len(tracks)
        self.infer_ms_sum += infer_ms
        self.fps_sum += proc_fps
        interval = self.cfg["interval_s"]
        iv = self.intervals.setdefault(int(ts // interval), {"detections": 0, "ids": set()})
        iv["detections"] += len(tracks)

        comp_active = self.use_comp and comp is not None
        comp_ok = comp_active and comp.reliable
        if comp_active:
            m = motion
            self.cam_rows.append({
                "frame": frame_idx, "timestamp": ts,
                "dx": m.dx, "dy": m.dy, "rotation_deg": m.rotation_deg, "scale": m.scale,
                "matches": m.matches, "inliers": m.inliers, "inlier_ratio": m.inlier_ratio,
                "reproj_err": m.reproj_err, "valid": bool(m.valid), "reason": m.reason,
                "cum_dx": comp.cum_dx, "cum_dy": comp.cum_dy})
            if not m.valid:
                self.cam_invalid_frames += 1

        use_calib = self.has("calibration") and self.calib.valid
        tol = self.cfg["calib_tolerance_px"]
        self.active_ids = set()
        for tr in tracks:
            tid = tr.track_id
            self.active_ids.add(tid)
            self._last_seen[tid] = ts
            iv["ids"].add(tid)
            cx, cy = tr.center
            wx, wy = (cx, cy)
            xc = yc = None
            if comp_active:
                xc, yc = comp.to_reference((cx, cy))
                wx, wy = xc, yc

            o = self.obj.setdefault(tid, {"cls": tr.cls_name, "first_t": ts, "last_t": ts,
                                          "frames": 0, "sum_px": 0.0, "n_px": 0,
                                          "max_px": 0.0, "sum_kmh": 0.0, "n_kmh": 0,
                                          "max_kmh": None})
            o["last_t"] = ts
            o["frames"] += 1
            self.det_rows.append({"frame": frame_idx, "timestamp": ts, "id": tid,
                                  "class": tr.cls_name, "confidence": round(tr.conf, 4),
                                  "x1": tr.x1, "y1": tr.y1, "x2": tr.x2, "y2": tr.y2})

            sample = SpeedSample()
            if not comp_active or comp_ok:       # sin compensacion confiable no se calcula
                world = None
                if use_calib and self.calib.inside(tr.foot, tol):
                    world = self.calib.to_world(tr.foot)
                if use_calib:
                    # con calibracion la velocidad real usa el punto de contacto con el suelo
                    sample = self.speed.update(tid, ts, (wx, wy), world)
                else:
                    sample = self.speed.update(tid, ts, (wx, wy))
            self.last_sample[tid] = sample
            if sample.px_s is not None:
                self.sum_px += sample.px_s
                self.n_px += 1
                self.max_px = max(self.max_px, sample.px_s)
                o["sum_px"] += sample.px_s
                o["n_px"] += 1
                o["max_px"] = max(o["max_px"], sample.px_s)
            if sample.kmh is not None:
                self.sum_kmh += sample.kmh
                self.n_kmh += 1
                self.max_kmh = max(self.max_kmh, sample.kmh)
                o["sum_kmh"] += sample.kmh
                o["n_kmh"] += 1
                o["max_kmh"] = sample.kmh if o["max_kmh"] is None else max(o["max_kmh"], sample.kmh)

            self.traj.add(tid, tr.cls_name, ts, wx, wy)
            self.traj_rows.append({
                "id": tid, "class": tr.cls_name, "frame": frame_idx, "timestamp": ts,
                "x": cx, "y": cy, "x_comp": xc, "y_comp": yc,
                "speed_px_s": sample.px_s, "speed_kmh": sample.kmh,
                "direction": sample.direction if sample.px_s is not None else None,
                "direction_deg": sample.direction_deg,
                "comp_valid": (bool(comp_ok) if comp_active else None)})

            if self.has("line"):
                self.line.update(tid, tr.cls_name, (cx, cy), ts, frame_idx)
            if self.has("heatmap") and self.mode == "fixed":
                self.heat.add(cx, cy, sample.px_s)

        self.series.append((ts, len(tracks), proc_fps))
        if frame_idx % 120 == 0:
            self._housekeeping(ts)

    def _housekeeping(self, now: float):
        alive = {k for k, t in self._last_seen.items() if now - t < 5.0}
        self.speed.forget(alive)
        self.line.forget(alive)
        self.traj.forget_tails(alive)
        for k in [k for k in self._last_seen if k not in alive]:
            del self._last_seen[k]
            self.last_sample.pop(k, None)

    def reset_counts(self):
        self.line.reset_counts()

    # ------------------------------------------------------------------
    def classes_count(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for o in self.obj.values():
            out[o["cls"]] = out.get(o["cls"], 0) + 1
        return out

    def snapshot(self) -> dict:
        n = max(1, self.frames_processed)
        calibrated = self.calib.valid and self.has("calibration")
        return {
            "unique": len(self.obj), "active": len(self.active_ids),
            "detections": self.total_dets,
            "crossed": self.line.total, "cross_ab": self.line.count_ab,
            "cross_ba": self.line.count_ba,
            "avg_px": (self.sum_px / self.n_px) if self.n_px else None,
            "max_px": self.max_px if self.n_px else None,
            "avg_kmh": (self.sum_kmh / self.n_kmh) if (calibrated and self.n_kmh) else None,
            "max_kmh": self.max_kmh if (calibrated and self.n_kmh) else None,
            "calibrated": calibrated,
            "fps": self.fps_sum / n, "infer_ms": self.infer_ms_sum / n,
            "frames": self.frames_processed, "t": self.last_ts,
        }
