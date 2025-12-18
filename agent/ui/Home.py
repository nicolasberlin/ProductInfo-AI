# pip install PyQt6 qasync
import sys
import asyncio
from io import StringIO
from pathlib import Path
from contextlib import redirect_stderr

from qasync import QEventLoop, asyncSlot
from PyQt6.QtGui import QFontDatabase, QAction, QTextCursor, QColor, QStandardItemModel
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QPlainTextEdit,
    QLabel,
    QFileDialog,
    QMessageBox,
    QLineEdit,
    QSizePolicy,
    QProgressBar,
    QComboBox,
    QListView,
)

# Import analyse_url with fallback when running this file directly
try:
    from agent.llm_inference.core import analyse_url
except ModuleNotFoundError:
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
from agent.llm_inference.core import analyse_url
from agent.llm_inference.essential import (
    essentials_from_raw,
    filename_from_url,
    resolve_patents_with_api,
    write_essential,
)


class ModeComboBox(QComboBox):
    """Non-editable combo with a hidden placeholder row."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(False)
        self.setView(QListView())

        # Placeholder (visible in field, hidden in dropdown)
        self.addItem("Mode", userData=None)
        # Actual options
        self.addItem("Brevets", userData="patents")
        self.addItem("Produits", userData="products")
        self.addItem("Complet", userData="full")
        self.setCurrentIndex(0)

        # Disable placeholder and style it as a hint
        model = self.model()
        if isinstance(model, QStandardItemModel):
            it = model.item(0)
            if it is not None:
                it.setEnabled(False)
                it.setForeground(QColor("#9aa3b2"))

        # Hide placeholder from dropdown menu
        self.view().setRowHidden(0, True)


class ChatUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Product↔Patents — Analyse URL/PDF → OpenAI")
        self.resize(980, 760)

        # Style (Fusion recommended on macOS for consistent QSS)
        self.setStyleSheet(
            """
            QWidget { background: #f7f8fa; font-size: 14px; }

            QLineEdit {
                padding: 8px 10px;
                border: 1px solid #d0d5dd;
                border-radius: 10px;
                background: #ffffff;
                color: #0f172a;
            }
            QLineEdit:focus { border: 1px solid #6ea8fe; }

            QPushButton {
                padding: 8px 12px;
                border: 1px solid #d0d5dd;
                border-radius: 10px;
                background: #ffffff;
                color: #0f172a;
            }
            QPushButton:hover { background: #eef2f6; }
            QPushButton:disabled { color: #94a3b8; background: #ffffff; }

            QComboBox {
                padding: 8px 34px 8px 12px;
                border: 1px solid #d0d5dd;
                border-radius: 10px;
                background: #ffffff;
                color: #0f172a;
            }
            QComboBox:focus { border: 1px solid #6ea8fe; }
            QComboBox::drop-down { border: 0px; width: 28px; }

            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #0f172a;
                selection-background-color: #bee3f8;
                selection-color: #0f172a;
                border: 1px solid #d0d5dd;
                outline: 0;
                padding: 6px;
            }
            QComboBox QAbstractItemView::item { padding: 6px 10px; }

            QPlainTextEdit {
                border: 1px solid #d0d5dd;
                border-radius: 10px;
                background: #ffffff;
                color: #0f172a;
            }

            QLabel { color: #0f172a; }
            QLabel#SourceLabel { color: #334155; padding: 4px 2px; }

            QProgressBar { border: 1px solid #d0d5dd; border-radius: 6px; height: 10px; background: #ffffff; }
            QProgressBar::chunk { background-color: #6ea8fe; }
            """
        )

        self.full_source = ""  # URL ou chemin local
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # --- Top row
        top = QHBoxLayout()
        top.setSpacing(10)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Coller une URL PDF/HTML…")
        self.url_input.textChanged.connect(self.on_url_changed)
        self.url_input.returnPressed.connect(self.validate_source)

        self.validate_action = QAction("➤", self)
        self.validate_action.triggered.connect(self.validate_source)
        self.url_input.addAction(self.validate_action, QLineEdit.ActionPosition.TrailingPosition)
        top.addWidget(self.url_input, stretch=1)

        self.btn_open_pdf = QPushButton("PDF")
        self.btn_open_pdf.clicked.connect(self.open_pdf)
        top.addWidget(self.btn_open_pdf)

        # Mode dropdown with placeholder hidden from the popup
        self.mode_selector = ModeComboBox()
        self.mode_selector.setMinimumWidth(170)
        top.addWidget(self.mode_selector)

        self.send_button = QPushButton("Envoyer")
        self.send_button.clicked.connect(self.send_to_openai)
        self.send_button.setEnabled(False)  # enabled only when mode selected
        top.addWidget(self.send_button)

        # enable send when mode != placeholder
        self.mode_selector.currentIndexChanged.connect(self._sync_send_enabled)

        # Harmonize heights
        H = 38
        self.url_input.setFixedHeight(H)
        self.btn_open_pdf.setFixedHeight(H)
        self.mode_selector.setFixedHeight(H)
        self.send_button.setFixedHeight(H)

        layout.addLayout(top)

        # --- Source label
        self.source_label = QLabel("Aucune source sélectionnée")
        self.source_label.setObjectName("SourceLabel")
        layout.addWidget(self.source_label)

        # --- Output
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(mono)
        self.output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.output.setMinimumHeight(420)
        layout.addWidget(self.output)

        # --- Logs
        layout.addWidget(QLabel("Logs"))
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(mono)
        self.log_output.setMinimumHeight(160)
        layout.addWidget(self.log_output)

        # --- Status + busy
        self.status_label = QLabel("Choisir une source et un mode")
        layout.addWidget(self.status_label)

        busy_row = QHBoxLayout()
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)  # indéterminé
        self.busy.setVisible(False)
        busy_row.addWidget(self.busy)
        layout.addLayout(busy_row)

    def _sync_send_enabled(self, _i: int):
        self.send_button.setEnabled(self.mode_selector.currentData() is not None)

    def _short(self, s: str, n: int = 80) -> str:
        if len(s) <= n:
            return s
        head, tail = s[: int(n * 0.2)], s[-int(n * 0.75) :]
        return head + "…" + tail

    def _set_busy(self, on: bool, msg: str = ""):
        self.busy.setVisible(on)
        self.send_button.setDisabled(on)
        self.btn_open_pdf.setDisabled(on)
        self.url_input.setDisabled(on)
        self.mode_selector.setDisabled(on)
        if msg:
            self.status_label.setText(msg)

    def _reset_source(self, msg: str = "Aucune source sélectionnée"):
        self.full_source = ""
        self.source_label.setText("Aucune source sélectionnée")
        self.status_label.setText(msg)

    def _mark_source_ready(self, txt: str, is_file: bool):
        prefix = "PDF sélectionné" if is_file else "Source"
        self.full_source = txt
        self.source_label.setText(f"{prefix}: {self._short(txt)}")
        # keep status helpful but neutral
        self.status_label.setText("Source prête — choisir un mode")

    def _handle_source_text(self, txt: str, warn: bool) -> bool:
        txt = (txt or "").strip()
        if not txt:
            self._reset_source("Choisir une source et un mode")
            return False

        import os

        if os.path.exists(txt):
            self._mark_source_ready(txt, is_file=True)
            return True

        if txt.startswith(("http://", "https://", "file://")):
            self._mark_source_ready(txt, is_file=False)
            return True

        self._reset_source("Source invalide")
        if warn:
            QMessageBox.warning(self, "Source invalide", "Colle une URL http(s) ou un chemin PDF existant.")
        return False

    def on_url_changed(self, txt: str):
        self._handle_source_text(txt, warn=False)

    def validate_source(self, _checked: bool = False) -> bool:
        return self._handle_source_text(self.url_input.text(), warn=True)

    def open_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choisir un PDF", "", "PDF (*.pdf)")
        if path:
            self._mark_source_ready(path, is_file=True)

    @asyncSlot()
    async def send_to_openai(self):
        # validate source
        if not self.full_source:
            if not self.validate_source():
                return
        source = self.full_source or (self.url_input.text() or "").strip()
        if not source:
            QMessageBox.warning(self, "Aucune source", "Colle une URL ou importe un PDF.")
            return

        mode = self.mode_selector.currentData()
        if mode is None:
            QMessageBox.warning(self, "Mode manquant", "Choisis un mode (Brevets, Produits ou Complet).")
            return

        # UI placeholders
        self.output.setPlainText("[envoi en cours…]")
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        self.log_output.setPlainText("[capture logs…]")
        self.log_output.moveCursor(QTextCursor.MoveOperation.End)
        self.source_label.setText(f"Source: {self._short(source)}")

        self._set_busy(True, f"Envoi… (mode={mode})")
        log_buf = StringIO()

        try:
            with redirect_stderr(log_buf):
                answer = await analyse_url(source, mode=mode)

            logs = (log_buf.getvalue() or "").strip()
            # Écriture essentielle auto pour l'UI
            try:
                products, patents = essentials_from_raw(answer or "", mode)
                patents = resolve_patents_with_api(patents)
                out_dir = Path("agent") / "evaluation" / "reports"
                out_path = out_dir / filename_from_url(source, ext=".essential.ndjson")
                write_essential(out_path, source, products, patents)
                extra_log = f"[ESSENTIAL] Écrit {out_path}"
            except Exception as err:
                extra_log = f"[ESSENTIAL][erreur] {err}"

            self.output.setPlainText(answer or "[réponse vide]")
            merged_logs = "\n".join([l for l in [logs, extra_log] if l])
            self.log_output.setPlainText(merged_logs or "[aucun log]")
            self.status_label.setText(f"Réponse reçue (mode={mode})")
        except Exception as e:
            logs = (log_buf.getvalue() or "").strip()
            self.output.setPlainText(f"[Erreur] {e}")
            self.log_output.setPlainText(logs or "[aucun log]")
            self.status_label.setText("Erreur")
        finally:
            self._set_busy(False)
            # re-enable send according to mode selection
            self._sync_send_enabled(self.mode_selector.currentIndex())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    w = ChatUI()
    w.show()

    with loop:
        loop.run_forever()
