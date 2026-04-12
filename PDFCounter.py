# IMPORTANT:
# Run this script from the folder where the file is located.
# Example:
# cd Desktop
# pyinstaller --onefile --windowed pdf_color_bw_counter_app.py

import importlib
import json
import os
import re
import sys
import hashlib
import hmac
import subprocess
from pathlib import Path

# Hints for PyInstaller static analysis:
# the imports below are intentionally unreachable at runtime, but help
# PyInstaller discover optional GUI modules when building from this script.
if False:  # pragma: no cover
    from PySide6 import QtCore as _QtCoreHint
    from PySide6 import QtGui as _QtGuiHint
    from PySide6 import QtWidgets as _QtWidgetsHint
    import tkinter as _TkHint
    import tkinter.filedialog as _TkFileDialogHint
    import tkinter.messagebox as _TkMessageBoxHint
    import tkinter.simpledialog as _TkSimpleDialogHint
    import tkinter.ttk as _TtkHint


APP_TITLE = "PDF Color / Black-and-White Counter"
COPYRIGHT_TEXT = "© Achim Pieters 2026"
UNREGISTERED_PAGE_LIMIT = 25
LICENSE_SIGNING_CODE = os.environ.get("PDFCOUNTER_LICENSE_SIGNING_CODE", "PDFCounter-Default-Signing-Code")
LICENSE_FILE = Path.home() / ".pdfcounter_license.json"


def _load_gui_backend():
    """Load a supported GUI backend without try/except around import statements."""
    try:
        qtcore = importlib.import_module("PySide6.QtCore")
        qtgui = importlib.import_module("PySide6.QtGui")
        qtwidgets = importlib.import_module("PySide6.QtWidgets")
    except Exception:
        qtcore = None
        qtgui = None
        qtwidgets = None

    if qtcore and qtgui and qtwidgets:
        globals().update(
            {
                "Qt": qtcore.Qt,
                "Signal": qtcore.Signal,
                "QSize": qtcore.QSize,
                "QAction": qtgui.QAction,
                "QFont": qtgui.QFont,
                "QPalette": qtgui.QPalette,
                "QColor": qtgui.QColor,
                "QAbstractSpinBox": qtwidgets.QAbstractSpinBox,
                "QApplication": qtwidgets.QApplication,
                "QFileDialog": qtwidgets.QFileDialog,
                "QDoubleSpinBox": qtwidgets.QDoubleSpinBox,
                "QFormLayout": qtwidgets.QFormLayout,
                "QFrame": qtwidgets.QFrame,
                "QGridLayout": qtwidgets.QGridLayout,
                "QGroupBox": qtwidgets.QGroupBox,
                "QHBoxLayout": qtwidgets.QHBoxLayout,
                "QLabel": qtwidgets.QLabel,
                "QLineEdit": qtwidgets.QLineEdit,
                "QInputDialog": qtwidgets.QInputDialog,
                "QMainWindow": qtwidgets.QMainWindow,
                "QMessageBox": qtwidgets.QMessageBox,
                "QPushButton": qtwidgets.QPushButton,
                "QSizePolicy": qtwidgets.QSizePolicy,
                "QSpinBox": qtwidgets.QSpinBox,
                "QStackedWidget": qtwidgets.QStackedWidget,
                "QStyle": qtwidgets.QStyle,
                "QTabBar": qtwidgets.QTabBar,
                "QTabWidget": qtwidgets.QTabWidget,
                "QTextBrowser": qtwidgets.QTextBrowser,
                "QToolBar": qtwidgets.QToolBar,
                "QToolButton": qtwidgets.QToolButton,
                "QVBoxLayout": qtwidgets.QVBoxLayout,
                "QWidget": qtwidgets.QWidget,
            }
        )
        return "pyside6"

    linux_headless = sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    if linux_headless:
        return None

    try:
        tkinter_module = importlib.import_module("tkinter")
        filedialog_module = importlib.import_module("tkinter.filedialog")
        messagebox_module = importlib.import_module("tkinter.messagebox")
        simpledialog_module = importlib.import_module("tkinter.simpledialog")
        ttk_module = importlib.import_module("tkinter.ttk")
    except Exception:
        return None

    globals().update(
        {
            "tk": tkinter_module,
            "filedialog": filedialog_module,
            "messagebox": messagebox_module,
            "simpledialog": simpledialog_module,
            "ttk": ttk_module,
        }
    )
    return "tkinter"


