"""Dibujo de cajas, IDs, trayectorias, linea virtual y HUD sobre el fotograma original.

Se dibuja siempre a la resolucion original: la interfaz solo escala la imagen final,
asi las coordenadas coinciden con las del video aunque se visualice reducido.
"""
import colorsys
import math

import cv2
import numpy as np


ALERT_COLOR = (0, 0, 255)      # BGR: rojo reservado para el exceso de velocidad


def color_for(tid: int):
    # el matiz evita el rango rojo para que solo la alerta de velocidad use ese color
    h = 0.12 + 0.72 * ((tid * 0.61803398875) % 1.0)
    r, g, b = colorsys.hsv_to_rgb(h, 0.75, 1.0)
    return int(b * 255), int(g * 255), int(r * 255)


def _label(img, text, org, color, scale, thick):
    (tw, th), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    x, y = int(org[0]), int(org[1])
    x = max(0, min(x, img.shape[1] - tw - 6))      # que la etiqueta no se salga del fotograma
    y = max(th + base + 2, y)
    cv2.rectangle(img, (x, y - th - base - 2), (x + tw + 4, y + 2), color, -1)
    cv2.putText(img, text, (x + 2, y - base // 2), cv2.FONT_HERSHEY_SIMPLEX, scale,
                (0, 0, 0), thick, cv2.LINE_AA)


def render_frame(frame, tracks, session, disp: dict, comp=None, motion=None):
    """Devuelve una copia del fotograma con todas las anotaciones activas."""
    out = frame.copy()
    h, w = out.shape[:2]
    s = max(1.0, max(w, h) / 960.0)
    th = max(1, int(round(s)))
    fs = 0.5 * s
    use_comp = comp is not None and session.use_comp
    to_cur = comp.to_current if use_comp else (lambda p: p)

    # zona calibrada
    if session.has("calibration") and session.calib.valid:
        cv2.polylines(out, [session.calib.image_pts.astype(np.int32)], True,
                      (0, 200, 255), th, cv2.LINE_AA)

    # odometria visual (puntos, correspondencias, transformacion)
    if use_comp and disp.get("show_orb", True):
        comp.draw_overlay(out)
    elif use_comp and not comp.reliable:
        cv2.rectangle(out, (0, 0), (w, int(34 * s)), (0, 0, 160), -1)
        cv2.putText(out, f"COMPENSACION NO CONFIABLE: {comp.last.reason}", (10, int(24 * s)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6 * s, (255, 255, 255), th, cv2.LINE_AA)

    # trayectorias
    mode = disp.get("traj_mode", "all") if disp.get("show_traj", True) else "none"
    if mode != "none":
        ids = [disp.get("traj_id")] if mode == "single" else list(session.active_ids)
        for tid in ids:
            tail = session.traj.tails.get(tid)
            if not tail or len(tail) < 2:
                continue
            pts = [to_cur(p) for p in tail]
            col = color_for(tid)
            n = len(pts)
            for i in range(1, n):
                a = (int(pts[i - 1][0]), int(pts[i - 1][1]))
                b = (int(pts[i][0]), int(pts[i][1]))
                cv2.line(out, a, b, col, max(1, int(th * (0.5 + i / n))), cv2.LINE_AA)

    # linea virtual y contadores
    ln = session.line
    if session.has("line") and ln.defined:
        p1 = (int(ln.p1[0]), int(ln.p1[1]))
        p2 = (int(ln.p2[0]), int(ln.p2[1]))
        col = (0, 255, 255) if ln.enabled else (128, 128, 128)
        cv2.line(out, p1, p2, col, max(2, th + 1), cv2.LINE_AA)
        cv2.circle(out, p1, 5 * th, col, -1)
        cv2.circle(out, p2, 5 * th, col, -1)
        dx, dy = ln.p2[0] - ln.p1[0], ln.p2[1] - ln.p1[1]
        L = math.hypot(dx, dy)
        nx, ny = -dy / L, dx / L
        mx, my = (ln.p1[0] + ln.p2[0]) / 2, (ln.p1[1] + ln.p2[1]) / 2
        for tag, sg in (("A", -1), ("B", 1)):
            cv2.putText(out, tag, (int(mx + nx * 30 * s * sg) - 6, int(my + ny * 30 * s * sg) + 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8 * s, col, th + 1, cv2.LINE_AA)
        _label(out, f"A->B: {ln.count_ab}   B->A: {ln.count_ba}   Total: {ln.total}",
               (10, int(26 * s)), (0, 255, 255), 0.6 * s, th)

    # cajas, IDs, confianza, velocidad
    show_speed = disp.get("show_speed", True) and session.has("speed")
    limit = disp.get("speed_limit_kmh")
    # alerta solo en el radar (N1) y solo con calibracion valida y velocidad real disponible
    radar = session.profile == "radar" and session.calib.valid and session.has("calibration")
    for tr in tracks:
        col = color_for(tr.track_id)
        smp = session.last_sample.get(tr.track_id)
        over = bool(radar and limit and smp is not None and smp.kmh is not None
                    and smp.kmh > limit)
        if over:
            col = ALERT_COLOR
        if disp.get("show_boxes", True):
            cv2.rectangle(out, (int(tr.x1), int(tr.y1)), (int(tr.x2), int(tr.y2)), col,
                          th + (3 if over else 1))
        parts = []
        if disp.get("show_ids", True):
            parts.append(f"#{tr.track_id} {tr.cls_name}")
        if disp.get("show_conf", True):
            parts.append(f"{tr.conf:.2f}")
        if (show_speed or over) and smp is not None and smp.px_s is not None:
            if session.calib.valid and session.has("calibration") and smp.kmh is not None:
                parts.append(f"{smp.kmh:.0f} km/h")
            else:
                parts.append(f"{smp.px_s:.0f} px/s")
        if over:
            parts.append("EXCESO")
        if parts:
            _label(out, " | ".join(parts), (tr.x1, tr.y1 - 2), col, fs, th)
    return out
