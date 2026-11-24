"""Panel lateral izquierdo: fuente, modo, perfil, tracker, deteccion, visualizacion,
linea virtual, calibracion, exportacion y controles de reproduccion."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton, QRadioButton,
                               QSpinBox, QVBoxLayout, QWidget)

from config.classes import COCO_CLASSES, PRESETS
from config.settings import (DEFAULT_MODEL, DEFAULT_RUN, MODEL_CHOICES, MODELS_DIR, MODES,
                             PLAYBACK_SPEEDS, PROFILES, TRACKERS)


class ClassesDialog(QDialog):
    def __init__(self, selected, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Clases a detectar")
        lay = QVBoxLayout(self)
        self.preset = QComboBox()
        self.preset.addItems(list(PRESETS))
        self.preset.activated.connect(self._apply_preset)
        lay.addWidget(self.preset)
        self.lst = QListWidget()
        for i, n in enumerate(COCO_CLASSES):
            it = QListWidgetItem(f"{i}: {n}")
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            on = selected is None or i in selected
            it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
            self.lst.addItem(it)
        lay.addWidget(self.lst)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.resize(300, 480)

    def _apply_preset(self):
        ids = PRESETS[self.preset.currentText()]
        for i in range(self.lst.count()):
            on = ids is None or i in ids
            self.lst.item(i).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def selected(self):
        ids = [i for i in range(self.lst.count())
               if self.lst.item(i).checkState() == Qt.CheckState.Checked]
        return None if len(ids) in (0, len(COCO_CLASSES)) else ids


class ControlPanel(QWidget):
    file_selected = Signal(str)
    webcam_preview_requested = Signal()
    start_clicked = Signal()
    pause_clicked = Signal()
    stop_clicked = Signal()
    restart_clicked = Signal()
    step_clicked = Signal()
    speed_changed = Signal(float)
    live_changed = Signal()
    mode_changed = Signal()
    define_line_clicked = Signal()
    reset_counts_clicked = Signal()
    calibrate_clicked = Signal()
    clear_calibration_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.path = ""
        self.classes = None
        self._locked_widgets = []
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        # --- reproduccion ---
        g = QGroupBox("Reproducción")
        v = QVBoxLayout(g)
        r1, r2 = QHBoxLayout(), QHBoxLayout()
        self.b_start = QPushButton("▶ Iniciar")
        self.b_start.setObjectName("primary")
        self.b_pause = QPushButton("⏸ Pausar")
        self.b_stop = QPushButton("⏹ Detener")
        self.b_restart = QPushButton("↺ Reiniciar")
        self.b_step = QPushButton("⏭ Fotograma")
        for b, s in ((self.b_start, self.start_clicked), (self.b_pause, self.pause_clicked),
                     (self.b_stop, self.stop_clicked), (self.b_restart, self.restart_clicked),
                     (self.b_step, self.step_clicked)):
            b.clicked.connect(s.emit)
        r1.addWidget(self.b_start)
        r1.addWidget(self.b_pause)
        r1.addWidget(self.b_stop)
        r2.addWidget(self.b_restart)
        r2.addWidget(self.b_step)
        v.addLayout(r1)
        v.addLayout(r2)
        f = QFormLayout()
        self.speed = QComboBox()
        for lbl, val in PLAYBACK_SPEEDS:
            self.speed.addItem(lbl, val)
        self.speed.setCurrentIndex(2)
        self.speed.currentIndexChanged.connect(
            lambda: self.speed_changed.emit(self.speed.currentData()))
        f.addRow("Velocidad (archivos):", self.speed)
        v.addLayout(f)
        root.addWidget(g)

        # --- fuente ---
        g = QGroupBox("Fuente de video")
        v = QVBoxLayout(g)
        row = QHBoxLayout()
        self.rb_file, self.rb_cam = QRadioButton("Archivo"), QRadioButton("Webcam")
        self.rb_file.setChecked(True)
        self.rb_file.toggled.connect(self._source_toggled)
        row.addWidget(self.rb_file)
        row.addWidget(self.rb_cam)
        v.addLayout(row)
        self.b_open = QPushButton("Abrir video…")
        self.b_open.clicked.connect(self._open_file)
        v.addWidget(self.b_open)
        self.cam_row = QWidget()
        cr = QHBoxLayout(self.cam_row)
        cr.setContentsMargins(0, 0, 0, 0)
        self.cam_index = QComboBox()
        for i in range(5):
            self.cam_index.addItem(f"Cámara {i}", i)
        self.b_cam_prev = QPushButton("Vista previa")
        self.b_cam_prev.clicked.connect(self.webcam_preview_requested.emit)
        cr.addWidget(self.cam_index)
        cr.addWidget(self.b_cam_prev)
        v.addWidget(self.cam_row)
        self.cam_row.hide()
        self.info = {k: QLabel("—") for k in ("Nombre", "Resolución", "FPS", "Duración",
                                              "Fotogramas")}
        fi = QFormLayout()
        for k, lab in self.info.items():
            lab.setWordWrap(True)
            fi.addRow(k + ":", lab)
        v.addLayout(fi)
        self._locked_widgets += [self.rb_file, self.rb_cam, self.b_open, self.cam_index,
                                 self.b_cam_prev]
        root.addWidget(g)

        # --- modo y perfil ---
        g = QGroupBox("Modo y perfil de análisis")
        f = QFormLayout(g)
        self.mode = QComboBox()
        for k, lbl in MODES.items():
            self.mode.addItem(lbl, k)
        self.profile = QComboBox()
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.profile.currentIndexChanged.connect(self._profile_changed)
        f.addRow("Cámara:", self.mode)
        f.addRow("Perfil:", self.profile)
        self._locked_widgets += [self.mode, self.profile]
        root.addWidget(g)

        # --- deteccion ---
        g = QGroupBox("Detección y tracking")
        f = QFormLayout(g)
        self.model = QComboBox()
        self.model.setEditable(True)
        local = sorted(p.name for p in MODELS_DIR.glob("*.pt")) if MODELS_DIR.exists() else []
        self.model.addItems(list(dict.fromkeys([DEFAULT_MODEL] + local + MODEL_CHOICES)))
        self.tracker = QComboBox()
        self.tracker.addItems(list(TRACKERS))
        self.conf = QDoubleSpinBox()
        self.conf.setRange(0.05, 0.99)
        self.conf.setSingleStep(0.05)
        self.conf.setValue(DEFAULT_RUN["conf"])
        self.iou = QDoubleSpinBox()
        self.iou.setRange(0.1, 0.95)
        self.iou.setSingleStep(0.05)
        self.iou.setValue(DEFAULT_RUN["iou"])
        self.imgsz = QComboBox()
        for s in (320, 480, 640, 960):
            self.imgsz.addItem(str(s), s)
        self.imgsz.setCurrentIndex(2)
        self.skip = QSpinBox()
        self.skip.setRange(1, 10)
        self.skip.setToolTip("Procesar 1 de cada N fotogramas (acelera en CPU)")
        self.b_classes = QPushButton("Todas las clases")
        self.b_classes.clicked.connect(self._pick_classes)
        f.addRow("Modelo YOLO:", self.model)
        f.addRow("Tracker:", self.tracker)
        f.addRow("Confianza:", self.conf)
        f.addRow("IoU:", self.iou)
        f.addRow("Tamaño (imgsz):", self.imgsz)
        f.addRow("1 de cada N fotog.:", self.skip)
        f.addRow("Clases:", self.b_classes)
        self._locked_widgets += [self.model, self.tracker, self.imgsz, self.skip, self.b_classes]
        self.conf.valueChanged.connect(self._emit_live)
        self.iou.valueChanged.connect(self._emit_live)
        root.addWidget(g)

        # --- visualizacion ---
        g = QGroupBox("Visualización")
        v = QVBoxLayout(g)
        self.cb = {}
        for key, lbl in (("show_boxes", "Cajas"), ("show_ids", "IDs"),
                         ("show_conf", "Confianza"), ("show_traj", "Trayectorias"),
                         ("show_speed", "Velocidad"), ("show_orb", "Puntos ORB / correspondencias")):
            c = QCheckBox(lbl)
            c.setChecked(True)
            c.toggled.connect(self._emit_live)
            self.cb[key] = c
            v.addWidget(c)
        row = QHBoxLayout()
        self.traj_mode = QComboBox()
        self.traj_mode.addItem("Todas", "all")
        self.traj_mode.addItem("Solo ID:", "single")
        self.traj_id = QSpinBox()
        self.traj_id.setRange(0, 999999)
        self.traj_mode.currentIndexChanged.connect(self._emit_live)
        self.traj_id.valueChanged.connect(self._emit_live)
        row.addWidget(self.traj_mode)
        row.addWidget(self.traj_id)
        v.addLayout(row)
        root.addWidget(g)

        # --- linea virtual ---
        self.g_line = QGroupBox("Línea virtual")
        v = QVBoxLayout(self.g_line)
        self.line_enabled = QCheckBox("Línea activa")
        self.line_enabled.setChecked(True)
        self.line_enabled.toggled.connect(self._emit_live)
        self.b_line = QPushButton("Definir línea (2 clics)")
        self.b_line.clicked.connect(self.define_line_clicked.emit)
        self.b_reset = QPushButton("Reiniciar conteo")
        self.b_reset.clicked.connect(self.reset_counts_clicked.emit)
        self.lbl_line = QLabel("Sin línea. Arrastre sus extremos para moverla.")
        self.lbl_line.setWordWrap(True)
        for w in (self.line_enabled, self.b_line, self.b_reset, self.lbl_line):
            v.addWidget(w)
        root.addWidget(self.g_line)

        # --- calibracion ---
        self.g_calib = QGroupBox("Calibración espacial")
        v = QVBoxLayout(self.g_calib)
        self.b_calib = QPushButton("Calibrar escena (homografía)")
        self.b_calib.clicked.connect(self.calibrate_clicked.emit)
        self.b_calib_clear = QPushButton("Quitar calibración")
        self.b_calib_clear.clicked.connect(self.clear_calibration_clicked.emit)
        self.lbl_calib = QLabel("Sin calibración: velocidades solo en px/s.")
        self.lbl_calib.setWordWrap(True)
        for w in (self.b_calib, self.b_calib_clear, self.lbl_calib):
            v.addWidget(w)
        root.addWidget(self.g_calib)

        # --- radar de velocidad (N1) ---
        self.g_radar = QGroupBox("Radar de velocidad")
        f = QFormLayout(self.g_radar)
        self.speed_limit = QDoubleSpinBox()
        self.speed_limit.setRange(1.0, 400.0)
        self.speed_limit.setSingleStep(5.0)
        self.speed_limit.setDecimals(1)
        self.speed_limit.setSuffix(" km/h")
        self.speed_limit.setValue(60.0)
        self.speed_limit.setToolTip("Los vehículos que superen este límite se dibujan en rojo. "
                                    "Solo aplica con calibración válida.")
        self.speed_limit.valueChanged.connect(self._emit_live)
        f.addRow("Límite de velocidad:", self.speed_limit)
        lbl = QLabel("Alerta visual (caja roja) solo con calibración válida.")
        lbl.setWordWrap(True)
        f.addRow(lbl)
        root.addWidget(self.g_radar)

        # --- exportacion ---
        g = QGroupBox("Exportación")
        v = QVBoxLayout(g)
        self.save_video = QCheckBox("Guardar video procesado")
        self.export_pdf = QCheckBox("Generar reporte PDF")
        v.addWidget(self.save_video)
        v.addWidget(self.export_pdf)
        root.addWidget(g)
        root.addStretch(1)

        self._mode_changed()
        self.set_running(False)

    # ---------- logica interna ----------
    def _emit_live(self, *_):
        """Las senales de Qt (valueChanged, toggled...) envian un argumento; live_changed no."""
        self.live_changed.emit()

    def _source_toggled(self):
        file_mode = self.rb_file.isChecked()
        self.b_open.setVisible(file_mode)
        self.cam_row.setVisible(not file_mode)
        self.speed.setEnabled(file_mode)
        self.mode_changed.emit()

    def _open_file(self):
        p, _ = QFileDialog.getOpenFileName(self, "Abrir video", "",
                                           "Videos (*.mp4 *.avi *.mov *.mkv);;Todos (*)")
        if p:
            self.path = p
            self.file_selected.emit(p)

    def _pick_classes(self):
        d = ClassesDialog(self.classes, self)
        if d.exec():
            self.classes = d.selected()
            self.b_classes.setText("Todas las clases" if self.classes is None
                                   else f"{len(self.classes)} clases seleccionadas")

    def _mode_changed(self):
        mode = self.mode.currentData()
        self.profile.blockSignals(True)
        self.profile.clear()
        for k, p in PROFILES.items():
            if mode in p["modes"]:
                self.profile.addItem(p["label"], k)
        self.profile.blockSignals(False)
        self._profile_changed()
        self.mode_changed.emit()

    def _profile_changed(self):
        feats = PROFILES.get(self.profile.currentData(), {"features": set()})["features"]
        self.g_line.setVisible("line" in feats)
        self.g_calib.setVisible("calibration" in feats)
        self.g_radar.setVisible(self.profile.currentData() == "radar")
        self.cb["show_orb"].setVisible("compensation" in feats)
        self.cb["show_speed"].setVisible("speed" in feats)
        self.mode_changed.emit()

    # ---------- API ----------
    def set_running(self, running: bool, paused: bool = False):
        for w in self._locked_widgets:
            w.setEnabled(not running)
        self.b_start.setEnabled(not running)
        for b in (self.b_pause, self.b_stop, self.b_restart):
            b.setEnabled(running)
        self.b_step.setEnabled(running)
        self.b_calib.setEnabled(not running)
        self.b_calib_clear.setEnabled(not running)
        self.b_pause.setText("▶ Reanudar" if paused else "⏸ Pausar")
        if not running:
            self.speed.setEnabled(self.rb_file.isChecked())

    def set_video_info(self, d: dict):
        self.info["Nombre"].setText(d.get("name", "—"))
        self.info["Resolución"].setText(f"{d.get('width', 0)} × {d.get('height', 0)}")
        self.info["FPS"].setText(f"{d['fps']:.2f}" if d.get("fps") else "no disponible")
        self.info["Duración"].setText(f"{d['duration']:.1f} s" if d.get("duration") else "—")
        self.info["Fotogramas"].setText(str(d["frames"]) if d.get("frames") else "—")

    def get_run_config(self) -> dict:
        return {
            "source_kind": "file" if self.rb_file.isChecked() else "webcam",
            "path": self.path, "cam_index": self.cam_index.currentData(),
            "mode": self.mode.currentData(), "profile": self.profile.currentData(),
            "model": self.model.currentText().strip() or DEFAULT_MODEL,
            "tracker": self.tracker.currentText(), "imgsz": self.imgsz.currentData(),
            "frame_skip": self.skip.value(), "classes": self.classes,
            **{k: v for k, v in DEFAULT_RUN.items()
               if k not in ("conf", "iou", "imgsz", "frame_skip")},
            "conf": self.conf.value(), "iou": self.iou.value(),
            "speed_limit_kmh": self.speed_limit.value(),
        }

    def get_live_config(self) -> dict:
        d = {k: c.isChecked() for k, c in self.cb.items()}
        d.update(conf=self.conf.value(), iou=self.iou.value(),
                 traj_mode=self.traj_mode.currentData(), traj_id=self.traj_id.value(),
                 line_enabled=self.line_enabled.isChecked(),
                 speed_limit_kmh=self.speed_limit.value(),
                 save_video=self.save_video.isChecked(), export_pdf=self.export_pdf.isChecked())
        return d
