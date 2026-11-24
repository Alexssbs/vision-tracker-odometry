"""Ventana principal: barra superior + panel izquierdo + video/pestanas + panel derecho."""
from pathlib import Path

import cv2
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                               QScrollArea, QSplitter, QVBoxLayout, QWidget)

from config.settings import APP_NAME, MODES, PROFILES
from core.calibration import Calibration
from core.pipeline import ProcessingThread
from core.video_capture import VideoSource, read_preview
from interface.analytics_panel import AnalyticsPanel, BottomTabs
from interface.calibration_dialog import CalibrationDialog
from interface.control_panel import ControlPanel
from interface.video_panel import VideoPanel


class MainWindow(QMainWindow):
    def __init__(self, detector_factory=None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1500, 900)
        self._detector_factory = detector_factory
        self.thread = None
        self.line = None
        self.calib = Calibration()
        self.preview_frame = None
        self._restart_pending = False
        self._has_line = self._has_speed = False
        self._pre_fullscreen = None

        self.control = ControlPanel()
        self.video = VideoPanel()
        self.analytics = AnalyticsPanel()
        self.tabs = BottomTabs()

        # barra superior
        top = QFrame()
        top.setObjectName("topbar")
        tl = QHBoxLayout(top)
        self.lbl_title = QLabel(f"◉ {APP_NAME}")
        self.lbl_title.setObjectName("title")
        self.lbl_mode = QLabel()
        self.lbl_state = QLabel("Estado: detenido")
        self.lbl_fps = QLabel("FPS: —")
        tl.addWidget(self.lbl_title)
        tl.addStretch(1)
        for w in (self.lbl_mode, self.lbl_state, self.lbl_fps):
            tl.addWidget(w)
            tl.addSpacing(24)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.control)
        scroll.setMinimumWidth(320)
        scroll.setMaximumWidth(380)
        self.left = scroll
        center = QSplitter(Qt.Orientation.Vertical)
        center.addWidget(self.video)
        center.addWidget(self.tabs)
        center.setStretchFactor(0, 4)
        center.setStretchFactor(1, 2)
        self.center = center
        self.analytics.setFixedWidth(250)
        body = QWidget()
        bl = QHBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(self.left)
        bl.addWidget(center, 1)
        bl.addWidget(self.analytics)
        root = QWidget()
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(top)
        rl.addWidget(body, 1)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Listo.")

        c = self.control
        c.file_selected.connect(self.on_file_selected)
        c.webcam_preview_requested.connect(self.on_webcam_preview)
        c.start_clicked.connect(self.on_start)
        c.pause_clicked.connect(self.on_pause)
        c.stop_clicked.connect(self.on_stop)
        c.restart_clicked.connect(self.on_restart)
        c.step_clicked.connect(lambda: self.thread and self.thread.step())
        c.speed_changed.connect(lambda v: self.thread and self.thread.set_speed(v))
        c.live_changed.connect(self.push_live)
        c.mode_changed.connect(self.on_mode_changed)
        c.define_line_clicked.connect(self.on_define_line)
        c.reset_counts_clicked.connect(lambda: self.thread and self.thread.request_reset_counts())
        c.calibrate_clicked.connect(self.on_calibrate)
        c.clear_calibration_clicked.connect(self.on_clear_calibration)
        self.video.view.points_selected.connect(self.on_points_selected)
        self.video.view.line_dragged.connect(self.on_line_dragged)
        self.video.fullscreen_requested.connect(self.toggle_fullscreen)
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence("Esc"), self, activated=self._exit_fullscreen)
        self.on_mode_changed()

    # ---------------- utilidades ----------------
    def _running(self) -> bool:
        return self.thread is not None and self.thread.isRunning()

    def push_live(self):
        if self.thread:
            self.thread.update_live(self._live_cfg())

    def _live_cfg(self) -> dict:
        d = self.control.get_live_config()
        d["line"] = self.line
        return d

    def on_mode_changed(self):
        mode = self.control.mode.currentData()
        prof = self.control.profile.currentData()
        feats = PROFILES.get(prof, {"features": set()})["features"]
        self._has_line, self._has_speed = "line" in feats, "speed" in feats
        self.lbl_mode.setText(f"Modo: {MODES.get(mode, '')} — "
                              f"{PROFILES.get(prof, {}).get('label', '')}")
        self.tabs.set_mode("compensation" in feats, "traffic" in feats)
        self.video.view.overlay_enabled = not self._running()

    # ---------------- fuente ----------------
    def on_file_selected(self, path):
        self.control.path = path
        try:
            info, frame = read_preview(path)
        except Exception as e:
            QMessageBox.warning(self, "Video", f"No se pudo abrir el video:\n{e}")
            return
        if frame is None:
            QMessageBox.warning(self, "Video", "No se pudo leer ningún fotograma del video.")
            return
        self._load_preview(info.as_dict(), frame)

    def on_webcam_preview(self):
        src = VideoSource("webcam", cam_index=self.control.cam_index.currentData())
        try:
            info = src.open()
            ok, frame, _, _ = src.read()
        except Exception as e:
            QMessageBox.warning(self, "Webcam", f"No se pudo acceder a la cámara:\n{e}")
            return
        finally:
            src.release()
        if not ok:
            QMessageBox.warning(self, "Webcam", "La cámara no entregó imagen.")
            return
        self._load_preview(info.as_dict(), frame)

    def _load_preview(self, info: dict, frame):
        self.preview_frame = frame
        self.control.set_video_info(info)
        self.line = None
        self.calib.clear()
        self.video.view.line = None
        self.video.view.calib_poly = None
        self.control.lbl_line.setText("Sin línea. Arrastre sus extremos para moverla.")
        self.control.lbl_calib.setText("Sin calibración: velocidades solo en px/s.")
        self.video.view.fit()
        self.video.view.set_frame(frame)
        self.statusBar().showMessage(
            f"Video cargado: {info['name']} ({info['width']}×{info['height']})")

    # ---------------- linea y calibracion ----------------
    def on_define_line(self):
        if self.video.view._img is None:
            QMessageBox.information(self, "Línea", "Cargue un video primero "
                                    "(en webcam use «Vista previa»).")
            return
        self.video.set_hint("Haga clic en los 2 extremos de la línea…")
        self.video.view.begin_capture("line", 2)

    def on_calibrate(self):
        if self._running() or self.preview_frame is None:
            QMessageBox.information(self, "Calibración", "Cargue un video y calibre antes de "
                                    "iniciar el procesamiento.")
            return
        d = CalibrationDialog(self)
        if d.exec():
            self._calib_dims = d.values()
            self.video.set_hint("Calibración: clic en 4 puntos del suelo (sup-izq, sup-der, "
                                "inf-der, inf-izq)…")
            self.video.view.begin_capture("calib", 4)

    def on_clear_calibration(self):
        self.calib.clear()
        self.video.view.calib_poly = None
        self.video.view.update()
        self.control.lbl_calib.setText("Sin calibración: velocidades solo en px/s.")

    def on_points_selected(self, kind, pts):
        self.video.set_hint("")
        if kind == "line":
            self.line = (pts[0], pts[1])
            self.video.view.line = self.line
            self._line_label()
            self.push_live()
        elif kind == "calib":
            try:
                self.calib.set(pts, *self._calib_dims)
            except ValueError as e:
                QMessageBox.warning(self, "Calibración", str(e))
                return
            self.video.view.calib_poly = pts
            w, l = self._calib_dims
            self.control.lbl_calib.setText(f"Calibrada: {w:g} m × {l:g} m. Válida cerca del plano "
                                           "del suelo calibrado.")
        self.video.view.update()

    def on_line_dragged(self, p1, p2):
        self.line = (p1, p2)
        self._line_label()
        self.push_live()

    def _line_label(self):
        (x1, y1), (x2, y2) = self.line
        self.control.lbl_line.setText(f"Línea: ({x1:.0f},{y1:.0f}) → ({x2:.0f},{y2:.0f})  px del "
                                      "video original")

    # ---------------- ejecucion ----------------
    def on_start(self):
        if self._running():
            return
        cfg = self.control.get_run_config()
        if cfg["source_kind"] == "file" and not cfg["path"]:
            QMessageBox.information(self, "Fuente", "Seleccione un archivo de video.")
            return
        self.analytics.reset()
        self.tabs.reset()
        t = ProcessingThread(cfg, self._live_cfg(), self.calib, self._detector_factory, self)
        self.thread = t
        t.set_speed(self.control.speed.currentData())
        t.frame_ready.connect(self._on_frame)
        t.stats_ready.connect(self._on_stats)
        t.info_ready.connect(self.control.set_video_info)
        t.events_ready.connect(self.tabs.add_events)
        t.camera_ready.connect(self.tabs.add_camera)
        t.views_ready.connect(self.tabs.set_views)
        t.state_changed.connect(self._on_state)
        t.session_finished.connect(self._on_session_finished)
        t.error.connect(self._on_error)
        t.finished.connect(self._on_thread_finished)
        self.control.set_running(True)
        self.video.view.overlay_enabled = False
        t.start()

    def on_pause(self):
        if not self._running():
            return
        if self.thread.paused:
            self.thread.resume()
        else:
            self.thread.pause()
        self.control.set_running(True, self.thread.paused)

    def on_stop(self):
        if self._running():
            self.thread.stop()
            self.statusBar().showMessage("Deteniendo y exportando resultados…")

    def on_restart(self):
        if self._running():
            self._restart_pending = True
            self.thread.stop()
        else:
            self.on_start()

    def _on_frame(self, frame):
        self.video.view.set_frame(frame)
        if self.thread:
            self.thread.ack_frame()

    def _on_stats(self, s):
        self.analytics.update_stats(s, self._has_line, self._has_speed)
        self.tabs.add_stats(s)
        self.lbl_fps.setText(f"FPS: {s['fps']:.1f}")

    def _on_state(self, st):
        self.lbl_state.setText(f"Estado: {st}")

    def _on_session_finished(self, folder, status):
        self.statusBar().showMessage(f"Sesión {status}. Resultados en: {folder}")
        self.tabs.history.refresh()
        png = Path(folder) / "crossings_by_hour.png"
        if png.exists():
            self.tabs.show_hour_chart(str(png))

    def _on_error(self, msg):
        QMessageBox.critical(self, "Error de procesamiento", msg)
        self.tabs.history.refresh()

    def _on_thread_finished(self):
        self.thread = None
        self.control.set_running(False)
        self.video.view.overlay_enabled = True
        self.lbl_fps.setText("FPS: —")
        if self._restart_pending:
            self._restart_pending = False
            self.on_start()

    # ---------------- pantalla completa ----------------
    def toggle_fullscreen(self):
        if self.isFullScreen():
            self._exit_fullscreen()
        else:
            self.left.hide()
            self.analytics.hide()
            self.tabs.hide()
            self.showFullScreen()

    def _exit_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.left.show()
            self.analytics.show()
            self.tabs.show()

    def closeEvent(self, e):
        if self._running():
            self.thread.stop()
            self.thread.wait(8000)
        super().closeEvent(e)
