"""Extraccion de caracteristicas ORB del entorno (excluyendo las cajas de objetos)."""
from dataclasses import dataclass
from typing import Optional, Sequence

import cv2
import numpy as np

from config.settings import ORB


@dataclass
class Features:
    pts: np.ndarray                 # (N,2) float32, coordenadas del fotograma original
    des: Optional[np.ndarray]       # descriptores ORB (N,32) o None


class FeatureExtractor:
    """ORB sobre imagen reducida y con mascara que excluye objetos detectados.

    Usar solo el fondo evita que objetos dinamicos (autos, personas) contaminen la
    estimacion del movimiento de la camara.
    """

    def __init__(self, cfg=ORB):
        self.cfg = cfg
        self.orb = cv2.ORB_create(nfeatures=cfg["n_features"], fastThreshold=12)

    def extract(self, frame_bgr: np.ndarray, boxes: Sequence = ()) -> Features:
        h, w = frame_bgr.shape[:2]
        s = min(1.0, self.cfg["proc_width"] / float(w))
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        if s < 1.0:
            gray = cv2.resize(gray, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        gh, gw = gray.shape
        mask = np.full((gh, gw), 255, np.uint8)
        pad = self.cfg["box_padding"]
        for (x1, y1, x2, y2) in boxes:
            bw, bh = (x2 - x1) * pad, (y2 - y1) * pad
            a, b = int(max(0, (x1 - bw) * s)), int(max(0, (y1 - bh) * s))
            c, d = int(min(gw, (x2 + bw) * s)), int(min(gh, (y2 + bh) * s))
            mask[b:d, a:c] = 0
        kps, des = self.orb.detectAndCompute(gray, mask)
        if not kps or des is None:
            return Features(np.zeros((0, 2), np.float32), None)
        pts = np.array([k.pt for k in kps], np.float32) / s
        return Features(pts, des)
