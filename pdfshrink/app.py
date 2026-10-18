"""PDF Shrink - the window."""

from __future__ import annotations

import os
import sys
from typing import Optional

from PySide6.QtCore import QObject, QSettings, QThread, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import engine

APP_NAME = "PDF Shrink"
PRESETS = [("200 KB", 0.2, "MB"), ("500 KB", 0.5, "MB"), ("1 MB", 1.0, "MB"), ("2 MB", 2.0, "MB")]
SHORT = {"copied": "already small enough", "lossless": "no quality loss", "images": "text kept sharp",
         "flattened": "pages turned into pictures", "unchanged": "could not shrink further"}
COL_NAME, COL_BEFORE, COL_AFTER, COL_STATUS = range(4)


def default_output_dir() -> str:
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    base = desktop if os.path.isdir(desktop) else os.path.expanduser("~")
    return os.path.join(base, "Compressed PDFs")


class Worker(QObject):
    """Runs compression off the UI thread."""

    started_file = Signal(int)
    step = Signal(int, str)
    finished_file = Signal(int, object, str)  # index, Result|None, error text
    all_done = Signal()

    def __init__(self, files: list[str], out_dir: str, max_bytes: int, allow_flatten: bool):
        super().__init__()
        self.files, self.out_dir = files, out_dir
        self.max_bytes, self.allow_flatten = max_bytes, allow_flatten
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        for i, src in enumerate(self.files):
            if self._cancel:
                break
            self.started_file.emit(i)
            try:
                dst = self._dst_for(src)
                res = engine.compress_pdf(
                    src, dst, self.max_bytes,
                    progress=lambda m, i=i: self.step.emit(i, m),
                    allow_flatten=self.allow_flatten,
                    cancelled=lambda: self._cancel,
                )
                self.finished_file.emit(i, res, "")
            except engine.Cancelled:
                self.finished_file.emit(i, None, "Cancelled")
                break
            except engine.CompressionError as exc:
                self.finished_file.emit(i, None, str(exc))
            except Exception as exc:  # noqa: BLE001 - never crash the app on one bad file
                self.finished_file.emit(i, None, f"Unexpected problem: {exc}")
        self.all_done.emit()

    def _dst_for(self, src: str) -> str:
        name = os.path.basename(src)
        same_folder = os.path.abspath(os.path.dirname(src)) == os.path.abspath(self.out_dir)
        if same_folder:  # never overwrite the original
            name = os.path.splitext(name)[0] + " - compressed.pdf"
        os.makedirs(self.out_dir, exist_ok=True)
        return engine.unique_path(self.out_dir, name)