GUI_BACKEND = _load_gui_backend()


def load_fitz():
    """Load PyMuPDF robustly."""
    errors = []

    try:
        import pymupdf as fitz  # PyMuPDF
        return fitz
    except Exception as exc:
        errors.append(f"pymupdf import failed: {exc}")

    try:
        import fitz  # type: ignore
        return fitz
    except Exception as exc:
        errors.append(f"fitz import failed: {exc}")

    message = (
        "PyMuPDF is not available in this Python environment.\n\n"
        "Install it using the same Python interpreter that starts this app:\n"
        "python -m pip install --upgrade pymupdf\n\n"
        "If you previously installed the wrong `fitz` package, remove it first:\n"
        "python -m pip uninstall -y fitz\n\n"
        "Technical details:\n- "
        + "\n- ".join(errors)
    )
    raise RuntimeError(message)


def normalize_email(email):
    return email.strip().lower()


def generate_serial(email, serial_code=LICENSE_SIGNING_CODE):
    clean_email = normalize_email(email)
    digest = hmac.new(
        serial_code.encode("utf-8"),
        clean_email.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().upper()
    compact = digest[:25]
    return "-".join(compact[i:i + 5] for i in range(0, len(compact), 5))


def normalize_serial(serial):
    return re.sub(r"[^A-Z0-9]", "", serial.upper())


def is_valid_license(email, serial):
    expected = normalize_serial(generate_serial(email))
    return hmac.compare_digest(normalize_serial(serial), expected)


def save_license(email, serial):
    LICENSE_FILE.write_text(
        json.dumps({"email": normalize_email(email), "serial": serial}, indent=2),
        encoding="utf-8",
    )


def load_license():
    if not LICENSE_FILE.exists():
        return None
    try:
        data = json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None

    email = data.get("email", "")
    serial = data.get("serial", "")
    if not email or not serial:
        return None
    return {"email": email, "serial": serial}


def is_registered():
    license_data = load_license()
    if not license_data:
        return False
    return is_valid_license(license_data["email"], license_data["serial"])


def is_color_page(page, fitz_module, tolerance=12, min_color_ratio=0.001, dpi=24):
    scale = dpi / 72.0
    pix = page.get_pixmap(
        matrix=fitz_module.Matrix(scale, scale),
        colorspace=fitz_module.csRGB,
        alpha=False,
    )

    samples = pix.samples
    channels = pix.n
    total_pixels = pix.width * pix.height

    if total_pixels == 0:
        return False

    min_color_pixels = max(1, int(total_pixels * min_color_ratio))
    color_pixels = 0

    for i in range(0, len(samples), channels):
        r = samples[i]
        g = samples[i + 1]
        b = samples[i + 2]

        if (
            abs(r - g) > tolerance
            or abs(g - b) > tolerance
            or abs(r - b) > tolerance
        ):
            color_pixels += 1
            if color_pixels >= min_color_pixels:
                return True

    return False


def count_pdf_pages(pdf_path, tolerance=12, min_color_ratio=0.001, dpi=24, page_limit=None):
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"File does not exist: {pdf_path}")

    if not pdf_path.is_file():
        raise FileNotFoundError(f"Path is not a file: {pdf_path}")

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"File is not a PDF: {pdf_path.name}")

    fitz = load_fitz()
    doc = fitz.open(str(pdf_path))
    try:
        color_pages = 0
        bw_pages = 0

        pages_to_scan = len(doc) if page_limit is None else min(len(doc), int(page_limit))

        for page_index in range(pages_to_scan):
            page = doc[page_index]
            if is_color_page(
                page,
                fitz_module=fitz,
                tolerance=tolerance,
                min_color_ratio=min_color_ratio,
                dpi=dpi,
            ):
                color_pages += 1
            else:
                bw_pages += 1

        return pages_to_scan, color_pages, bw_pages
    finally:
        doc.close()


