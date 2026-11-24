"""Detector simulado para pruebas: detecta rectangulos de color saturado (sin YOLO)."""
import cv2
import numpy as np
from core.tracker import Track

COLORS = {1: (0, 0, 255), 2: (255, 0, 0), 3: (0, 255, 0)}   # BGR -> id
TOL = 70


class FakeDetector:
    def track(self, frame, conf, iou, imgsz, classes):
        out = []
        for tid, col in COLORS.items():
            c = np.array(col, np.int32)
            lo = np.clip(c - TOL, 0, 255).astype(np.uint8)
            hi = np.clip(c + TOL, 0, 255).astype(np.uint8)
            mask = cv2.inRange(frame, lo, hi)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
            n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
            if n > 1:
                k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
                x, y, w, h, a = stats[k]
                if a > 300:
                    out.append(Track(tid, 2, "car", 0.9, float(x), float(y),
                                     float(x + w - 1), float(y + h - 1)))
        return out


def factory(_cfg):
    return FakeDetector()
