"""PDF Shrink compression engine.

Goal: get a PDF at or under a size limit while keeping it as readable as possible.

Strategy (stops at the first step that fits, so quality is only reduced as far as needed):
  0. Already small enough -> copy untouched.
  1. Lossless clean-up (compress streams, drop unused objects, strip metadata).
  2. Re-encode embedded images. Resolution is lowered only if needed, and within the
     resolution that fits, the HIGHEST JPEG quality that fits is chosen.
     Text and vector graphics are untouched, so text stays sharp and selectable.
  3. Last resort: re-draw every page as a JPEG picture (text is no longer selectable).

Everything runs locally. Nothing is uploaded anywhere.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Callable, Optional

import pymupdf

# Resolution stages tried in order (None = keep the original resolution).
IMAGE_DPI_STAGES = [None, 200, 150, 120, 96, 72, 60, 50]
MIN_IMAGE_QUALITY = 45  # never go below this while text is still kept sharp
MAX_IMAGE_QUALITY = 90

# Last-resort "flatten pages to pictures" stages: (dpi, quality). Best -> smallest.
RASTER_LADDER = [(200, 80), (150, 75), (150, 60), (120, 60), (100, 50),
                 (85, 45), (72, 40), (60, 35), (50, 30), (40, 25)]


class CompressionError(Exception):
    """A readable problem to show the user (bad file, password-protected, ...)."""


class Cancelled(Exception):
    """Raised when the user presses Cancel."""


@dataclass
class Result:
    src: str
    dst: Optional[str]
    original_bytes: int
    final_bytes: int
    reached_target: bool
    method: str  # human-readable description of what was done
    note: str = ""
    kind: str = "unchanged"  # copied | lossless | images | flattened | unchanged


Progress = Callable[[str], None]


def _size(path: str) -> int:
    return os.path.getsize(path)


def _open(src: str) -> pymupdf.Document:
    try:
        doc = pymupdf.open(src)
    except Exception as exc:  # noqa: BLE001 - surface any parser failure readably
        raise CompressionError("This doesn't look like a valid PDF. It may be damaged or not really a PDF.") from exc
    if doc.needs_pass:
        doc.close()
        raise CompressionError("This PDF is password-protected. Remove the password first.")
    if doc.page_count == 0:
        doc.close()
        raise CompressionError("This PDF has no pages.")
    return doc


def _save_clean(doc: pymupdf.Document, path: str) -> None:
    doc.set_metadata({})  # strips author/title/producer etc.
    doc.save(path, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True, clean=True)


def _try_images(src: str, dpi: Optional[int], quality: int, out: str) -> int:
    doc = _open(src)
    try:
        kwargs = dict(quality=quality)
        if dpi is not None:
            # Only touch images sharper than the target; scale them down to the target.
            kwargs.update(dpi_threshold=dpi + 1, dpi_target=dpi)
        doc.rewrite_images(**kwargs)
        _save_clean(doc, out)
    finally:
        doc.close()
    return _size(out)


def _estimate_raster(src: str, dpi: int, quality: int, samples: int = 3) -> float:
    """Cheaply estimate the flattened size by rendering a few evenly spaced pages."""
    doc = _open(src)
    try:
        n = doc.page_count
        idx = sorted({int(i * (n - 1) / max(samples - 1, 1)) for i in range(min(samples, n))})
        total = 0
        for i in idx:
            pix = doc[i].get_pixmap(dpi=dpi, alpha=False)
            total += len(pix.tobytes("jpeg", jpg_quality=quality))
        return total / len(idx) * n
    finally:
        doc.close()


def _try_raster(src: str, dpi: int, quality: int, out: str) -> int:
    doc = _open(src)
    new = pymupdf.open()
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            data = pix.tobytes("jpeg", jpg_quality=quality)
            np_ = new.new_page(width=page.rect.width, height=page.rect.height)
            np_.insert_image(np_.rect, stream=data)
        new.save(out, garbage=4, deflate=True)
    finally:
        new.close()
        doc.close()
    return _size(out)


def _img_label(dpi: Optional[int], q: int) -> str:
    return f"images re-encoded at quality {q}" + (f", max {dpi} DPI" if dpi else "")


def compress_pdf(
    src: str,
    dst: str,
    max_bytes: int,
    progress: Optional[Progress] = None,
    allow_flatten: bool = True,
    cancelled: Optional[Callable[[], bool]] = None,
) -> Result:
    """Compress ``src`` into ``dst`` aiming for ``max_bytes`` or less."""
    say = progress or (lambda _m: None)

    def check() -> None:
        if cancelled and cancelled():
            raise Cancelled()

    original = _size(src)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)

    # Validate up front so errors are clear and fast.
    _open(src).close()

    if original <= max_bytes:
        shutil.copyfile(src, dst)
        return Result(src, dst, original, original, True, "Already under the limit, copied as is", kind="copied")

    with tempfile.TemporaryDirectory(prefix="pdfshrink_") as tmp:
        cand = os.path.join(tmp, "cand.pdf")
        best = {"path": None, "size": original, "method": "unchanged", "kind": "unchanged"}

        def keep_if_better(size: int, method: str, force: bool = False, kind: str = "images") -> None:
            # "force" is used for results that fit the limit: among those, higher quality
            # (i.e. larger but still fitting) is better than a smaller, blurrier one.
            if force or size < best["size"]:
                keep = os.path.join(tmp, "best.pdf")
                shutil.copyfile(cand, keep)
                best.update(path=keep, size=size, method=method, kind=kind)

        def finish(reached: bool, note: str = "") -> Result:
            if best["path"] is None:  # nothing beat the original
                shutil.copyfile(src, dst)
                return Result(src, dst, original, original, original <= max_bytes,
                              "Could not shrink further",
                              note or "This PDF is already as small as it can get without damaging it.")
            shutil.copyfile(best["path"], dst)
            return Result(src, dst, original, best["size"], reached, best["method"], note, best["kind"])

        # Step 1: lossless
        check()
        say("Cleaning up (lossless)…")
        doc = _open(src)
        try:
            _save_clean(doc, cand)
        finally:
            doc.close()
        s = _size(cand)
        keep_if_better(s, "Lossless clean-up (no quality loss)", kind="lossless")
        if s <= max_bytes:
            return finish(True)

        # Step 2: re-encode embedded images. For each resolution stage, first check the lowest
        # acceptable quality; if even that is too big, move to a lower resolution. Once a stage
        # fits, search for the highest quality that still fits.
        for dpi in IMAGE_DPI_STAGES:
            check()
            say(f"Trying images at {'original' if dpi is None else str(dpi) + ' DPI'} resolution…")
            try:
                s = _try_images(src, dpi, MIN_IMAGE_QUALITY, cand)
            except CompressionError:
                raise
            except Exception as exc:  # noqa: BLE001
                say(f"Skipped a step ({exc}).")
                continue
            if s > max_bytes:
                keep_if_better(s, f"Text kept sharp; {_img_label(dpi, MIN_IMAGE_QUALITY)}")
                continue
            keep_if_better(s, f"Text kept sharp; {_img_label(dpi, MIN_IMAGE_QUALITY)}", force=True)
            lo, hi = MIN_IMAGE_QUALITY, MAX_IMAGE_QUALITY  # lo fits; find the largest that fits
            while hi - lo > 3:
                check()
                mid = (lo + hi) // 2
                try:
                    s = _try_images(src, dpi, mid, cand)
                except Exception:  # noqa: BLE001
                    hi = mid
                    continue
                if s <= max_bytes:
                    keep_if_better(s, f"Text kept sharp; {_img_label(dpi, mid)}", force=True)
                    lo = mid
                else:
                    hi = mid
            return finish(True)

        # Step 3: flatten pages to pictures (skip rungs that clearly cannot fit)
        if allow_flatten:
            for dpi, q in RASTER_LADDER:
                check()
                label = f"pages converted to pictures at {dpi} DPI, quality {q}"
                say(f"Trying: {label}…")
                try:
                    if _estimate_raster(src, dpi, q) > max_bytes * 1.3:
                        continue
                    s = _try_raster(src, dpi, q, cand)
                except Exception as exc:  # noqa: BLE001
                    say(f"Skipped a step ({exc}).")
                    continue
                keep_if_better(s, f"Text no longer selectable; {label}", kind="flattened")
                if s <= max_bytes:
                    return finish(True)

        return finish(False, "Could not reach the limit; this is the smallest readable result. "
                             "Try a higher limit.")


def unique_path(folder: str, filename: str) -> str:
    """Return a path in ``folder`` that does not overwrite anything."""
    base, ext = os.path.splitext(filename)
    path = os.path.join(folder, filename)
    n = 1
    while os.path.exists(path):
        path = os.path.join(folder, f"{base} ({n}){ext}")
        n += 1
    return path


def find_pdfs(folder: str, recursive: bool = False) -> list[str]:
    found: list[str] = []
    if recursive:
        for root, _dirs, files in os.walk(folder):
            found += [os.path.join(root, f) for f in files if f.lower().endswith(".pdf")]
    else:
        found = [os.path.join(folder, f) for f in os.listdir(folder)
                 if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(folder, f))]
    return sorted(found)


def human_size(n: float) -> str:
    # Decimal units (1 MB = 1,000,000 bytes) to match what macOS Finder shows.
    if n < 1000:
        return f"{n:.0f} B"
    if n < 1000 ** 2:
        return f"{n / 1000:.0f} KB"
    if n < 1000 ** 3:
        return f"{n / 1000 ** 2:.2f} MB"
    return f"{n / 1000 ** 3:.2f} GB"
