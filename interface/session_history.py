"""Historial sencillo de sesiones: lee results/*/summary.json."""
import json

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from config.settings import MODES, RESULTS_DIR

COLS = ["Sesión", "Video", "Modo", "Tracker", "Fecha", "Objetos", "Estado"]


class SessionHistory(QWidget):
    def __init__(self):
        super().__init__()
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self.open_selected)
        b1, b2 = QPushButton("Actualizar"), QPushButton("Abrir carpeta de resultados")
        b1.clicked.connect(self.refresh)
        b2.clicked.connect(self.open_selected)
        row = QHBoxLayout()
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch(1)
        lay = QVBoxLayout(self)
        lay.addLayout(row)
        lay.addWidget(self.table)
        self._folders = []
        self.refresh()

    def refresh(self):
        self.table.setRowCount(0)
        self._folders = []
        if not RESULTS_DIR.exists():
            return
        for d in sorted((p for p in RESULTS_DIR.iterdir() if p.is_dir()), reverse=True):
            f = d / "summary.json"
            if not f.exists():
                continue
            try:
                s = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                s = {"status": "ilegible"}
            vals = [d.name, (s.get("video") or {}).get("name", "-"),
                    MODES.get(s.get("camera_mode"), s.get("camera_mode", "-")),
                    s.get("tracker", "-"), s.get("started_at", "-"),
                    s.get("total_unique_objects", "-"), s.get("status", "-")]
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, v in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(str(v)))
            self._folders.append(d)

    def open_selected(self, *_):
        r = self.table.currentRow()
        if 0 <= r < len(self._folders):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._folders[r])))
