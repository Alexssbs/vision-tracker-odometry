"""Linea virtual: conteo de cruces en ambos sentidos sin dobles conteos."""
import math
from typing import Dict, List, Optional, Tuple


class LineCounter:
    """Cuenta cruces por cambio de lado de la linea, con estado por ID.

    * Lado = signo de la distancia con signo a la recta P1->P2.
    * Zona muerta (``margin``): el lado solo se actualiza al alejarse mas de
      ``margin`` px, asi que un objeto detenido o temblando junto a la linea no
      genera cruces.
    * Cruce valido solo si cae dentro del segmento y respetando un ``cooldown``
      por ID.
    Sentidos: "A->B" = del lado negativo (A) al positivo (B). El lado B esta en la
    direccion de la normal (-dy, dx) del vector P1->P2.
    """

    def __init__(self, margin: float = 6.0, cooldown: float = 1.0):
        self.margin, self.cooldown = margin, cooldown
        self.p1: Optional[Tuple[float, float]] = None
        self.p2: Optional[Tuple[float, float]] = None
        self.enabled = True
        self.reset_counts()

    def reset_counts(self):
        self.count_ab = 0
        self.count_ba = 0
        self.by_class: Dict[str, Dict[str, int]] = {}
        self.events: List[dict] = []
        self._side: Dict[int, int] = {}
        self._last_cross: Dict[int, float] = {}

    def set_line(self, p1, p2):
        self.p1 = (float(p1[0]), float(p1[1]))
        self.p2 = (float(p2[0]), float(p2[1]))
        self._side.clear()          # evita cruces falsos al mover la linea

    @property
    def defined(self) -> bool:
        return self.p1 is not None and self.p2 is not None and \
            math.hypot(self.p2[0] - self.p1[0], self.p2[1] - self.p1[1]) > 5

    @property
    def total(self) -> int:
        return self.count_ab + self.count_ba

    def _geometry(self, pos):
        dx, dy = self.p2[0] - self.p1[0], self.p2[1] - self.p1[1]
        length = math.hypot(dx, dy)
        px, py = pos[0] - self.p1[0], pos[1] - self.p1[1]
        dist = (dx * py - dy * px) / length
        t = (px * dx + py * dy) / (length * length)
        return dist, t

    def update(self, tid: int, cls_name: str, pos, ts: float, frame: int) -> Optional[dict]:
        if not (self.enabled and self.defined):
            return None
        dist, t = self._geometry(pos)
        prev = self._side.get(tid)
        if abs(dist) <= self.margin:
            return None                      # zona muerta: no cambia el estado
        side = 1 if dist > 0 else -1
        self._side[tid] = side
        if prev is None or prev == side:
            return None
        if not (-0.05 <= t <= 1.05):         # cruzo la recta fuera del segmento
            return None
        if ts - self._last_cross.get(tid, -1e9) < self.cooldown:
            return None
        self._last_cross[tid] = ts
        direction = "A->B" if side > 0 else "B->A"
        if side > 0:
            self.count_ab += 1
        else:
            self.count_ba += 1
        c = self.by_class.setdefault(cls_name, {"A->B": 0, "B->A": 0})
        c[direction] += 1
        ev = {"id": tid, "direction": direction, "timestamp": ts, "class": cls_name,
              "frame": frame}
        self.events.append(ev)
        return ev

    def forget(self, active_ids):
        """Libera el estado de IDs que ya no estan activos."""
        for d in (self._side,):
            for k in [k for k in d if k not in active_ids]:
                del d[k]
