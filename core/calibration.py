"""Calibracion espacial por homografia (plano del suelo) para velocidades reales."""
from typing import Optional, Tuple

import cv2
import numpy as np


class Calibration:
    """Homografia imagen -> plano del suelo en metros.

    El usuario marca 4 puntos del suelo que forman un rectangulo real de
    ``width_m`` x ``length_m`` en este orden: sup-izq, sup-der, inf-der, inf-izq
    (tal como se ven en la imagen). Solo es valida sobre el plano del suelo, por
    eso las velocidades usan el punto de contacto (centro inferior de la caja).
    """

    def __init__(self):
        self.clear()

    def clear(self):
        self.image_pts: Optional[np.ndarray] = None
        self.width_m = 0.0
        self.length_m = 0.0
        self.H: Optional[np.ndarray] = None

    @property
    def valid(self) -> bool:
        return self.H is not None

    def set(self, image_pts, width_m: float, length_m: float):
        pts = np.asarray(image_pts, dtype=np.float32).reshape(4, 2)
        if width_m <= 0 or length_m <= 0:
            raise ValueError("Las dimensiones reales deben ser mayores que cero.")
        if cv2.contourArea(pts) < 100 or not cv2.isContourConvex(pts.reshape(-1, 1, 2)):
            raise ValueError("Los 4 puntos deben formar un cuadrilatero convexo "
                             "(orden: sup-izq, sup-der, inf-der, inf-izq).")
        world = np.array([[0, 0], [width_m, 0], [width_m, length_m], [0, length_m]],
                         dtype=np.float32)
        self.H = cv2.getPerspectiveTransform(pts, world)
        self.image_pts, self.width_m, self.length_m = pts, float(width_m), float(length_m)

    def to_world(self, pt: Tuple[float, float]) -> Tuple[float, float]:
        p = cv2.perspectiveTransform(np.array([[pt]], dtype=np.float32), self.H)[0, 0]
        return float(p[0]), float(p[1])

    def inside(self, pt: Tuple[float, float], tol_px: float = 20.0) -> bool:
        if not self.valid:
            return False
        poly = self.image_pts.reshape(-1, 1, 2)
        return cv2.pointPolygonTest(poly, (float(pt[0]), float(pt[1])), True) >= -tol_px

    def to_dict(self):
        if not self.valid:
            return None
        return {"image_pts": self.image_pts.tolist(), "width_m": self.width_m,
                "length_m": self.length_m}

    @classmethod
    def from_dict(cls, d):
        c = cls()
        if d:
            c.set(d["image_pts"], d["width_m"], d["length_m"])
        return c
