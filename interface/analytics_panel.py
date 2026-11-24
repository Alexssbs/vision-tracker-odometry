"""Panel derecho (tarjetas de estadisticas) y panel inferior (pestanas)."""
from collections import deque

import cv2
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QGridLayout, QLabel, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from interface.session_history import SessionHistory

pg.setConfigOptions(antialias=True, background="#0f172a", foreground="#cbd5e1")


class Card(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)
        self.t = QLabel(title)
        self.t.setObjectName("cardTitle")
        self.v = QLabel("—")
        self.v.setObjectName("cardValue")
        self.s = QLabel("")
        self.s.setObjectName("cardSub")
        lay.addWidget(self.t)
        lay.addWidget(self.v)
        lay.addWidget(self.s)

    def set(self, value, sub=""):
        self.v.setText(str(value))
        self.s.setText(sub)


class AnalyticsPanel(QWidget):
    def __init__(self):
        super().__init__()
        lay = QGridLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.cards = {k: Card(t) for k, t in (
            ("unique", "Objetos únicos"), ("active", "Objetos activos"),
            ("detections", "Total de detecciones"), ("crossed", "Cruzaron la línea"),
            ("avg", "Velocidad promedio"), ("max", "Velocidad máxima"),
            ("fps", "FPS de procesamiento"), ("infer", "Tiempo de inferencia"))}
        for i, c in enumerate(self.cards.values()):
            lay.addWidget(c, i, 0)
        lay.setRowStretch(len(self.cards), 1)

    def reset(self):
        for c in self.cards.values():
            c.set("—")

    def update_stats(self, s: dict, has_line: bool, has_speed: bool):
        c = self.cards
        c["unique"].set(s["unique"])
        c["active"].set(s["active"])
        c["detections"].set(s["detections"])
        if has_line:
            c["crossed"].set(s["crossed"], f"A→B: {s['cross_ab']}   B→A: {s['cross_ba']}")
        else:
            c["crossed"].set("—", "perfil sin línea")
        if not has_speed:
            c["avg"].set("—", "perfil sin velocidad")
            c["max"].set("—", "perfil sin velocidad")
        else:
            for key, px, kmh in (("avg", s["avg_px"], s["avg_kmh"]),
                                 ("max", s["max_px"], s["max_kmh"])):
                main = "—" if px is None else f"{px:.1f} px/s"
                sub = (f"real: {kmh:.1f} km/h" if kmh is not None
                       else "real: sin calibración válida")
                c[key].set(main, sub)
        c["fps"].set(f"{s['fps']:.1f}")
        c["infer"].set(f"{s['infer_ms']:.0f} ms")


