"""Velocidad con timestamps reales (px/s y, si hay calibracion valida, m/s)."""
import math
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple

ARROWS = ["→", "↗", "↑", "↖", "←", "↙", "↓", "↘"]


@dataclass
class SpeedSample:
    px_s: Optional[float] = None
    mps: Optional[float] = None          # None si no hay calibracion valida / fuera de zona
    direction_deg: Optional[float] = None   # 0=derecha, 90=arriba (sentido antihorario)
    direction: str = "sin datos"

    @property
    def kmh(self) -> Optional[float]:
        return None if self.mps is None else self.mps * 3.6


def direction_label(dx: float, dy: float, min_move: float = 2.0):
    """Devuelve (grados, flecha) a partir del desplazamiento en imagen (y hacia abajo)."""
    if math.hypot(dx, dy) < min_move:
        return None, "quieto"
    deg = math.degrees(math.atan2(-dy, dx)) % 360.0
    return deg, ARROWS[int(((deg + 22.5) % 360) // 45)]


class SpeedEstimator:
    """Estima velocidad por ID sobre una ventana temporal corta y la suaviza (EMA).

    No supone FPS constante: usa la diferencia real de timestamps.
    """

    def __init__(self, window_s=0.5, min_dt_s=0.2, ema=0.5, noise_px=1.0):
        self.window_s, self.min_dt_s, self.ema, self.noise_px = window_s, min_dt_s, ema, noise_px
        self._hist: Dict[int, Deque[Tuple]] = {}
        self._smooth: Dict[int, float] = {}
        self._smooth_m: Dict[int, float] = {}

    def update(self, tid: int, t: float, xy, world_xy: Optional[Tuple[float, float]] = None
               ) -> SpeedSample:
        dq = self._hist.setdefault(tid, deque())
        dq.append((t, xy[0], xy[1], world_xy))
        while len(dq) >= 2 and (t - dq[1][0]) >= self.window_s:
            dq.popleft()
        t0, x0, y0, w0 = dq[0]
        dt = t - t0
        if dt < self.min_dt_s:
            return SpeedSample()
        dx, dy = xy[0] - x0, xy[1] - y0
        dist = math.hypot(dx, dy)
        px_s = 0.0 if dist < self.noise_px else dist / dt
        prev = self._smooth.get(tid)
        px_s = px_s if prev is None else self.ema * px_s + (1 - self.ema) * prev
        self._smooth[tid] = px_s
        mps = None
        if world_xy is not None and w0 is not None:
            wd = math.hypot(world_xy[0] - w0[0], world_xy[1] - w0[1]) / dt
            pm = self._smooth_m.get(tid)
            mps = wd if pm is None else self.ema * wd + (1 - self.ema) * pm
            self._smooth_m[tid] = mps
        deg, label = direction_label(dx, dy)
        return SpeedSample(px_s, mps, deg, label)

    def forget(self, active_ids):
        for d in (self._hist, self._smooth, self._smooth_m):
            for k in [k for k in d if k not in active_ids]:
                del d[k]
