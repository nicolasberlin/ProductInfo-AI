# pip install PyQt6
import sys
from agent import llm_inference
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase, QFont, QAction, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QPlainTextEdit, QLabel, QFileDialog, QMessageBox, QLineEdit,
    QSizePolicy, QProgressBar
)

class ChatUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Product↔Patents — Analyse URL/PDF → OpenAI")
        self.resize(900, 700)

        # Style moderne
        self.setStyleSheet(
            """
            QWidget { background: #f7f8fa; font-size: 14px; }

            /* Champ URL lisible en clair comme en sombre */
            QLineEdit {
                padding: 8px 2px 8px 10px;
                border: 1px solid #d0d5dd;
                border-radius: 8px;
                background: #ffffff;
                color: #0f172a;                /* texte */
                selection-background-color: #bee3f8;
                selection-color: #0f172a;
            }
            QLineEdit:focus { border: 1px solid #6ea8fe; }
            QLineEdit::placeholder { color: #9aa3b2; }

            /* Libellés et boutons lisibles */
            QLabel { color: #0f172a; }
            QLabel#SourceLabel { color: #334155; padding: 4px 2px; }

            QPushButton {
                padding: 8px 12px;
                border: 1px solid #d0d5dd;
                border-radius: 8px;
                background: #ffffff;
                color: #0f172a;
            }
            QPushButton:hover { background: #eef2f6; }

            /* Zone texte générique (si utilisée ailleurs) */
            QPlainTextEdit {
                border: 1px solid #d0d5dd;
                border-radius: 8px;
                background: #ffffff;
                color: #0f172a;              /* texte sombre sur fond clair */
            }

            /* Sortie principale en mode terminal lisible */
            #Output {
                background: #ffffff;
                color: #0f172a;              /* texte sombre sur fond clair */
                border-color: #d0d5dd;
            }

            /* Barre de progression */
            QProgressBar { border: 1px solid #d0d5dd; border-radius: 6px; height: 10px; background: #ffffff; }
            QProgressBar::chunk { background-color: #6ea8fe; }
            """
        )

        self.full_source = ""  # URL ou chemin local
        layout = QVBoxLayout(self)

        # Ligne du haut : URL + flèche de validation + PDF + Envoyer
        top = QHBoxLayout()

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Coller une URL PDF/HTML…")
        self.url_input.returnPressed.connect(self.validate_source)
        # Trailing action with icon inside the line edit (right side)
        self.validate_action = QAction("➤", self)
        self.validate_action.triggered.connect(self.validate_source)
        self.url_input.addAction(self.validate_action, QLineEdit.ActionPosition.TrailingPosition)
        top.addWidget(self.url_input)

        self.btn_open_pdf = QPushButton("PDF")
        self.btn_open_pdf.clicked.connect(self.open_pdf)
        top.addWidget(self.btn_open_pdf)

        self.send_button = QPushButton("Envoyer")
        self.send_button.clicked.connect(self.send_to_openai)
        top.addWidget(self.send_button)

        layout.addLayout(top)

        # Label source compact
        self.source_label = QLabel("Aucune source sélectionnée")
        self.source_label.setObjectName("SourceLabel")
        layout.addWidget(self.source_label)

        # Grande zone de réponse
        self.output = QPlainTextEdit()
        self.output.setObjectName("Output")
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.output.setFont(mono)
        self.output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.output.setMinimumHeight(500)
        layout.addWidget(self.output)

        # Statut + barre de progression
        self.status_label = QLabel("Aucune source sélectionnée")
        layout.addWidget(self.status_label)

        busy_row = QHBoxLayout()
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)  # indéterminé
        self.busy.setVisible(False)
        busy_row.addWidget(self.busy)
        layout.addLayout(busy_row)

                # Entrée libre pour parler directement à OpenAI
        bottom = QHBoxLayout()
        self.free_input = QLineEdit()
        self.free_input.setPlaceholderText("Écris directement ta question…")
        self.free_input.returnPressed.connect(self.send_free_text)
        bottom.addWidget(self.free_input)

        self.free_send = QPushButton("➤")
        self.free_send.setToolTip("Envoyer le message libre")
        self.free_send.clicked.connect(self.send_free_text)
        bottom.addWidget(self.free_send)

        layout.addLayout(bottom)

    def _short(self, s: str, n: int = 80) -> str:
        if len(s) <= n:
            return s
        head, tail = s[: int(n * 0.2)], s[-int(n * 0.75) :]
        return head + "…" + tail

    def validate_source(self):
        txt = self.url_input.text().strip()
        if not txt:
            return
        import os
        if os.path.exists(txt):
            self.full_source = txt
            self.source_label.setText(f"PDF sélectionné: {self._short(txt)}")
            self.status_label.setText("<font color='green'>Prêt à envoyer</font>")
            return
        if txt.startswith(("http://", "https://", "file://")):
            self.full_source = txt
            self.source_label.setText(f"Source: {self._short(txt)}")
            self.status_label.setText("<font color='green'>Prêt à envoyer</font>")
            return
        QMessageBox.warning(self, "Source invalide", "Colle une URL http(s) ou un chemin PDF existant.")
        
    def send_free_text(self):
        text = self.free_input.text().strip()
        if not text:
            return
        # Busy ON
        self.busy.setVisible(True)
        self.send_button.setDisabled(True)
        self.btn_open_pdf.setDisabled(True)
        self.free_send.setDisabled(True)
        self.url_input.setDisabled(True)
        self.free_input.setDisabled(True)
        self.status_label.setText("Envoi…")

        try:
            # log exact input to terminal (blue) so you can verify what is sent
            BLUE = "\x1b[34m"
            GREEN = "\x1b[32m"
            RESET = "\x1b[0m"
            import sys as _sys
            _sys.stderr.write(f"{BLUE}[UI free] Sending (repr): {repr(text)[:2000]}{RESET}\n")

            # Afficher la requête puis la réponse
            self.output.appendPlainText(f"Vous: {text}")
            self.free_input.clear()
            answer = llm_inference.ask_user(text)

            # log response (green)
            _sys.stderr.write(f"{GREEN}[UI free] Received (preview): {repr(answer)[:1000]}{RESET}\n")

            self.output.appendPlainText(f"Assistant: {answer or '[réponse vide]'}")
            self.status_label.setText("Réponse reçue")
        except Exception as e:
            self.output.appendPlainText(f"[Erreur libre] {str(e)}")
            self.status_label.setText("Erreur lors de l'appel libre")
        finally:
            # Busy OFF
            self.busy.setVisible(False)
            self.send_button.setDisabled(False)
            self.btn_open_pdf.setDisabled(False)
            self.free_send.setDisabled(False)
            self.url_input.setDisabled(False)
            self.free_input.setDisabled(False)

    def open_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choisir un PDF", "", "PDF (*.pdf)")
        if not path:
            return
        self.full_source = path
        self.source_label.setText(f"PDF sélectionné: {self._short(path)}")
        self.status_label.setText("<font color='green'>Prêt à envoyer</font>")

    def send_to_openai(self):
        source = self.full_source or self.url_input.text().strip()
        if not source:
            QMessageBox.warning(self, "Aucune source", "Colle une URL ou importe un PDF.")
            return
        # Clear previous output and show a short placeholder
        self.output.clear()
        self.output.appendPlainText("[envoi en cours…]")
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        self.source_label.setText(f"Source: {self._short(source)}")
        # Busy on
        self.busy.setVisible(True)
        self.send_button.setDisabled(True)
        self.btn_open_pdf.setDisabled(True)
        self.url_input.setDisabled(True)
        self.status_label.setText("Envoi…")
        try:
            answer = llm_inference.analyse_url(source)
            self.output.setPlainText(answer or "[réponse vide]")
            self.output.moveCursor(QTextCursor.MoveOperation.End)
            self.status_label.setText("Réponse reçue")
        except Exception as e:
            self.output.setPlainText(f"[Erreur] {str(e)}")
            self.output.moveCursor(QTextCursor.MoveOperation.End)
            self.status_label.setText("Erreur lors de l'appel à infer_gpt")
        finally:
            # Busy off
            self.busy.setVisible(False)
            self.send_button.setDisabled(False)
            self.btn_open_pdf.setDisabled(False)
            self.url_input.setDisabled(False)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ChatUI()
    w.show()
    sys.exit(app.exec())