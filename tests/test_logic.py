"""Pruebas de la logica pura (sin interfaz ni YOLO). Ejecutar: python -m tests.test_logic"""
import math
import numpy as np
import cv2

from core.line_counter import LineCounter
from core.speed_estimator import SpeedEstimator
from core.calibration import Calibration
from odometry.camera_compensation import CameraCompensator


def test_line_counter():
    lc = LineCounter(margin=6, cooldown=1.0)
    lc.set_line((100, 0), (100, 200))            # linea vertical
    # objeto que cruza de izquierda a derecha, con jitter junto a la linea
    xs = [60, 80, 96, 99, 101, 98, 102, 104, 120, 140]
    evs = [lc.update(1, "car", (x, 100), i * 0.1, i) for i, x in enumerate(xs)]
    evs = [e for e in evs if e]
    assert len(evs) == 1, f"un solo conteo esperado, hubo {len(evs)}"
    # objeto detenido pegado a la linea: nunca cuenta
    for i in range(50):
        assert lc.update(2, "car", (100 + (i % 3) - 1, 50), i * 0.1, i) is None
    # cruce en sentido contrario
    for i, x in enumerate([140, 120, 90, 70]):
        lc.update(3, "person", (x, 100), 10 + i * 0.1, i)
    assert lc.total == 2 and lc.count_ab + lc.count_ba == 2
    assert {e["direction"] for e in lc.events} == {"A->B", "B->A"}
    # cruce fuera del segmento no cuenta
    lc2 = LineCounter()
    lc2.set_line((100, 0), (100, 200))
    for i, x in enumerate([60, 140]):
        assert lc2.update(9, "car", (x, 500), i, i) is None
    print("line_counter OK")


def test_speed_and_calibration():
    se = SpeedEstimator(window_s=0.5, min_dt_s=0.2)
    # 100 px/s a fps VARIABLE (timestamps irregulares)
    t, x, last = 0.0, 0.0, None
    for dt in [0.03, 0.04, 0.033, 0.05, 0.02, 0.033] * 10:
        t += dt
        x = 100.0 * t
        last = se.update(1, t, (x, 50))
    assert abs(last.px_s - 100) < 5, last.px_s
    assert last.direction == "→"
    # calibracion: rectangulo 10m x 20m dibujado como cuadrilatero en perspectiva
    cal = Calibration()
    cal.set([(300, 100), (500, 100), (600, 400), (200, 400)], 10.0, 20.0)
    w0 = cal.to_world((300, 100))
    w1 = cal.to_world((600, 400))
    assert abs(w0[0]) < 1e-3 and abs(w0[1]) < 1e-3
    assert abs(w1[0] - 10) < 1e-3 and abs(w1[1] - 20) < 1e-3
    # movimiento de 10 m en 1 s dentro del plano -> 36 km/h
    se2 = SpeedEstimator(window_s=0.5, min_dt_s=0.2)
    out = None
    for i in range(61):
        tt = i / 30.0
        wy = 5 + 10 * tt                      # metros
        out = se2.update(1, tt, (0, 0), (2.0, wy))
    assert abs(out.kmh - 36) < 1.0, out.kmh
    # cuadrilatero no convexo -> error
    try:
        Calibration().set([(0, 0), (100, 100), (100, 0), (0, 100)], 1, 1)
        raise AssertionError("debio fallar")
    except ValueError:
        pass
    assert not cal.inside((10, 10)) and cal.inside((400, 250))
    print("speed/calibration OK")


def _textured(w=640, h=480, seed=0):
    rng = np.random.default_rng(seed)
    img = (rng.random((h, w, 3)) * 255).astype(np.uint8)
    img = cv2.GaussianBlur(img, (0, 0), 1.2)
    for _ in range(80):
        cv2.circle(img, (int(rng.integers(0, w)), int(rng.integers(0, h))),
                   int(rng.integers(4, 18)), tuple(int(v) for v in rng.integers(0, 255, 3)), -1)
    return img


def test_camera_compensation():
    big = _textured(1400, 700, 1)
    comp = CameraCompensator()
    obj_world = np.array([700.0, 350.0])         # objeto QUIETO en el mundo
    refs = []
    for i in range(30):
        ox, oy = 100 + i * 8, 80 + i * 3          # camara se desplaza (paneo)
        frame = big[oy:oy + 480, ox:ox + 640].copy()
        res = comp.update(frame, [])
        assert res.valid, (i, res.reason)
        px = (obj_world[0] - ox, obj_world[1] - oy)   # donde se VE el objeto
        refs.append(comp.to_reference(px))
    refs = np.array(refs)
    spread = np.linalg.norm(refs - refs.mean(0), axis=1).max()
    raw_motion = math.hypot(29 * 8, 29 * 3)
    assert spread < 3.0, spread
    print(f"camera compensation OK (movimiento aparente {raw_motion:.0f}px -> dispersion compensada {spread:.2f}px)")
    # sin textura -> estimacion NO confiable y la transformacion no cambia
    comp2 = CameraCompensator()
    comp2.update(big[0:480, 0:640].copy())
    T_before = comp2.T.copy()
    flat = np.full((480, 640, 3), 128, np.uint8)
    r = comp2.update(flat)
    assert not r.valid and np.allclose(comp2.T, T_before)
    print("invalid estimation handled OK:", r.reason)


if __name__ == "__main__":
    test_line_counter()
    test_speed_and_calibration()
    test_camera_compensation()
    print("TODAS LAS PRUEBAS DE LOGICA PASARON")
