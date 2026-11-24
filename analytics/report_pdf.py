"""Reporte PDF opcional (matplotlib PdfPages, sin dependencias extra)."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def _text_page(pdf, title, text):
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.text(0.07, 0.95, title, fontsize=16, weight="bold", va="top")
    fig.text(0.07, 0.91, text, fontsize=7.5, va="top", family="monospace")
    pdf.savefig(fig)
    plt.close(fig)


def build_pdf(folder: Path, summary: dict, config: dict, images: list):
    """Resumen + configuracion + graficas ya generadas (PNG)."""
    path = folder / "report.pdf"
    with PdfPages(path) as pdf:
        s = {k: v for k, v in summary.items() if k not in ("files", "notes")}
        _text_page(pdf, "Vision Tracker - Resumen de sesion",
                   json.dumps(s, indent=1, ensure_ascii=False, default=str)[:6500])
        _text_page(pdf, "Configuracion utilizada",
                   json.dumps(config, indent=1, ensure_ascii=False, default=str)[:6500])
        for img in images:
            p = folder / img
            if not p.exists():
                continue
            fig = plt.figure(figsize=(8.27, 11.69))
            ax = fig.add_axes([0.05, 0.1, 0.9, 0.8])
            ax.imshow(plt.imread(str(p)))
            ax.axis("off")
            fig.text(0.5, 0.93, img, ha="center", fontsize=11)
            pdf.savefig(fig)
            plt.close(fig)
    return path.name
