# PDFCounter

PDFCounter is a desktop + CLI utility that estimates how many pages in a PDF are **color** versus **black-and-white (grayscale)** for print-cost planning.

---

## Deep Code Audit (April 10, 2026)

This repository currently contains a single application module (`PDFCounter.py`) with:
- PDF analysis logic (`count_pdf_pages`, `is_color_page`)
- GUI frontends (PySide6 preferred, tkinter fallback)
- CLI fallback mode

### What was audited
- Import/loading strategy for GUI and PDF engine dependencies.
- Input validation and runtime error handling.
- CLI behavior and process exit semantics.
- Headless environment behavior.
- Algorithm characteristics and practical limitations.
- Security posture (file handling and code execution risks).

### Key findings

#### ✅ Strengths
- Clear file validation before analysis (exists/file/`.pdf` suffix checks).
- Robust PyMuPDF loading path with actionable install guidance when unavailable.
- Defensive page analysis guard for empty rendered pages.
- GUI + CLI fallback architecture keeps tool usable across environments.

#### ⚠️ Risks / limitations
- The color-detection heuristic is pixel-threshold-based and can misclassify:
  - near-grayscale tints,
  - scanned pages with compression noise,
  - pages where tiny colored logos are either ignored or over-counted depending on settings.
- Runtime cost scales with page count and DPI; large PDFs can become slow at higher DPI.
- Results are best considered **print-estimation** metrics, not strict document-color ground truth.

### Audit-driven fixes applied
- Reworked GUI backend discovery to avoid direct try/except-wrapped imports; now uses module discovery + dynamic import with graceful fallback if a backend is present but unusable at runtime.
- Improved CLI correctness:
  - usage text now references the real script name (`PDFCounter.py`);
  - exit code `2` for bad CLI invocation;
  - exit code `1` for analysis/runtime errors;
  - exit code `0` on success.
- Added headless safety: tkinter backend is skipped on Linux when no display server is detected (`DISPLAY`/`WAYLAND_DISPLAY`), allowing clean CLI fallback instead of crashing.

---

## Requirements

- Python 3.10+ (tested in Python 3.12)
- PyMuPDF (`pymupdf`) for PDF analysis
- Optional GUI backend:
  - `PySide6` (preferred)
  - `tkinter` (usually bundled with Python, may require OS packages)

Install analyzer dependency:

```bash
python -m pip install --upgrade pymupdf
```

Optional (for richer UI):

```bash
python -m pip install --upgrade PySide6
```

---

## Usage

### GUI mode

If PySide6 is installed (or tkinter is available with a display), run:

```bash
python PDFCounter.py
```

### CLI mode

If no GUI backend is available (or in headless environments), run with a PDF path:

```bash
python PDFCounter.py /path/to/file.pdf
```

Output:
- Total pages
- Color pages
- Black-and-white pages

Exit codes:
- `0` success
- `1` runtime/analysis error
- `2` incorrect CLI usage

---

## Detection settings explained

- **Tolerance** (0–255): minimum RGB channel distance to treat a pixel as color.
  - Higher => stricter color detection (fewer pages classified as color).
- **Min. color ratio** (0.0001–1.0): minimum colored-pixel fraction before a page is counted as color.
  - Higher => tiny color traces less likely to mark page as color.
- **DPI** (12–300): render resolution used for analysis.
  - Lower => faster, less precise.
  - Higher => slower, potentially more precise.

Recommended defaults:
- Tolerance: `12`
- Min. color ratio: `0.0010`
- DPI: `24`

---

## Known limitations

- Classification is heuristic-based and intentionally optimized for speed.
- Transparency/blending and anti-aliased text can affect edge cases.
- Encrypted or malformed PDFs may fail to open depending on PyMuPDF behavior.
- Very large or image-heavy PDFs can consume substantial CPU time.

---

## License

See `LICENSE`.

---

## Continuous Integration

GitHub Actions runs a CI workflow on every push and pull request that:
- compiles `PDFCounter.py` (`python -m py_compile PDFCounter.py`)
- runs unit tests in `tests/test_pdfcounter.py`
