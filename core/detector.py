"""Envoltura de Ultralytics YOLO: detecta y hace tracking en una sola llamada."""
from pathlib import Path
from typing import List, Optional, Sequence

from config.settings import MODELS_DIR, TRACKERS
from core.tracker import Track


class YoloTracker:
    """YOLO + ByteTrack/BoT-SORT mediante ``model.track(persist=True)``.

    YOLO se ejecuta una unica vez por fotograma; el resto de modulos
    reutilizan la lista de ``Track`` devuelta.
    """

    def __init__(self, model_name: str, tracker_name: str = "ByteTrack"):
        self.model_name = model_name
        self.tracker_yaml = TRACKERS.get(tracker_name, "bytetrack.yaml")
        self.model = None

    def load(self):
        from ultralytics import YOLO  # import tardio: arranque rapido de la UI
        path = Path(self.model_name)
        if not path.is_absolute():
            local = MODELS_DIR / self.model_name
            path = local if local.exists() else Path(self.model_name)
        self.model = YOLO(str(path))   # descarga automatica si no existe
        return self

    def reset(self):
        """Reinicia el estado del tracker (nueva sesion)."""
        if self.model is not None:
            self.model.predictor = None

    def track(self, frame, conf: float, iou: float, imgsz: int,
              classes: Optional[Sequence[int]]) -> List[Track]:
        results = self.model.track(frame, persist=True, conf=conf, iou=iou, imgsz=imgsz,
                                   classes=list(classes) if classes else None,
                                   tracker=self.tracker_yaml, verbose=False)
        r = results[0]
        out: List[Track] = []
        boxes = r.boxes
        if boxes is None or boxes.id is None:
            return out
        xyxy = boxes.xyxy.cpu().numpy()
        ids = boxes.id.int().cpu().tolist()
        cls = boxes.cls.int().cpu().tolist()
        confs = boxes.conf.cpu().tolist()
        names = r.names
        for b, i, c, p in zip(xyxy, ids, cls, confs):
            out.append(Track(int(i), int(c), str(names.get(int(c), c)), float(p),
                             float(b[0]), float(b[1]), float(b[2]), float(b[3])))
        return out