if GUI_BACKEND == "pyside6":
    class DropArea(QFrame):
        file_dropped = Signal(str)

        def __init__(self):
            super().__init__()
            self.setAcceptDrops(True)
            self.setObjectName("dropArea")
            self.setFrameShape(QFrame.StyledPanel)
            self._build_ui()

        def _build_ui(self):
            layout = QVBoxLayout(self)
            layout.setContentsMargins(22, 22, 22, 22)
            layout.setSpacing(6)

            self.icon_label = QLabel()
            self.icon_label.setAlignment(Qt.AlignCenter)
            self.icon_label.setPixmap(
                self.style().standardIcon(QStyle.SP_DialogOpenButton).pixmap(28, 28)
            )

            self.title_label = QLabel("Drop a PDF here")
            self.title_label.setObjectName("dropTitle")
            self.title_label.setAlignment(Qt.AlignCenter)

            self.subtitle_label = QLabel("or use Open in the toolbar")
            self.subtitle_label.setObjectName("secondaryText")
            self.subtitle_label.setAlignment(Qt.AlignCenter)

            layout.addStretch()
            layout.addWidget(self.icon_label)
            layout.addWidget(self.title_label)
            layout.addWidget(self.subtitle_label)
            layout.addStretch()

        def _set_dragging(self, dragging):
            self.setProperty("dragging", dragging)
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()

        def dragEnterEvent(self, event):
            if event.mimeData().hasUrls():
                for url in event.mimeData().urls():
                    if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf"):
                        event.acceptProposedAction()
                        self._set_dragging(True)
                        return
            event.ignore()

        def dragLeaveEvent(self, event):
            self._set_dragging(False)
            super().dragLeaveEvent(event)

        def dropEvent(self, event):
            self._set_dragging(False)
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if path.lower().endswith(".pdf"):
                        self.file_dropped.emit(path)
                        event.acceptProposedAction()
                        return
            event.ignore()


    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setAcceptDrops(True)
            self.setWindowTitle(APP_TITLE)
            self.setUnifiedTitleAndToolBarOnMac(True)
            self.setMinimumSize(860, 600)
            self._apply_palette()
            self._create_menu()
            self._create_toolbar()
            self._build_ui()

        def _apply_palette(self):
            self.setStyleSheet(
                """
                QLabel#dropTitle {
                    font-size: 19px;
                    font-weight: 600;
                }
                QLabel#secondaryText {
                    color: palette(mid);
                }
                QFrame#dropArea {
                    border: 1px dashed palette(mid);
                    border-radius: 8px;
                }
                QFrame#dropArea[dragging="true"] {
                    border: 2px solid palette(highlight);
                }
                QLabel#footerText {
                    font-size: 12px;
                }
                """
            )

        def _create_menu(self):
            menubar = self.menuBar()
            app_menu = menubar.addMenu("App")

            open_action = QAction("Open…", self)
            open_action.triggered.connect(self.browse_pdf)
            open_action.setShortcut("Ctrl+O")
            app_menu.addAction(open_action)

            analyze_action = QAction("Analyze", self)
            analyze_action.triggered.connect(self.analyze_pdf)
            analyze_action.setShortcut("Ctrl+R")
            app_menu.addAction(analyze_action)
            app_menu.addSeparator()

            register_action = QAction("Register License", self)
            register_action.triggered.connect(self.register_license)
            app_menu.addAction(register_action)

            about_action = QAction("About", self)
            about_action.triggered.connect(self.show_about)
            app_menu.addAction(about_action)

            help_action = QAction("How to Use", self)
            help_action.triggered.connect(self.show_help_view)
            app_menu.addAction(help_action)

            app_menu.addSeparator()

            quit_action = QAction("Quit", self)
            quit_action.triggered.connect(self.close)
            quit_action.setShortcut("Ctrl+Q")
            app_menu.addAction(quit_action)

        def _create_toolbar(self):
            toolbar = QToolBar("Main Toolbar", self)
            toolbar.setMovable(False)
            toolbar.setFloatable(False)
            toolbar.setIconSize(QSize(18, 18))
            self.addToolBar(toolbar)
            self.toolbar = toolbar

            open_button = QToolButton()
            open_button.setText("Open")
            open_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            open_button.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
            open_button.clicked.connect(self.browse_pdf)
            toolbar.addWidget(open_button)

            spacer = QWidget()
            spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            toolbar.addWidget(spacer)

            help_button = QToolButton()
            help_button.setText("Help")
            help_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            help_button.clicked.connect(self.show_help_view)
            toolbar.addWidget(help_button)

        def show_about(self):
            QMessageBox.information(
                self,
                "About",
                "PDF Color / Black-and-White Counter\n\n"
                "Counts visible color and black-and-white pages in PDF files for print-cost estimation.\n\n"
                f"License status: {self.license_status_text()}\n\n"
                f"{COPYRIGHT_TEXT}",
            )

        def license_status_text(self):
            license_data = load_license()
            if is_registered() and license_data:
                return f"Registered to {license_data['email']}"
            return f"Unregistered (max {UNREGISTERED_PAGE_LIMIT} pages per scan)"

        def register_license(self):
            email, ok = QInputDialog.getText(self, "Register License", "Email address:")
            if not ok or not email.strip():
                return

            serial, ok = QInputDialog.getText(self, "Register License", "Serial key:")
            if not ok or not serial.strip():
                return

            if is_valid_license(email, serial):
                save_license(email, serial)
                QMessageBox.information(self, APP_TITLE, "License activated successfully.")
                return

            QMessageBox.warning(self, APP_TITLE, "Invalid email/serial combination.")

        def _build_ui(self):
            central = QWidget()
            self.setCentralWidget(central)

            root = QVBoxLayout(central)
            root.setContentsMargins(16, 12, 16, 14)
            root.setSpacing(12)

            self.counter_page = QWidget()
            self._build_counter_page()

            footer = QLabel(COPYRIGHT_TEXT)
            footer.setObjectName("footerText")
            footer.setAlignment(Qt.AlignCenter)

            root.addWidget(self.counter_page, 1)
            root.addWidget(footer)

        def _build_counter_page(self):
            root = QVBoxLayout(self.counter_page)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(12)

            file_group = QGroupBox("Document")
            file_layout = QVBoxLayout(file_group)
            file_layout.setSpacing(10)

            self.drop_area = DropArea()
            self.drop_area.file_dropped.connect(self.set_pdf_path)
            self.drop_area.setMinimumHeight(132)

            file_row = QHBoxLayout()
            file_row.setSpacing(10)

            self.file_edit = QLineEdit()
            self.file_edit.setPlaceholderText("Choose a PDF file or drop one here")
            self.file_edit.setClearButtonEnabled(True)

            browse_button = QPushButton("Open…")
            browse_button.clicked.connect(self.browse_pdf)

            file_row.addWidget(self.file_edit, 1)
            file_row.addWidget(browse_button)

            file_layout.addWidget(self.drop_area)
            file_layout.addLayout(file_row)

            settings_group = QGroupBox("Settings")
            settings_layout = QFormLayout(settings_group)
            settings_layout.setLabelAlignment(Qt.AlignLeft)
            settings_layout.setFormAlignment(Qt.AlignTop)
            settings_layout.setHorizontalSpacing(14)
            settings_layout.setVerticalSpacing(10)

            self.tolerance_spin = QSpinBox()
            self.tolerance_spin.setRange(0, 255)
            self.tolerance_spin.setValue(12)
            self.tolerance_spin.setButtonSymbols(QAbstractSpinBox.UpDownArrows)

            self.ratio_spin = QDoubleSpinBox()
            self.ratio_spin.setRange(0.0001, 1.0)
            self.ratio_spin.setDecimals(4)
            self.ratio_spin.setSingleStep(0.0005)
            self.ratio_spin.setValue(0.0010)
            self.ratio_spin.setButtonSymbols(QAbstractSpinBox.UpDownArrows)

            self.dpi_spin = QSpinBox()
            self.dpi_spin.setRange(12, 300)
            self.dpi_spin.setValue(24)
            self.dpi_spin.setButtonSymbols(QAbstractSpinBox.UpDownArrows)

            tolerance_label = QLabel("Tolerance")
            ratio_label = QLabel("Min. color ratio")
            dpi_label = QLabel("DPI")

            settings_layout.addRow(tolerance_label, self.tolerance_spin)
            settings_layout.addRow(ratio_label, self.ratio_spin)
            settings_layout.addRow(dpi_label, self.dpi_spin)

            actions_row = QHBoxLayout()
            actions_row.addStretch()

            analyze_button = QPushButton("Analyze PDF")
            analyze_button.setDefault(True)
            analyze_button.clicked.connect(self.analyze_pdf)
            actions_row.addWidget(analyze_button)

            results_group = QGroupBox("Results")
            results_layout = QFormLayout(results_group)
            results_layout.setLabelAlignment(Qt.AlignLeft)
            results_layout.setFormAlignment(Qt.AlignTop)
            results_layout.setHorizontalSpacing(22)
            results_layout.setVerticalSpacing(8)

            self.total_value = QLabel("—")
            self.color_value = QLabel("—")
            self.bw_value = QLabel("—")
            for label in (self.total_value, self.color_value, self.bw_value):
                label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                value_font = QFont(label.font())
                value_font.setPointSize(max(16, value_font.pointSize() + 8))
                value_font.setWeight(QFont.DemiBold)
                label.setFont(value_font)

            results_layout.addRow(QLabel("Total pages"), self.total_value)
            results_layout.addRow(QLabel("Color pages"), self.color_value)
            results_layout.addRow(QLabel("Black-and-white pages"), self.bw_value)

            root.addWidget(file_group)
            root.addWidget(settings_group)
            root.addLayout(actions_row)
            root.addWidget(results_group)
            root.addStretch()

        def show_help_view(self):
            QMessageBox.information(
                self,
                "How to Use",
                "1. Open a PDF from the toolbar, or drag a PDF into the drop area.\n"
                "2. Adjust settings if needed.\n"
                "3. Click Analyze PDF.\n"
                "4. Read totals in Results.\n\n"
                "Settings:\n"
                "- Tolerance: color sensitivity between RGB channels.\n"
                "- Min. color ratio: fraction of colored pixels needed.\n"
                "- DPI: render resolution for analysis.",
            )

        def set_pdf_path(self, path):
            self.file_edit.setText(path)

        def dragEnterEvent(self, event):
            if event.mimeData().hasUrls():
                for url in event.mimeData().urls():
                    if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf"):
                        event.acceptProposedAction()
                        return
            event.ignore()

        def dropEvent(self, event):
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if path.lower().endswith(".pdf"):
                        self.set_pdf_path(path)
                        event.acceptProposedAction()
                        return
            event.ignore()

        def browse_pdf(self):
            filename, _ = QFileDialog.getOpenFileName(
                self,
                "Open PDF",
                str(Path.home()),
                "PDF files (*.pdf)",
            )
            if filename:
                self.set_pdf_path(filename)

        def analyze_pdf(self):
            pdf_path = self.file_edit.text().strip()

            if not pdf_path:
                QMessageBox.warning(self, APP_TITLE, "Please choose a PDF file first.")
                return

            try:
                page_limit = None if is_registered() else UNREGISTERED_PAGE_LIMIT
                total_pages, color_pages, bw_pages = count_pdf_pages(
                    pdf_path,
                    tolerance=self.tolerance_spin.value(),
                    min_color_ratio=self.ratio_spin.value(),
                    dpi=self.dpi_spin.value(),
                    page_limit=page_limit,
                )
            except Exception as exc:
                QMessageBox.critical(self, APP_TITLE, f"Analysis failed:\n{exc}")
                return

            if not is_registered():
                QMessageBox.information(
                    self,
                    APP_TITLE,
                    f"Unregistered mode: only the first {UNREGISTERED_PAGE_LIMIT} pages were scanned.",
                )

            self.total_value.setText(str(total_pages))
            self.color_value.setText(str(color_pages))
            self.bw_value.setText(str(bw_pages))


