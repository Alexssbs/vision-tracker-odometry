"""Correspondencia de descriptores ORB entre fotogramas consecutivos."""
from typing import Tuple

import cv2
import numpy as np

from config.settings import ORB
from odometry.feature_extractor import Features


class FeatureMatcher:
    """BFMatcher (Hamming) con prueba de razon de Lowe."""

    def __init__(self, cfg=ORB):
        self.ratio = cfg["ratio"]
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING)

    def match(self, prev: Features, curr: Features) -> Tuple[np.ndarray, np.ndarray]:
        """Devuelve (puntos_prev, puntos_curr) de las correspondencias aceptadas."""
        empty = np.zeros((0, 2), np.float32)
        if prev.des is None or curr.des is None or len(prev.des) < 2 or len(curr.des) < 2:
            return empty, empty
        pairs = self.bf.knnMatch(prev.des, curr.des, k=2)
        src, dst = [], []
        for p in pairs:
            if len(p) == 2 and p[0].distance < self.ratio * p[1].distance:
                src.append(prev.pts[p[0].queryIdx])
                dst.append(curr.pts[p[0].trainIdx])
        if not src:
            return empty, empty
        return np.array(src, np.float32), np.array(dst, np.float32)
