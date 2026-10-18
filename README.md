# PDF Shrink

A small, free Mac app that makes PDFs smaller. Pick one PDF or a whole folder, say how big each file is allowed to be (for example **1 MB**), choose where the smaller copies go, and click **Compress**.

- **Private:** everything happens on your own Mac. Nothing is uploaded anywhere, and the app needs no internet.
- **Your originals are never changed.** Compressed copies are saved in the folder you choose.
- **Hits your size limit:** it only lowers quality as far as needed, and keeps text sharp and selectable whenever it can.
- **One file or many:** drop in a single PDF, several, or an entire folder.

## Install (about a minute)

1. Open the **[Releases page](../../releases/latest)** and download **`PDF-Shrink-apple-silicon.dmg`**.

   This app is for Macs with **Apple silicon** (M1 or newer, from late 2020 onward). To check, click the Apple menu → **About This Mac**: it should say *Chip: Apple M…* (or another Apple chip). Older Intel Macs aren't supported.
2. Open the `.dmg` and drag **PDF Shrink** onto the **Applications** shortcut.
3. Open **PDF Shrink** from Applications.

### The first time you open it, macOS will warn you

This app is free and open source, so it is not signed with a paid Apple developer certificate. macOS shows a warning for any such app. It is a one-time step:

1. Try to open **PDF Shrink**. macOS says it can't verify the app. Click **Done** (not "Move to Trash").
2. Open **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to *"PDF Shrink" was blocked*. Enter your password and confirm.

Prefer Terminal? This does the same thing:

```bash
xattr -dr com.apple.quarantine "/Applications/PDF Shrink.app"
```

## How to use it

1. **Add files:** drag PDFs or folders into the window, or use **Add PDFs…** / **Add Folder…** (tick *Include subfolders* first if you want those too).
2. **Set the limit:** type a number and choose KB or MB, or tap a preset (200 KB, 500 KB, 1 MB, 2 MB).
3. **Choose where to save:** click **Choose…** next to *Save compressed files in*.
4. Click **Compress**. The list shows each file's size before and after. Click **Show in Finder** when it's done.

Sizes use the same units as Finder (1 MB = 1,000,000 bytes), so a file set to "1 MB" will never show as larger than 1 MB.

### What the Result column means

| Result | Meaning |
| --- | --- |
| Done (already small enough) | The file was under your limit already, so it was just copied. |
| Done (no quality loss) | Tidied up the file's internals; nothing visible changed. |
| Done (text kept sharp) | Photos and scans inside the PDF were compressed. Text and drawings are untouched. |
| Done (pages turned into pictures) | The only way to reach your limit was to turn each page into an image. Looks the same, but you can't select or search the text. You can switch this off with the checkbox. |
| Still over the limit | Even the smallest readable result was bigger than your limit. Try a larger limit. |

Password-protected or damaged PDFs are skipped with a message. Remove the password first, then try again.

## How it works

PDF Shrink tries gentler methods first and stops at the first one that fits your limit: (1) a lossless clean-up, (2) re-compressing the images inside the PDF, lowering their resolution only if needed and choosing the highest JPEG quality that still fits, and (3) as a last resort, turning pages into pictures. The engine is [PyMuPDF](https://pymupdf.readthedocs.io/); the window is built with Qt ([PySide6](https://doc.qt.io/qtforpython-6/)).

## For developers

Run from source (macOS, Windows or Linux with Python 3.10+):

```bash
pip install -r requirements.txt
python -m pdfshrink
```

Run the tests:

```bash
pip install -r requirements-dev.txt
python tests/smoke_test.py
```

### Publishing a new version

The `.dmg` files are built automatically on GitHub's Mac servers (see `.github/workflows/build-mac.yml`). To publish a release, push a version tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

A few minutes later the `.dmg` file appears on the Releases page. Every normal push also runs the tests and builds the app as a downloadable artifact on the Actions tab.

## License

[GNU AGPL v3](LICENSE), because it uses PyMuPDF, which is AGPL-licensed. The source code is all in this repository.