class BottomTabs(QTabWidget):
    MAXPTS = 600

    def __init__(self):
        super().__init__()
        # estadisticas
        self.p_stats = pg.PlotWidget(title="Objetos activos (azul) y FPS (naranja) en el tiempo")
        self.p_stats.showGrid(x=True, y=True, alpha=0.2)
        self.c_active = self.p_stats.plot(pen=pg.mkPen("#3b82f6", width=2))
        self.c_fps = self.p_stats.plot(pen=pg.mkPen("#f59e0b", width=2))
        self.t, self.act, self.fps = deque(maxlen=self.MAXPTS), deque(maxlen=self.MAXPTS), \
            deque(maxlen=self.MAXPTS)
        self.addTab(self.p_stats, "Estadísticas")
        # trayectorias
        self.p_traj = pg.PlotWidget(title="Trayectorias de objetos activos")
        self.p_traj.invertY(True)
        self.p_traj.setAspectLocked(True)
        self.p_traj.showGrid(x=True, y=True, alpha=0.2)
        self.addTab(self.p_traj, "Trayectorias")
        # mapa de calor
        self.lbl_heat = QLabel("Mapa de calor no disponible para este perfil/modo.")
        self.lbl_heat.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_heat.setMinimumSize(100, 100)
        self.addTab(self.lbl_heat, "Mapa de calor")
        self._heat_img = None
        # eventos
        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["Tiempo (s)", "ID", "Clase", "Sentido"])
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.addTab(self.tbl, "Historial de eventos")
        # odometria
        self.p_odo = pg.PlotWidget(title="Movimiento acumulado de cámara (px, estimación 2D)")
        self.p_odo.showGrid(x=True, y=True, alpha=0.2)
        self.p_odo.addLegend()
        self.c_dx = self.p_odo.plot(pen=pg.mkPen("#22d3ee", width=2), name="dx")
        self.c_dy = self.p_odo.plot(pen=pg.mkPen("#a78bfa", width=2), name="dy")
        self.c_bad = pg.ScatterPlotItem(size=6, brush=pg.mkBrush("#ef4444"), pen=None)
        self.p_odo.addItem(self.c_bad)
        self.ot, self.odx, self.ody, self.bad = [deque(maxlen=self.MAXPTS) for _ in range(3)] + \
            [deque(maxlen=self.MAXPTS)]
        self.odo_tab = self.addTab(self.p_odo, "Odometría visual")
        self.setTabVisible(self.odo_tab, False)
        # cruces por hora (N2): imagen generada al finalizar la sesion
        self.lbl_hour = QLabel("El gráfico se genera al finalizar la sesión.")
        self.lbl_hour.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_hour.setMinimumSize(100, 100)
        self._hour_pix = None
        self.hour_tab = self.addTab(self.lbl_hour, "Cruces por hora")
        self.setTabVisible(self.hour_tab, False)
        # sesiones
        self.history = SessionHistory()
        self.addTab(self.history, "Sesiones")

    def set_mode(self, moving_comp: bool, traffic: bool = False):
        self.setTabVisible(self.odo_tab, moving_comp)
        self.setTabVisible(self.hour_tab, traffic)

    def reset(self):
        for d in (self.t, self.act, self.fps, self.ot, self.odx, self.ody, self.bad):
            d.clear()
        for c in (self.c_active, self.c_fps, self.c_dx, self.c_dy):
            c.setData([], [])
        self.c_bad.setData([], [])
        self.p_traj.clear()
        self.tbl.setRowCount(0)
        self.lbl_heat.clear()
        self._hour_pix = None
        self.lbl_hour.clear()
        self.lbl_hour.setText("El gráfico se genera al finalizar la sesión.")
        self.lbl_heat.setText("Mapa de calor no disponible para este perfil/modo.")

    def add_stats(self, s: dict):
        self.t.append(s["t"])
        self.act.append(s["active"])
        self.fps.append(s["fps"])
        self.c_active.setData(list(self.t), list(self.act))
        self.c_fps.setData(list(self.t), list(self.fps))

    def add_events(self, events: list):
        for ev in events:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            for c, v in enumerate((f"{ev['timestamp']:.2f}", ev["id"], ev["class"],
                                   ev["direction"])):
                self.tbl.setItem(r, c, QTableWidgetItem(str(v)))
        self.tbl.scrollToBottom()

    def add_camera(self, d: dict):
        self.ot.append(d["t"])
        self.odx.append(d["dx"])
        self.ody.append(d["dy"])
        self.bad.append(None if d["valid"] else d["t"])
        self.c_dx.setData(list(self.ot), list(self.odx))
        self.c_dy.setData(list(self.ot), list(self.ody))
        xs = [t for t in self.bad if t is not None]
        self.c_bad.setData(xs, [0] * len(xs))

    def set_views(self, heat, paths):
        if heat is not None:
            self._heat_img = heat
            self._paint_heat()
        if paths is not None and self.currentWidget() is self.p_traj:
            self.p_traj.clear()
            for tid, pts in paths.items():
                if len(pts) > 1:
                    a = np.array(pts)
                    self.p_traj.plot(a[:, 1], a[:, 2], pen=pg.mkPen(pg.intColor(tid, 20), width=2))

    def _paint_heat(self):
        if self._heat_img is None:
            return
        rgb = cv2.cvtColor(self._heat_img, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        img = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy()
        self.lbl_heat.setPixmap(QPixmap.fromImage(img).scaled(
            self.lbl_heat.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def show_hour_chart(self, png_path: str):
        pix = QPixmap(png_path)
        if not pix.isNull():
            self._hour_pix = pix
            self._paint_hour()

    def _paint_hour(self):
        if self._hour_pix is not None:
            self.lbl_hour.setPixmap(self._hour_pix.scaled(
                self.lbl_hour.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._paint_heat()
        self._paint_hour()