if GUI_BACKEND == "tkinter":
    class TkApp:
        def __init__(self):
            self.root = tk.Tk()
            self.root.title(APP_TITLE)
            self.root.minsize(760, 440)
            self._build_ui()

        def _build_ui(self):
            container = ttk.Frame(self.root, padding=12)
            container.pack(fill="both", expand=True)

            notebook = ttk.Notebook(container)
            notebook.pack(fill="both", expand=True)

            counter_tab = ttk.Frame(notebook, padding=12)
            help_tab = ttk.Frame(notebook, padding=12)
            notebook.add(counter_tab, text="Counter")
            notebook.add(help_tab, text="Help")

            file_frame = ttk.LabelFrame(counter_tab, text="Document", padding=10)
            file_frame.pack(fill="x", pady=(0, 10))

            self.file_var = tk.StringVar()
            ttk.Entry(file_frame, textvariable=self.file_var).pack(side="left", fill="x", expand=True)
            ttk.Button(file_frame, text="Open…", command=self.browse_pdf).pack(side="left", padx=(8, 0))
            ttk.Button(file_frame, text="Register", command=self.register_license).pack(side="left", padx=(8, 0))

            settings = ttk.LabelFrame(counter_tab, text="Settings", padding=10)
            settings.pack(fill="x", pady=(0, 10))

            self.tolerance_var = tk.IntVar(value=12)
            self.ratio_var = tk.DoubleVar(value=0.0010)
            self.dpi_var = tk.IntVar(value=24)

            ttk.Label(settings, text="Tolerance:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Spinbox(settings, from_=0, to=255, textvariable=self.tolerance_var, width=10).grid(row=0, column=1, sticky="w", pady=4)
            ttk.Label(settings, text="Min. color ratio:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Spinbox(settings, from_=0.0001, to=1.0, increment=0.0005, textvariable=self.ratio_var, width=10).grid(row=1, column=1, sticky="w", pady=4)
            ttk.Label(settings, text="DPI:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Spinbox(settings, from_=12, to=300, textvariable=self.dpi_var, width=10).grid(row=2, column=1, sticky="w", pady=4)

            ttk.Button(counter_tab, text="Analyze PDF", command=self.analyze_pdf).pack(anchor="e", pady=(0, 10))

            result_frame = ttk.LabelFrame(counter_tab, text="Results", padding=10)
            result_frame.pack(fill="x")

            self.total_var = tk.StringVar(value="—")
            self.color_var = tk.StringVar(value="—")
            self.bw_var = tk.StringVar(value="—")

            ttk.Label(result_frame, text="Total pages:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Label(result_frame, textvariable=self.total_var).grid(row=0, column=1, sticky="w", pady=4)
            ttk.Label(result_frame, text="Color pages:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Label(result_frame, textvariable=self.color_var).grid(row=1, column=1, sticky="w", pady=4)
            ttk.Label(result_frame, text="Black-and-white pages:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Label(result_frame, textvariable=self.bw_var).grid(row=2, column=1, sticky="w", pady=4)

            ttk.Label(counter_tab, text=COPYRIGHT_TEXT, justify="center").pack(fill="x", pady=(12, 0))

            help_copy = tk.Text(help_tab, wrap="word", height=18)
            help_copy.insert(
                "1.0",
                "PDF Color / Black-and-White Counter\n\n"
                "This app counts visible color pages and black-and-white pages in a PDF for print-cost estimation.\n\n"
                "How to use it:\n"
                "1. Open a PDF.\n"
                "2. Adjust the settings if needed.\n"
                "3. Click Analyze PDF.\n\n"
                "Settings:\n"
                "- Tolerance: how different RGB values must be before a pixel counts as color.\n"
                "- Min. color ratio: minimum colored area needed before a page counts as color.\n"
                "- DPI: render resolution used for analysis.\n"
            )
            help_copy.configure(state="disabled")
            help_copy.pack(fill="both", expand=True)

        def browse_pdf(self):
            filename = filedialog.askopenfilename(
                title="Open PDF",
                initialdir=str(Path.home()),
                filetypes=[("PDF files", "*.pdf")],
            )
            if filename:
                self.file_var.set(filename)

        def analyze_pdf(self):
            pdf_path = self.file_var.get().strip()

            if not pdf_path:
                messagebox.showwarning(APP_TITLE, "Please choose a PDF file first.")
                return

            try:
                page_limit = None if is_registered() else UNREGISTERED_PAGE_LIMIT
                total_pages, color_pages, bw_pages = count_pdf_pages(
                    pdf_path,
                    tolerance=int(self.tolerance_var.get()),
                    min_color_ratio=float(self.ratio_var.get()),
                    dpi=int(self.dpi_var.get()),
                    page_limit=page_limit,
                )
            except Exception as exc:
                messagebox.showerror(APP_TITLE, f"Analysis failed:\n{exc}")
                return

            if not is_registered():
                messagebox.showinfo(
                    APP_TITLE,
                    f"Unregistered mode: only the first {UNREGISTERED_PAGE_LIMIT} pages were scanned.",
                )

            self.total_var.set(str(total_pages))
            self.color_var.set(str(color_pages))
            self.bw_var.set(str(bw_pages))

        def register_license(self):
            email = simpledialog.askstring(APP_TITLE, "Email address:")
            if not email:
                return
            serial = simpledialog.askstring(APP_TITLE, "Serial key:")
            if not serial:
                return
            if is_valid_license(email, serial):
                save_license(email, serial)
                messagebox.showinfo(APP_TITLE, "License activated successfully.")
            else:
                messagebox.showwarning(APP_TITLE, "Invalid email/serial combination.")

        def run(self):
            self.root.mainloop()


def run_cli():
    if len(sys.argv) >= 3 and sys.argv[1] == "--generate-serial":
        email = sys.argv[2]
        print(generate_serial(email))
        return 0

    if len(sys.argv) < 2:
        print("Usage: python PDFCounter.py file.pdf")
        print("Or run the script in an environment with PySide6 or tkinter for the graphical interface.")
        return 2

    pdf_path = sys.argv[1]

    try:
        page_limit = None if is_registered() else UNREGISTERED_PAGE_LIMIT
        total_pages, color_pages, bw_pages = count_pdf_pages(pdf_path, page_limit=page_limit)
    except Exception as exc:
        print(f"Error: {exc}")
        return 1

    print(f"Total pages             : {total_pages}")
    print(f"Color pages             : {color_pages}")
    print(f"Black-and-white pages   : {bw_pages}")
    return 0


def show_startup_error(message):
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, APP_TITLE, 0x10)
            return
        except Exception:
            pass

    if sys.platform == "darwin":
        escaped = message.replace("\\", "\\\\").replace('"', '\\"')
        script = f'display alert "{APP_TITLE}" message "{escaped}" as critical'
        try:
            subprocess.run(["osascript", "-e", script], check=False)
            return
        except Exception:
            pass

    print(message)


def main():
    if GUI_BACKEND == "pyside6":
        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()
        app.exec()
        return 0

    if GUI_BACKEND == "tkinter":
        TkApp().run()
        return 0

    if getattr(sys, "frozen", False) and len(sys.argv) < 2:
        show_startup_error(
            "No GUI toolkit was packaged, so the app cannot stay open in windowed mode.\n\n"
            "Make sure PySide6 is installed in the same Python environment, then rebuild with:\n"
            "python -m PyInstaller --onefile --windowed --icon PDFCounter.icns "
            "--collect-submodules PySide6 --collect-data PySide6 PDFCounter.py"
        )
        return 1

    return run_cli()


if __name__ == "__main__":
    sys.exit(main())


# Manual test cases:
# 1. Start the app without PyMuPDF: the app should still open and only show a clear install message when analysis starts.
# 2. Choose a non-existing path: the app should show a clean error that the file does not exist.
# 3. Choose a PDF with only grayscale pages: all pages should count as black-and-white.
# 4. Choose a PDF with some color pages: total = color + black-and-white.
# 5. Increase "Min. color ratio" and verify that pages with tiny traces of color are less likely to count as color.
# 6. Lower DPI for speed and verify that the app still gives usable results.
# 7. Accidentally install the wrong `fitz` package: the app should show technical details in the analysis error.
# 8. Start the app in an environment without a PDF analysis package but with PySide6: the GUI should still open without crashing.
# 9. Start the app without PySide6 but with tkinter: the tkinter GUI should open and remain usable.
# 10. Start the app without PySide6 and without tkinter and pass a PDF path as an argument: CLI output should show the three count lines.
# 11. Start the app without a GUI backend and without an argument: CLI should show a short usage message without a traceback.
# 12. Use the same PDF in PySide6, tkinter, and CLI mode: the results should be identical.
# 13. In CLI mode, pass a path to a non-existing file: a clean error should appear without a traceback.
# 14. In CLI mode, pass a non-PDF file: a clean error should appear without a traceback.
# 15. Start the PySide6 version and force an analysis failure: the error dialog should show a correct multi-line message without a syntax error.
# 16. Open the About dialog from the menu: it should show the app name, description, and copyright text.
# 17. Drag a PDF onto the drop area in the PySide6 UI: the file path should update automatically.
# 18. Drag a PDF anywhere onto the main PySide6 window: the file path should update automatically.
# 19. Switch between Counter and Help using the segmented control: the visible page should switch.
# 20. The main Counter view should use a toolbar, grouped content, and a light native-looking appearance.
