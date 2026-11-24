"""Compensacion 2D del movimiento de camara respecto a un fotograma de referencia.

IMPORTANTE: esto NO es odometria visual 3D. Es una aproximacion en el plano de la
imagen (similitud 2D) valida si el fondo es aproximadamente plano o lejano.
Distingue el movimiento aparente causado por la camara del movimiento propio de
los objetos: una coordenada compensada es la posicion del objeto expresada en el
sistema del fotograma de referencia.
"""
from typing import Optional, Sequence, Tuple

import cv2
import numpy as np

from config.settings import ORB
from odometry.feature_extractor import FeatureExtractor, Features
from odometry.feature_matcher import FeatureMatcher
from odometry.motion_estimator import MotionResult, estimate_motion


def _to3(M: np.ndarray) -> np.ndarray:
    return np.vstack([M, [0, 0, 1]])


class CameraCompensator:
    """Acumula T (actual -> referencia). Si una estimacion no es confiable, NO se
    aplica y se conserva la ultima transformacion valida (marcando el fotograma)."""

    def __init__(self, cfg=ORB):
        self.cfg = cfg
        self.extractor = FeatureExtractor(cfg)
        self.matcher = FeatureMatcher(cfg)
        self.reset()

    def reset(self):
        self.T = np.eye(3)               # actual -> referencia
        self.prev: Optional[Features] = None
        self.last: MotionResult = MotionResult(valid=True, reason="referencia")
        self.curr: Optional[Features] = None
        self.consecutive_invalid = 0
        self.cum_dx = self.cum_dy = 0.0   # movimiento acumulado del centro (ref -> actual)

    @property
    def reliable(self) -> bool:
        return self.last.valid

    def update(self, frame_bgr: np.ndarray, boxes: Sequence = ()) -> MotionResult:
        h, w = frame_bgr.shape[:2]
        feats = self.extractor.extract(frame_bgr, boxes)
        if self.prev is None:
            res = MotionResult(valid=True, reason="fotograma de referencia")
            res.M = np.array([[1, 0, 0], [0, 1, 0]], np.float64)
        else:
            src, dst = self.matcher.match(self.prev, feats)
            res = estimate_motion(src, dst, (w, h), self.cfg)
            if res.valid:
                self.T = self.T @ np.linalg.inv(_to3(res.M))
                self.consecutive_invalid = 0
            else:
                self.consecutive_invalid += 1     # no se aplica la correccion
        self.prev, self.curr, self.last = feats, feats, res
        c = self.to_current((w / 2.0, h / 2.0))
        self.cum_dx, self.cum_dy = c[0] - w / 2.0, c[1] - h / 2.0
        return res

    def to_reference(self, pt: Tuple[float, float]) -> Tuple[float, float]:
        p = self.T @ np.array([pt[0], pt[1], 1.0])
        return float(p[0]), float(p[1])

    def to_current(self, pt_ref: Tuple[float, float]) -> Tuple[float, float]:
        p = np.linalg.inv(self.T) @ np.array([pt_ref[0], pt_ref[1], 1.0])
        return float(p[0]), float(p[1])

    def reference_outline(self, w: int, h: int) -> np.ndarray:
        """Contorno del fotograma de referencia visto desde el fotograma actual."""
        corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32)
        return np.array([self.to_current(tuple(c)) for c in corners], np.float32)

    def draw_overlay(self, canvas: np.ndarray, show_points=True, show_matches=True):
        """Dibuja puntos ORB, correspondencias (vectores de flujo) y la transformacion."""
        h, w = canvas.shape[:2]
        s = max(1.0, max(w, h) / 960.0)
        r = self.last
        ok = r.valid
        if show_points and self.curr is not None:
            for p in self.curr.pts[:600]:
                cv2.circle(canvas, (int(p[0]), int(p[1])), max(1, int(s)), (255, 200, 0), -1)
        if show_matches and len(r.src):
            idx = np.arange(len(r.src))[:150]
            for i in idx:
                inl = i < len(r.inlier_mask) and r.inlier_mask[i]
                col = (0, 220, 0) if inl else (0, 0, 220)
                cv2.line(canvas, tuple(int(v) for v in r.src[i]),
                         tuple(int(v) for v in r.dst[i]), col, 1, cv2.LINE_AA)
        if ok:
            poly = self.reference_outline(w, h).astype(np.int32)
            cv2.polylines(canvas, [poly], True, (255, 255, 0), max(1, int(s)), cv2.LINE_AA)
        txt = (f"Camara dx={r.dx:+.1f} dy={r.dy:+.1f} rot={r.rotation_deg:+.2f} "
               f"inl={r.inliers}/{r.matches}") if r.matches else "Camara: referencia"
        cv2.putText(canvas, txt, (10, int(h - 12 * s)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5 * s, (0, 255, 255) if ok else (0, 0, 255), max(1, int(s)), cv2.LINE_AA)
        if not ok:
            msg = f"COMPENSACION NO CONFIABLE: {r.reason}"
            cv2.rectangle(canvas, (0, 0), (w, int(34 * s)), (0, 0, 160), -1)
            cv2.putText(canvas, msg, (10, int(24 * s)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6 * s, (255, 255, 255), max(1, int(s)), cv2.LINE_AA)
