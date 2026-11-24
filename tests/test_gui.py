"""Prueba de la interfaz en modo offscreen. QT_QPA_PLATFORM=offscreen python -m tests.test_gui"""
import os, sys, tempfile, time
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2, numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

import core.pipeline as pl
import interface.session_history as sh
from config.settings import STYLES_PATH
from interface.main_window import MainWindow

TMP = Path(tempfile.mkdtemp())
pl.RESULTS_DIR = TMP / "results"
sh.RESULTS_DIR = TMP / "results"
OUT = Path(os.environ.get("SHOT_DIR", TMP))

app = QApplication(sys.argv)
from tests.fake_detector import factory
from tests.test_pipeline import make_fixed
app.setStyleSheet(STYLES_PATH.read_text(encoding="utf-8"))
win = MainWindow(detector_factory=factory)
win.resize(1500, 900)
win.show()
app.processEvents()


def pump(sec=0.0, until=None, timeout=60):
    t0 = time.time()
    while time.time() - t0 < (timeout if until else sec):
        app.processEvents()
        if until and until():
            return True
        time.sleep(0.01)
    return not until


# 1) cargar video horizontal y verificar vista previa + informacion
v = TMP / "h.avi"
make_fixed(v, 640, 480)
win.on_file_selected(str(v))
assert win.control.info["Resolución"].text() == "640 × 480", win.control.info["Resolución"].text()
print("info:", {k: l.text() for k, l in win.control.info.items()})

# 2) perfiles por modo
win.control.mode.setCurrentIndex(0)
labels = [win.control.profile.itemText(i) for i in range(win.control.profile.count())]
win.control.mode.setCurrentIndex(1)
labels_m = [win.control.profile.itemText(i) for i in range(win.control.profile.count())]
print("perfiles fija:", labels)
print("perfiles movil:", labels_m)
assert len(labels) == 4 and len(labels_m) == 2
win.control.mode.setCurrentIndex(0)
win.control.profile.setCurrentIndex(labels.index("Radar de velocidad (N1)"))

# 3) mapeo de coordenadas: el clic en el widget debe caer en el pixel correcto del original
view = win.video.view
app.processEvents()
s, ox, oy = view._geom()
fp = view.to_frame(view.to_widget((123.0, 321.0)))
assert abs(fp[0] - 123) < 1e-6 and abs(fp[1] - 321) < 1e-6
print(f"mapeo clic<->original OK (escala visual {s:.3f}, offset {ox:.0f},{oy:.0f})")

# 4) linea por 2 clics reales sobre el visor
view.begin_capture("line", 2)
for p in ((320, 20), (320, 460)):
    pos = view.to_widget(p)
    from PySide6.QtTest import QTest
    QTest.mouseClick(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     pos.toPoint())
assert win.line is not None and abs(win.line[0][0] - 320) < 1.5, win.line
print("linea definida con clics:", [(round(a), round(b)) for a, b in win.line])

# 5) arrastrar un extremo de la linea
a = view.to_widget(win.line[0]).toPoint()
b = a + view.to_widget((330, 20)).toPoint() - view.to_widget((320, 20)).toPoint()
QTest.mousePress(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
QTest.mouseMove(view, b)
QTest.mouseRelease(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
print("linea tras arrastre:", [(round(x), round(y)) for x, y in win.line])
assert abs(win.line[0][0] - 330) < 2
win.line = ((320.0, 20.0), (320.0, 460.0)); view.line = win.line

# 6) calibracion por 4 clics
win._calib_dims = (16.0, 12.0)
win.on_points_selected("calib", [(5, 5), (635, 5), (635, 475), (5, 475)])
assert win.calib.valid
print("calibracion:", win.control.lbl_calib.text())

# 7) ejecutar y verificar que la UI sigue respondiendo (no se congela)
win.control.save_video.setChecked(False)
win.on_start()
assert win._running()
ticks = []
t0 = time.time()
pump(until=lambda: (ticks.append(time.time()) or True) and len(win.tabs.t) > 25, timeout=60)
gaps = np.diff(ticks)
print(f"UI: {len(ticks)} ciclos de eventos durante el procesamiento, hueco maximo {gaps.max()*1000:.0f} ms")
win.on_pause()
pump(0.3)
print("estado:", win.lbl_state.text(), "| boton:", win.control.b_pause.text())
win.thread.step()
pump(0.3)
win.on_pause()                  # reanudar
pump(until=lambda: not win._running(), timeout=120)
pump(0.3)
cards = {k: (c.v.text(), c.s.text()) for k, c in win.analytics.cards.items()}
print("tarjetas:", cards)
assert cards["unique"][0] == "2"
assert cards["crossed"][0] == "2"
assert "km/h" in cards["avg"][1]
win.tabs.setCurrentIndex(2); pump(0.2)
win.grab().save(str(OUT / "gui_fixed.png"))
print("historial filas:", win.tabs.history.table.rowCount(),
      [win.tabs.history.table.item(0, c).text() for c in (2, 3, 5, 6)])

# 8) video vertical 9:16 y cuadrado: sin deformar
for (w, h, name) in ((360, 640, "vertical"), (480, 480, "cuadrado")):
    p = TMP / f"{name}.avi"
    make_fixed(p, w, h, secs=2)
    win.on_file_selected(str(p))
    app.processEvents()
    s, ox, oy = view._geom()
    iw, ih = view._size
    rw, rh = iw * s, ih * s
    assert abs(rw / rh - w / h) < 1e-6, (rw, rh)
    assert rw <= view.width() + 1 and rh <= view.height() + 1
    view.grab().save(str(OUT / f"gui_{name}.png"))
    print(f"{name} {w}x{h}: se muestra {rw:.0f}x{rh:.0f} dentro de {view.width()}x{view.height()} (proporcion {rw/rh:.3f} = {w/h:.3f})")

# 9) pantalla completa (modo offscreen: solo comprobar que alterna sin error)
win.toggle_fullscreen(); app.processEvents(); win._exit_fullscreen(); app.processEvents()
print("GUI OK")
