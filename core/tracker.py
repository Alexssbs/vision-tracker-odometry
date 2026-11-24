"""Estructuras de datos compartidas entre detector, tracker y modulos de analisis."""
from dataclasses import dataclass
from typing import Tuple


@dataclass
class Track:
    """Resultado de detector+tracker para un objeto en un fotograma (coords originales)."""
    track_id: int
    cls_id: int
    cls_name: str
    conf: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    @property
    def foot(self) -> Tuple[float, float]:
        """Punto de contacto con el suelo (centro inferior de la caja)."""
        return ((self.x1 + self.x2) / 2.0, self.y2)

    @property
    def box(self):
        return (self.x1, self.y1, self.x2, self.y2)