class DropZone(QFrame):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("dropzone")
        self.setStyleSheet(
            "#dropzone { border: 2px dashed palette(mid); border-radius: 10px; }"
            "#dropzone[hover='true'] { border-color: palette(highlight); }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        self.label = QLabel("Drop PDFs or folders here")
        self.label.setAlignment(Qt.AlignCenter)
        f = self.label.font(); f.setPointSize(f.pointSize() + 3); self.label.setFont(f)
        self.sub = QLabel("or use the buttons below")
        self.sub.setAlignment(Qt.AlignCenter)
        self.sub.setEnabled(False)
        lay.addWidget(self.label)
        lay.addWidget(self.sub)

    def _hover(self, on: bool) -> None:
        self.setProperty("hover", "true" if on else "false")
        self.style().unpolish(self); self.style().polish(self)

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction(); self._hover(True)

    def dragLeaveEvent(self, _e) -> None:
        self._hover(False)

    def dropEvent(self, e: QDropEvent) -> None:
        self._hover(False)
        self.files_dropped.emit([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(760, 680)
        self.settings = QSettings("PDFShrink", "PDFShrink")
        self.files: list[str] = []
        self.thread: Optional[QThread] = None
        self.worker: Optional[Worker] = None
        self._build()

    # ---- UI ----
    def _build(self) -> None:
        root = QWidget(); self.setCentralWidget(root)
        v = QVBoxLayout(root); v.setSpacing(12); v.setContentsMargins(18, 16, 18, 16)

        self.drop = DropZone(); self.drop.setMinimumHeight(86)
        self.drop.files_dropped.connect(self.add_paths)
        v.addWidget(self.drop)

        row = QHBoxLayout()
        b_files = QPushButton("Add PDFs…"); b_files.clicked.connect(self.pick_files)
        b_folder = QPushButton("Add Folder…"); b_folder.clicked.connect(self.pick_folder)
        self.sub_cb = QCheckBox("Include subfolders")
        b_clear = QPushButton("Clear list"); b_clear.clicked.connect(self.clear_files)
        row.addWidget(b_files); row.addWidget(b_folder); row.addWidget(self.sub_cb)
        row.addStretch(); row.addWidget(b_clear)
        v.addLayout(row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File", "Before", "After", "Result"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        h = self.tree.header()
        h.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        h.setSectionResizeMode(COL_BEFORE, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_AFTER, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_STATUS, QHeaderView.Stretch)
        v.addWidget(self.tree, 1)

        # size limit
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Make each PDF no bigger than"))
        self.size_spin = QDoubleSpinBox(); self.size_spin.setDecimals(2)
        self.size_spin.setRange(0.01, 9999); self.size_spin.setValue(1.0)
        self.size_spin.setFixedWidth(90)
        self.unit = QComboBox(); self.unit.addItems(["KB", "MB"]); self.unit.setCurrentText("MB")
        r2.addWidget(self.size_spin); r2.addWidget(self.unit); r2.addSpacing(8)
        for text, val, unit in PRESETS:
            b = QPushButton(text); b.setFlat(False)
            b.clicked.connect(lambda _=False, val=val, unit=unit: self.set_limit(val, unit))
            r2.addWidget(b)
        r2.addStretch()
        v.addLayout(r2)

        # output folder
        r3 = QHBoxLayout()
        r3.addWidget(QLabel("Save compressed files in"))
        self.out_edit = QLineEdit(self.settings.value("out_dir", default_output_dir()))
        self.out_edit.setReadOnly(True)
        b_out = QPushButton("Choose…"); b_out.clicked.connect(self.pick_output)
        r3.addWidget(self.out_edit, 1); r3.addWidget(b_out)
        v.addLayout(r3)

        self.flatten_cb = QCheckBox("If needed, allow turning pages into pictures to reach the limit "
                                    "(text will no longer be selectable)")
        self.flatten_cb.setChecked(True)
        v.addWidget(self.flatten_cb)

        # run
        r4 = QHBoxLayout()
        self.run_btn = QPushButton("Compress"); self.run_btn.setDefault(True)
        self.run_btn.setMinimumHeight(34); self.run_btn.clicked.connect(self.start)
        self.cancel_btn = QPushButton("Cancel"); self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel)
        self.show_btn = QPushButton("Show in Finder" if sys.platform == "darwin" else "Open folder")
        self.show_btn.clicked.connect(self.reveal)
        r4.addWidget(self.run_btn, 1); r4.addWidget(self.cancel_btn); r4.addWidget(self.show_btn)
        v.addLayout(r4)

        self.progress = QProgressBar(); self.progress.setTextVisible(False); self.progress.setFixedHeight(8)
        self.status = QLabel("Add some PDFs to begin. Everything stays on your computer.")
        self.status.setEnabled(False)
        v.addWidget(self.progress); v.addWidget(self.status)

    # ---- file list ----
    def set_limit(self, val: float, unit: str) -> None:
        self.unit.setCurrentText(unit)
        self.size_spin.setValue(val)

    def max_bytes(self) -> int:
        mult = 1000 if self.unit.currentText() == "KB" else 1000 * 1000  # decimal, like Finder
        return int(self.size_spin.value() * mult)

    def pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose PDFs", self.settings.value("last_dir", os.path.expanduser("~")),
                                                "PDF files (*.pdf *.PDF)")
        if paths:
            self.add_paths(paths)

    def pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose a folder of PDFs", self.settings.value("last_dir", os.path.expanduser("~")))
        if d:
            self.add_paths([d])

    def add_paths(self, paths: list[str]) -> None:
        added = 0
        for p in paths:
            found: list[str] = []
            if os.path.isdir(p):
                found = engine.find_pdfs(p, recursive=self.sub_cb.isChecked())
                self.settings.setValue("last_dir", p)
            elif p.lower().endswith(".pdf") and os.path.isfile(p):
                found = [p]
                self.settings.setValue("last_dir", os.path.dirname(p))
            for f in found:
                if f in self.files:
                    continue
                self.files.append(f)
                it = QTreeWidgetItem([os.path.basename(f), engine.human_size(os.path.getsize(f)), "", "Waiting"])
                it.setToolTip(COL_NAME, f)
                it.setData(0, Qt.UserRole, f)
                self.tree.addTopLevelItem(it)
                added += 1
        if added:
            self.status.setText(f"{len(self.files)} PDF{'s' if len(self.files) != 1 else ''} ready.")
        elif paths:
            self.status.setText("No PDFs found in what you added.")

    def clear_files(self) -> None:
        if self.thread:
            return
        self.files.clear(); self.tree.clear(); self.progress.setValue(0)
        self.status.setText("Add some PDFs to begin. Everything stays on your computer.")

    def pick_output(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Where should the compressed PDFs go?", self.out_edit.text())
        if d:
            self.out_edit.setText(d)
            self.settings.setValue("out_dir", d)

    def reveal(self) -> None:
        d = self.out_edit.text()
        if os.path.isdir(d):
            QDesktopServices.openUrl(QUrl.fromLocalFile(d))
        else:
            self.status.setText("That folder doesn't exist yet. It is created when you compress.")

    # ---- running ----
    def _item(self, i: int) -> QTreeWidgetItem:
        return self.tree.topLevelItem(i)

    def start(self) -> None:
        if not self.files:
            QMessageBox.information(self, APP_NAME, "Add at least one PDF first.")
            return
        out = self.out_edit.text().strip()
        if not out:
            self.pick_output(); out = self.out_edit.text().strip()
            if not out:
                return
        self.settings.setValue("out_dir", out)
        for i in range(self.tree.topLevelItemCount()):
            self._item(i).setText(COL_AFTER, ""); self._item(i).setText(COL_STATUS, "Waiting")
        self.progress.setRange(0, len(self.files)); self.progress.setValue(0)
        self.run_btn.setEnabled(False); self.cancel_btn.setEnabled(True)
        self._ok = self._bad = 0

        self.thread = QThread()
        self.worker = Worker(list(self.files), out, self.max_bytes(), self.flatten_cb.isChecked())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.started_file.connect(self.on_started)
        self.worker.step.connect(self.on_step)
        self.worker.finished_file.connect(self.on_finished_file)
        self.worker.all_done.connect(self.on_all_done)
        self.thread.start()

    def cancel(self) -> None:
        if self.worker:
            self.worker.cancel(); self.status.setText("Cancelling…")

    def on_started(self, i: int) -> None:
        self._item(i).setText(COL_STATUS, "Working…")
        self.status.setText(f"Compressing {i + 1} of {len(self.files)}: {os.path.basename(self.files[i])}")

    def on_step(self, i: int, msg: str) -> None:
        self._item(i).setText(COL_STATUS, msg)

    def on_finished_file(self, i: int, res, err: str) -> None:
        it = self._item(i)
        if res is None:
            it.setText(COL_STATUS, err or "Failed")
            it.setToolTip(COL_STATUS, err)
            self._bad += 1
        else:
            it.setText(COL_AFTER, engine.human_size(res.final_bytes))
            if res.reached_target:
                it.setText(COL_STATUS, "Done  (" + SHORT.get(res.kind, "ok") + ")")
                self._ok += 1
            else:
                it.setText(COL_STATUS, "Still over the limit. Try a bigger limit.")
                self._bad += 1
            it.setToolTip(COL_STATUS, f"{res.method}. {res.note}".strip())
        self.progress.setValue(i + 1)

    def on_all_done(self) -> None:
        self.thread.quit(); self.thread.wait()
        self.thread = None; self.worker = None
        self.run_btn.setEnabled(True); self.cancel_btn.setEnabled(False)
        msg = f"Finished: {self._ok} done"
        if self._bad:
            msg += f", {self._bad} need attention (see the Result column)"
        self.status.setText(msg + f". Saved in {self.out_edit.text()}")

    def closeEvent(self, e) -> None:
        if self.worker:
            self.worker.cancel()
        if self.thread:
            self.thread.quit(); self.thread.wait(3000)
        e.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("PDFShrink")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
