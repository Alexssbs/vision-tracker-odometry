"""Fuente de video unificada (archivo o webcam) con timestamps reales."""
import sys
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np


@dataclass
class VideoInfo:
    kind: str = "file"          # "file" | "webcam"
    name: str = ""
    path: str = ""
    width: int = 0
    height: int = 0
    fps: float = 0.0
    frames: int = 0
    duration: float = 0.0

    def as_dict(self):
        return dict(self.__dict__)


class VideoSource:
    """Abre un archivo o una webcam. ``read`` devuelve (ok, frame, timestamp_s, indice).

    Archivos: timestamp tomado de CAP_PROP_POS_MSEC (si es monotono); si el backend
    no lo entrega bien se usa indice/fps. Webcam: reloj monotonico.
    """

    def __init__(self, kind: str, path: str = "", cam_index: int = 0):
        self.kind, self.path, self.cam_index = kind, path, cam_index
        self.cap: Optional[cv2.VideoCapture] = None
        self.info = VideoInfo(kind=kind)
        self._idx = -1
        self._last_ts = -1.0
        self._t0 = 0.0

    def open(self) -> VideoInfo:
        if self.kind == "webcam":
            backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
            self.cap = cv2.VideoCapture(self.cam_index, backend)
            name = f"Webcam {self.cam_index}"
        else:
            self.cap = cv2.VideoCapture(self.path)
            name = self.path.replace("\\", "/").split("/")[-1]
        if self.cap is None or not self.cap.isOpened():
            self.release()
            what = f"la cámara {self.cam_index}" if self.kind == "webcam" else self.path
            raise IOError(f"No se pudo abrir {what}.")
        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)
        n = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if self.kind == "webcam":
            n = 0
        if fps <= 1e-3 or fps > 1000:
            fps = 30.0 if self.kind == "file" else 0.0
        self.info = VideoInfo(self.kind, name, self.path, w, h, fps, max(n, 0),
                              (n / fps) if (n > 0 and fps > 0) else 0.0)
        self._t0 = time.perf_counter()
        self._idx = -1
        return self.info

    def read(self) -> Tuple[bool, Optional[np.ndarray], float, int]:
        if self.cap is None:
            return False, None, 0.0, self._idx
        ok, frame = self.cap.read()
        if not ok or frame is None:
            return False, None, 0.0, self._idx
        self._idx += 1
        if self.kind == "webcam":
            ts = time.perf_counter() - self._t0
        else:
            ts = self.cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if self._idx > 0 and ts <= self._last_ts:      # backend no fiable
                ts = self._idx / self.info.fps
            elif self._idx == 0 and ts < 0:
                ts = 0.0
        self._last_ts = ts
        return True, frame, ts, self._idx

    def release(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None


def read_preview(path: str):
    """Lee el primer fotograma de un archivo y su informacion (para vista previa)."""
    src = VideoSource("file", path)
    info = src.open()
    ok, frame, _, _ = src.read()
    src.release()
    return info, (frame if ok else None)
