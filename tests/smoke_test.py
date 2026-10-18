"""Self-contained smoke test: builds sample PDFs, compresses them, drives the real window.

Run:  python tests/smoke_test.py      (needs requirements-dev.txt)
CI runs this on a real Mac before building the app.
"""
import io
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import numpy as np
import pymupdf
from PIL import Image

from pdfshrink import engine


def noisy_jpeg(w, h, q=92):
    rng = np.random.default_rng(1)
    arr = np.clip(235 + rng.integers(-25, 25, size=(h, w, 1)) + rng.integers(-6, 6, size=(h, w, 3)), 0, 255)
    b = io.BytesIO()
    Image.fromarray(arr.astype("uint8")).save(b, "JPEG", quality=q)
    return b.getvalue()


def make_scan(path):
    doc = pymupdf.open()
    for _ in range(2):
        p = doc.new_page(width=1000, height=1400)
        p.insert_image(p.rect, stream=noisy_jpeg(1000, 1400))
    doc.save(path)
    doc.close()


def make_text(path):
    doc = pymupdf.open()
    for i in range(3):
        p = doc.new_page()
        p.insert_text((72, 90), f"Hello page {i + 1}", fontsize=20)
        p.insert_image(pymupdf.Rect(72, 200, 520, 500), stream=noisy_jpeg(1800, 1200, 95))
    doc.save(path)
    doc.close()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        scan, text = os.path.join(tmp, "scan.pdf"), os.path.join(tmp, "text.pdf")
        make_scan(scan)
        make_text(text)
        limit = int(0.5 * 1000 * 1000)

        for src in (scan, text):
            dst = os.path.join(tmp, "out", os.path.basename(src))
            r = engine.compress_pdf(src, dst, limit)
            size = os.path.getsize(dst)
            print(f"{os.path.basename(src)}: {r.original_bytes} -> {size} bytes ({r.method})")
            assert r.reached_target and size <= limit, "did not reach the limit"
            assert pymupdf.open(dst).page_count == pymupdf.open(src).page_count, "page count changed"
        assert "Hello page 1" in pymupdf.open(os.path.join(tmp, "out", "text.pdf"))[0].get_text()

        # the real window, end to end
        from PySide6.QtCore import QEventLoop, QSettings, QTimer
        from PySide6.QtWidgets import QApplication
        from pdfshrink.app import MainWindow

        QSettings("PDFShrink", "PDFShrink").clear()
        app = QApplication([])
        w = MainWindow()
        out = os.path.join(tmp, "ui_out")
        w.out_edit.setText(out)
        w.add_paths([tmp])
        assert len(w.files) == 2, w.files
        w.set_limit(500, "KB")
        assert w.max_bytes() == 500_000
        loop = QEventLoop()
        QTimer.singleShot(0, w.start)
        t = QTimer()
        t.setInterval(200)
        t.timeout.connect(lambda: (w.thread is None and w.progress.value() == 2) and loop.quit())
        t.start()
        QTimer.singleShot(180000, loop.quit)
        loop.exec()
        assert sorted(os.listdir(out)) == ["scan.pdf", "text.pdf"], os.listdir(out)
        assert all(os.path.getsize(os.path.join(out, f)) <= 500_000 for f in os.listdir(out))
        w.close()
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
