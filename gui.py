import logging
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

from config import DEFAULT_QUERY, OLLAMA_URL
from gmail_auth import get_gmail_service
from llm_classifier import check_ollama_available
from classifier_engine import ClassifierEngine

log = logging.getLogger(__name__)


class GmailCleanupGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Gmail Cleanup Tool")
        self.root.geometry("700x520")
        self.root.resizable(True, True)

        self.engine = None
        self.service = None

        self._build_ui()

    def _build_ui(self):
        # --- Input row ---
        input_frame = ttk.LabelFrame(self.root, text="Settings", padding=8)
        input_frame.pack(fill="x", padx=10, pady=(10, 5))

        ttk.Label(input_frame, text="Query:").grid(row=0, column=0, sticky="w")
        self.query_var = tk.StringVar(value=DEFAULT_QUERY)
        ttk.Entry(input_frame, textvariable=self.query_var, width=30).grid(
            row=0, column=1, padx=(5, 20)
        )

        ttk.Label(input_frame, text="Ollama URL:").grid(row=0, column=2, sticky="w")
        self.ollama_var = tk.StringVar(value=OLLAMA_URL)
        ttk.Entry(input_frame, textvariable=self.ollama_var, width=25).grid(
            row=0, column=3, padx=5
        )

        # --- Button row ---
        btn_frame = ttk.Frame(self.root, padding=8)
        btn_frame.pack(fill="x", padx=10)

        self.start_btn = ttk.Button(btn_frame, text="Start", command=self._on_start)
        self.start_btn.pack(side="left", padx=5)

        self.stop_btn = ttk.Button(
            btn_frame, text="Stop", command=self._on_stop, state="disabled"
        )
        self.stop_btn.pack(side="left", padx=5)

        self.resume_btn = ttk.Button(
            btn_frame, text="Resume", command=self._on_resume
        )
        self.resume_btn.pack(side="left", padx=5)

        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(btn_frame, textvariable=self.status_var, foreground="blue").pack(
            side="right", padx=10
        )

        # --- Progress ---
        prog_frame = ttk.LabelFrame(self.root, text="Progress", padding=8)
        prog_frame.pack(fill="x", padx=10, pady=5)

        self.progress_bar = ttk.Progressbar(prog_frame, mode="determinate")
        self.progress_bar.pack(fill="x", pady=(0, 5))

        stats_row = ttk.Frame(prog_frame)
        stats_row.pack(fill="x")

        self.progress_label = tk.StringVar(value="0/0")
        ttk.Label(stats_row, textvariable=self.progress_label).pack(side="left")

        self.important_var = tk.StringVar(value="Important: 0")
        ttk.Label(stats_row, textvariable=self.important_var, foreground="green").pack(
            side="left", padx=20
        )

        self.low_var = tk.StringVar(value="Low Priority: 0")
        ttk.Label(stats_row, textvariable=self.low_var, foreground="gray").pack(
            side="left"
        )

        self.current_var = tk.StringVar(value="")
        ttk.Label(prog_frame, textvariable=self.current_var, wraplength=650).pack(
            fill="x", pady=(5, 0)
        )

        # --- Log ---
        log_frame = ttk.LabelFrame(self.root, text="Log", padding=8)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=10, state="disabled", wrap="word"
        )
        self.log_text.pack(fill="both", expand=True)

        # Counters
        self._important_count = 0
        self._low_count = 0

    def _log(self, msg):
        def _update():
            self.log_text.config(state="normal")
            self.log_text.insert("end", f"> {msg}\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")

        self.root.after(0, _update)

    def _progress(self, done, total, classification):
        def _update():
            if classification == "important":
                self._important_count += 1
            else:
                self._low_count += 1

            self.progress_bar["maximum"] = total
            self.progress_bar["value"] = done
            self.progress_label.set(f"{done}/{total}")
            self.important_var.set(f"Important: {self._important_count}")
            self.low_var.set(f"Low Priority: {self._low_count}")

        self.root.after(0, _update)

    def _set_running(self, running):
        self.start_btn.config(state="disabled" if running else "normal")
        self.resume_btn.config(state="disabled" if running else "normal")
        self.stop_btn.config(state="normal" if running else "disabled")
        self.status_var.set("Running..." if running else "Idle")

    def _launch_engine(self, resume=False):
        # Reset counters
        self._important_count = 0
        self._low_count = 0

        # Check Ollama
        self._log("Checking Ollama...")
        ok, msg = check_ollama_available()
        if not ok:
            messagebox.showerror("Ollama Error", msg)
            return

        # Auth Gmail
        self._log("Authenticating with Gmail...")
        try:
            self.service = get_gmail_service()
        except Exception as e:
            messagebox.showerror("Gmail Auth Error", str(e))
            return

        self._log("Starting classifier engine...")
        self._set_running(True)

        self.engine = ClassifierEngine(
            service=self.service,
            progress_cb=self._progress,
            log_cb=self._log,
            query=self.query_var.get(),
        )
        self.engine.start(resume=resume)

        self._poll_engine()

    def _poll_engine(self):
        if self.engine and self.engine.is_running():
            self.root.after(500, self._poll_engine)
        else:
            self._set_running(False)

    def _on_start(self):
        self._launch_engine(resume=False)

    def _on_stop(self):
        if self.engine:
            self.engine.stop()
            self._log("Stop requested...")

    def _on_resume(self):
        self._launch_engine(resume=True)
