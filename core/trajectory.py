"""Almacen de trayectorias por ID."""
from collections import deque
from typing import Deque, Dict, List, Tuple


class TrajectoryStore:
    """Guarda la trayectoria completa (para exportar) y una cola corta (para dibujar).

    Las coordenadas guardadas son las "de trabajo": en camara movil con
    compensacion valida son coordenadas del fotograma de referencia.
    """

    def __init__(self, tail_length: int = 60):
        self.tail_length = tail_length
        self.paths: Dict[int, List[Tuple[float, float, float]]] = {}   # id -> [(t,x,y)]
        self.tails: Dict[int, Deque[Tuple[float, float]]] = {}
        self.cls: Dict[int, str] = {}

    def add(self, tid: int, cls_name: str, t: float, x: float, y: float):
        self.paths.setdefault(tid, []).append((t, x, y))
        self.tails.setdefault(tid, deque(maxlen=self.tail_length)).append((x, y))
        self.cls[tid] = cls_name

    def forget_tails(self, active_ids, keep: int = 0):
        for k in [k for k in self.tails if k not in active_ids]:
            del self.tails[k]
