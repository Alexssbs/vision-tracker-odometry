"""Visor de video: mantiene la relacion de aspecto, permite zoom y convierte los clics
del widget a coordenadas del fotograma original."""
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget


class VideoView(QWidget):
    points_selected = Signal(str, list)      # (tipo, [(x,y),...]) en coords originales
    line_dragged = Signal(tuple, tuple)      # nueva posicion de la linea

    def __init__(self):
        super().__init__()
        self.setMinimumSize(320, 220)
        self._img = None
        self._size = (0, 0)
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self.line = None                     # ((x1,y1),(x2,y2)) coords originales
        self.overlay_enabled = True          # dibuja la linea propia (cuando no hay procesamiento)
        self.calib_poly = None               # 4 puntos coords originales
        self._cap_kind, self._cap_n, self._cap_pts = None, 0, []
        self._drag_idx = None
        self._pan_last = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    # ---- imagen ----
    def set_frame(self, frame: np.ndarray):
        frame = np.ascontiguousarray(frame)
        h, w = frame.shape[:2]
        self._img = QImage(frame.data, w, h, frame.strides[0], QImage.Format.Format_BGR888).copy()
        self._size = (w, h)
        self.update()

    def clear(self):
        self._img, self._size = None, (0, 0)
        self.update()

    def fit(self):
        self.zoom, self.pan = 1.0, QPointF(0, 0)
        self.update()

    def zoom_by(self, f: float):
        self.zoom = min(8.0, max(1.0, self.zoom * f))
        if self.zoom == 1.0:
            self.pan = QPointF(0, 0)
        self.update()

    # ---- captura de puntos / linea ----
    def begin_capture(self, kind: str, n: int):
        self._cap_kind, self._cap_n, self._cap_pts = kind, n, []
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def cancel_capture(self):
        self._cap_kind, self._cap_pts = None, []
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    @property
    def capturing(self) -> bool:
        return self._cap_kind is not None

    # ---- geometria ----
    def _geom(self):
        iw, ih = self._size
        if iw == 0:
            return 1.0, 0.0, 0.0
        s = min(self.width() / iw, self.height() / ih) * self.zoom
        ox = (self.width() - iw * s) / 2 + self.pan.x()
        oy = (self.height() - ih * s) / 2 + self.pan.y()
        return s, ox, oy

    def to_frame(self, pos):
        s, ox, oy = self._geom()
        return ((pos.x() - ox) / s, (pos.y() - oy) / s)

    def to_widget(self, p):
        s, ox, oy = self._geom()
        return QPointF(p[0] * s + ox, p[1] * s + oy)

    def _inside(self, p):
        return 0 <= p[0] <= self._size[0] and 0 <= p[1] <= self._size[1]

    # ---- eventos ----
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#0b0f17"))
        if self._img is None:
            p.setPen(QColor("#64748b"))
            p.setFont(QFont("Segoe UI", 12))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Seleccione un video o una webcam para comenzar")
            return
        s, ox, oy = self._geom()
        iw, ih = self._size
        p.drawImage(QRectF(ox, oy, iw * s, ih * s), self._img)
        if self.calib_poly and self.overlay_enabled:
            p.setPen(QPen(QColor("#f59e0b"), 2))
            for i in range(4):
                p.drawLine(self.to_widget(self.calib_poly[i]),
                           self.to_widget(self.calib_poly[(i + 1) % 4]))
        if self.line and (self.overlay_enabled or self._drag_idx is not None):
            p.setPen(QPen(QColor("#22d3ee"), 3))
            a, b = self.to_widget(self.line[0]), self.to_widget(self.line[1])
            p.drawLine(a, b)
            p.setBrush(QColor("#22d3ee"))
            p.drawEllipse(a, 6, 6)
            p.drawEllipse(b, 6, 6)
        if self._cap_kind:
            p.setPen(QPen(QColor("#facc15"), 2))
            p.setBrush(QColor("#facc15"))
            pts = [self.to_widget(q) for q in self._cap_pts]
            for i, q in enumerate(pts):
                p.drawEllipse(q, 5, 5)
                p.drawText(q + QPointF(8, -8), str(i + 1))
                if i:
                    p.drawLine(pts[i - 1], q)

    def mousePressEvent(self, e):
        fp = self.to_frame(e.position())
        if e.button() == Qt.MouseButton.RightButton or (
                e.button() == Qt.MouseButton.MiddleButton):
            self._pan_last = e.position()
            return
        if e.button() != Qt.MouseButton.LeftButton or self._img is None:
            return
        if self._cap_kind:
            if self._inside(fp):
                self._cap_pts.append(fp)
                if len(self._cap_pts) >= self._cap_n:
                    kind, pts = self._cap_kind, list(self._cap_pts)
                    self.cancel_capture()
                    self.points_selected.emit(kind, pts)
                self.update()
            return
        if self.line:
            for i in (0, 1):
                w = self.to_widget(self.line[i])
                if (w - e.position()).manhattanLength() < 18:
                    self._drag_idx = i
                    return
        if self.zoom > 1.0:
            self._pan_last = e.position()

    def mouseMoveEvent(self, e):
        if self._drag_idx is not None:
            fp = self.to_frame(e.position())
            fp = (min(max(fp[0], 0), self._size[0]), min(max(fp[1], 0), self._size[1]))
            ln = list(self.line)
            ln[self._drag_idx] = fp
            self.line = (ln[0], ln[1])
            self.update()
        elif self._pan_last is not None:
            d = e.position() - self._pan_last
            self._pan_last = e.position()
            self.pan += d
            self.update()

    def mouseReleaseEvent(self, e):
        if self._drag_idx is not None:
            self._drag_idx = None
            self.line_dragged.emit(self.line[0], self.line[1])
            self.update()
        self._pan_last = None

    def wheelEvent(self, e):
        self.zoom_by(1.15 if e.angleDelta().y() > 0 else 1 / 1.15)


class VideoPanel(QWidget):
    fullscreen_requested = Signal()

    def __init__(self):
        super().__init__()
        self.view = VideoView()
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        self.hint = QPushButton("")
        self.hint.setObjectName("hint")
        self.hint.setFlat(True)
        self.hint.setEnabled(False)
        bar.addWidget(self.hint, 1)
        for text, fn, tip in (("Ajustar", self.view.fit, "Ajustar al panel"),
                              ("Ampliar +", lambda: self.view.zoom_by(1.25), "Ampliar (rueda del ratón)"),
                              ("Reducir −", lambda: self.view.zoom_by(0.8), "Reducir"),
                              ("Pantalla completa", self.fullscreen_requested.emit, "F11")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            bar.addWidget(b)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view, 1)
        lay.addLayout(bar)

    def set_hint(self, text: str):
        self.hint.setText(text)
