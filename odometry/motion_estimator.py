"""Estimacion robusta (RANSAC) del movimiento global 2D entre fotogramas."""
import math
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from config.settings import ORB


@dataclass
class MotionResult:
    valid: bool = False
    reason: str = ""
    M: Optional[np.ndarray] = None        # 2x3, mapea puntos del fotograma previo al actual
    matches: int = 0
    inliers: int = 0
    inlier_ratio: float = 0.0
    dx: float = 0.0                       # desplazamiento aparente del centro de la imagen
    dy: float = 0.0
    rotation_deg: float = 0.0
    scale: float = 1.0
    reproj_err: float = 0.0
    src: np.ndarray = field(default_factory=lambda: np.zeros((0, 2), np.float32))
    dst: np.ndarray = field(default_factory=lambda: np.zeros((0, 2), np.float32))
    inlier_mask: np.ndarray = field(default_factory=lambda: np.zeros(0, bool))


def estimate_motion(src: np.ndarray, dst: np.ndarray, frame_size, cfg=ORB) -> MotionResult:
    """Transformacion de similitud (traslacion+rotacion+escala uniforme) con RANSAC.

    Se valida con: minimo de correspondencias e inliers, proporcion de inliers,
    escala plausible y error de reproyeccion. Si falla, ``valid=False`` y el
    llamador NO debe aplicar la correccion.
    """
    r = MotionResult(matches=len(src), src=src, dst=dst)
    if len(src) < cfg["min_matches"]:
        r.reason = f"pocas correspondencias ({len(src)}<{cfg['min_matches']})"
        return r
    M, mask = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                          ransacReprojThreshold=cfg["ransac_thresh"],
                                          maxIters=2000, confidence=0.99)
    if M is None or mask is None:
        r.reason = "RANSAC sin solucion"
        return r
    mask = mask.ravel().astype(bool)
    r.inlier_mask = mask
    r.inliers = int(mask.sum())
    r.inlier_ratio = r.inliers / max(1, len(src))
    r.M = M
    r.scale = float(math.hypot(M[0, 0], M[1, 0]))
    r.rotation_deg = float(math.degrees(math.atan2(M[1, 0], M[0, 0])))
    w, h = frame_size
    c = np.array([w / 2.0, h / 2.0, 1.0])
    r.dx, r.dy = float(M[0] @ c - c[0]), float(M[1] @ c - c[1])
    if r.inliers:
        proj = (src[mask] @ M[:, :2].T) + M[:, 2]
        r.reproj_err = float(np.mean(np.linalg.norm(proj - dst[mask], axis=1)))
    if r.inliers < cfg["min_inliers"]:
        r.reason = f"pocos inliers ({r.inliers}<{cfg['min_inliers']})"
    elif r.inlier_ratio < cfg["min_inlier_ratio"]:
        r.reason = f"proporcion de inliers baja ({r.inlier_ratio:.2f})"
    elif abs(r.scale - 1.0) > cfg["max_scale_dev"]:
        r.reason = f"escala implausible ({r.scale:.2f})"
    elif r.reproj_err > cfg["max_reproj_err"]:
        r.reason = f"error de reproyeccion alto ({r.reproj_err:.1f}px)"
    else:
        r.valid, r.reason = True, "ok"
    return r
