"""Mapas de calor: densidad de posiciones e intensidad de movimiento."""
import cv2
import numpy as np


class HeatMap:
    """Acumula posiciones en una rejilla de baja resolucion.

    * density: cuantas veces se observaron objetos en cada celda.
    * motion: suma de velocidades (px/s) observadas en cada celda -> intensidad
      de movimiento (zonas donde los objetos se mueven rapido, no solo donde estan).
    """

    def __init__(self, width: int, height: int, scale: float = 0.25):
        self.w, self.h = width, height
        self.scale = scale
        self.gw, self.gh = max(8, int(width * scale)), max(8, int(height * scale))
        self.density = np.zeros((self.gh, self.gw), np.float32)
        self.motion = np.zeros((self.gh, self.gw), np.float32)
        self.has_motion = False

    def reset(self):
        self.density[:] = 0
        self.motion[:] = 0
        self.has_motion = False

    def add(self, x: float, y: float, speed_px_s=None):
        gx, gy = int(x * self.scale), int(y * self.scale)
        if 0 <= gx < self.gw and 0 <= gy < self.gh:
            self.density[gy, gx] += 1.0
            if speed_px_s is not None:
                self.motion[gy, gx] += float(speed_px_s)
                self.has_motion = True

    def normalized(self, kind: str = "density") -> np.ndarray:
        grid = self.density if kind == "density" else self.motion
        sigma = max(1.5, 0.02 * max(self.gw, self.gh))
        blur = cv2.GaussianBlur(grid, (0, 0), sigma)
        m = float(blur.max())
        return blur / m if m > 0 else blur

    def render(self, background=None, kind: str = "density", alpha: float = 0.6):
        """Devuelve una imagen BGR del tamano original con el mapa superpuesto."""
        norm = cv2.resize(self.normalized(kind), (self.w, self.h), interpolation=cv2.INTER_CUBIC)
        norm = np.clip(norm, 0, 1)
        color = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_JET)
        if background is None:
            background = np.zeros((self.h, self.w, 3), np.uint8)
        out = background.copy()
        a = (alpha * np.clip(norm * 4, 0, 1))[..., None]      # transparente donde no hay datos
        return (out * (1 - a) + color * a).astype(np.uint8)
