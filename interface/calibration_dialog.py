"""Dialogo para ingresar las dimensiones reales del rectangulo de calibracion."""
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
                               QVBoxLayout)


class CalibrationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibración espacial")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Se usará una homografía del plano del suelo.\n"
            "Después de aceptar, haga clic sobre el video en 4 puntos del SUELO que formen\n"
            "un rectángulo de medidas conocidas, en este orden:\n"
            "1) sup-izq  2) sup-der  3) inf-der  4) inf-izq.\n"
            "Solo es confiable cerca del plano calibrado."))
        form = QFormLayout()
        self.width_m = QDoubleSpinBox()
        self.length_m = QDoubleSpinBox()
        for sp, v in ((self.width_m, 3.5), (self.length_m, 10.0)):
            sp.setRange(0.1, 500.0)
            sp.setDecimals(2)
            sp.setSuffix(" m")
            sp.setValue(v)
        form.addRow("Ancho real (lado 1→2):", self.width_m)
        form.addRow("Largo real (lado 2→3):", self.length_m)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def values(self):
        return self.width_m.value(), self.length_m.value()
