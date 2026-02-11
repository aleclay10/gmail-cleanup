import json
import logging
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

from config import DEFAULT_QUERY, OLLAMA_URL, SETTINGS_FILE
from gmail_auth import get_gmail_service
from llm_classifier import check_ollama_available
from classifier_engine import ClassifierEngine

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

log = logging.getLogger(__name__)

DARK_COLORS = {
    "bg": "#2b2b2b",
    "fg": "#e0e0e0",
    "field_bg": "#3c3c3c",
    "field_fg": "#e0e0e0",
    "accent": "#4a9eff",
    "readonly_bg": "#353535",
    "log_bg": "#1e1e1e",
    "log_fg": "#d4d4d4",
}

LIGHT_COLORS = {
    "bg": "#f0f0f0",
    "fg": "#000000",
    "field_bg": "white",
    "field_fg": "#000000",
    "accent": "blue",
    "readonly_bg": "#f0f0f0",
    "log_bg": "white",
    "log_fg": "#000000",
}


class GmailCleanupGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Gmail Cleanup Tool")
        self.root.geometry("700x550")
        self.root.resizable(True, True)

        self.engine = None
        self.service = None
        self._tray_icon = None

        self.style = ttk.Style()
        self.style.theme_use("clam")

        self._build_ui()
        self._load_and_apply_settings()

        if HAS_TRAY:
            self._start_tray()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # --- Input row ---
        self.input_frame = ttk.LabelFrame(self.root, text="Settings", padding=8)
        self.input_frame.pack(fill="x", padx=10, pady=(10, 5))

        ttk.Label(self.input_frame, text="Query:").grid(row=0, column=0, sticky="w")
        self.query_var = tk.StringVar(value=DEFAULT_QUERY)
        ttk.Entry(self.input_frame, textvariable=self.query_var, width=30).grid(
            row=0, column=1, padx=(5, 20)
        )

        ttk.Label(self.input_frame, text="Ollama URL:").grid(row=0, column=2, sticky="w")
        self.ollama_var = tk.StringVar(value=OLLAMA_URL)
        ttk.Entry(self.input_frame, textvariable=self.ollama_var, width=25).grid(
            row=0, column=3, padx=5
        )

        # Connected email row
        ttk.Label(self.input_frame, text="Connected:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.email_var = tk.StringVar(value="Not connected")
        self.email_entry = ttk.Entry(
            self.input_frame, textvariable=self.email_var, state="readonly", width=60
        )
        self.email_entry.grid(row=1, column=1, columnspan=3, sticky="we", padx=5, pady=(5, 0))

        self.input_frame.columnconfigure(3, weight=1)

        # --- Button row ---
        self.btn_frame = ttk.Frame(self.root, padding=8)
        self.btn_frame.pack(fill="x", padx=10)

        self.start_btn = ttk.Button(self.btn_frame, text="Start", command=self._on_start)
        self.start_btn.pack(side="left", padx=5)

        self.stop_btn = ttk.Button(
            self.btn_frame, text="Stop", command=self._on_stop, state="disabled"
        )
        self.stop_btn.pack(side="left", padx=5)

        self.resume_btn = ttk.Button(
            self.btn_frame, text="Resume", command=self._on_resume
        )
        self.resume_btn.pack(side="left", padx=5)

        # Dark mode toggle
        self.dark_mode_var = tk.BooleanVar(value=False)
        self.dark_check = ttk.Checkbutton(
            self.btn_frame, text="Dark Mode",
            variable=self.dark_mode_var, command=self._on_dark_toggle
        )
        self.dark_check.pack(side="left", padx=15)

        self.status_var = tk.StringVar(value="Idle")
        self.status_label = ttk.Label(
            self.btn_frame, textvariable=self.status_var,
            foreground="blue", style="Status.TLabel"
        )
        self.status_label.pack(side="right", padx=10)

        # --- Progress ---
        self.prog_frame = ttk.LabelFrame(self.root, text="Progress", padding=8)
        self.prog_frame.pack(fill="x", padx=10, pady=5)

        self.progress_bar = ttk.Progressbar(self.prog_frame, mode="determinate")
        self.progress_bar.pack(fill="x", pady=(0, 5))

        self.stats_row = ttk.Frame(self.prog_frame)
        self.stats_row.pack(fill="x")

        self.progress_label = tk.StringVar(value="0/0")
        ttk.Label(self.stats_row, textvariable=self.progress_label).pack(side="left")

        self.important_var = tk.StringVar(value="Important: 0")
        ttk.Label(self.stats_row, textvariable=self.important_var, foreground="green").pack(
            side="left", padx=20
        )

        self.low_var = tk.StringVar(value="Low Priority: 0")
        ttk.Label(self.stats_row, textvariable=self.low_var, foreground="gray").pack(
            side="left"
        )

        self.current_var = tk.StringVar(value="")
        ttk.Label(self.prog_frame, textvariable=self.current_var, wraplength=650).pack(
            fill="x", pady=(5, 0)
        )

        # --- Log ---
        self.log_frame = ttk.LabelFrame(self.root, text="Log", padding=8)
        self.log_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.log_text = scrolledtext.ScrolledText(
            self.log_frame, height=10, state="disabled", wrap="word"
        )
        self.log_text.pack(fill="both", expand=True)

        # Counters
        self._important_count = 0
        self._low_count = 0

    # --- Settings Persistence ---

    def _load_settings(self):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_settings(self):
        settings = {
            "query": self.query_var.get(),
            "ollama_url": self.ollama_var.get(),
            "dark_mode": self.dark_mode_var.get(),
            "geometry": self.root.geometry(),
        }
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(settings, f, indent=2)
        except OSError:
            log.warning("Could not save settings")

    def _load_and_apply_settings(self):
        settings = self._load_settings()
        if not settings:
            self._apply_theme()
            return

        if "query" in settings:
            self.query_var.set(settings["query"])
        if "ollama_url" in settings:
            self.ollama_var.set(settings["ollama_url"])
        if "dark_mode" in settings:
            self.dark_mode_var.set(settings["dark_mode"])
        if "geometry" in settings:
            self.root.geometry(settings["geometry"])

        self._apply_theme()

    # --- Dark Mode ---

    def _on_dark_toggle(self):
        self._apply_theme()

    def _apply_theme(self):
        colors = DARK_COLORS if self.dark_mode_var.get() else LIGHT_COLORS

        self.style.configure("TFrame", background=colors["bg"])
        self.style.configure("TLabelframe", background=colors["bg"])
        self.style.configure("TLabelframe.Label", background=colors["bg"], foreground=colors["fg"])
        self.style.configure("TLabel", background=colors["bg"], foreground=colors["fg"])
        self.style.configure("TButton", background=colors["bg"], foreground=colors["fg"])
        self.style.configure("TCheckbutton", background=colors["bg"], foreground=colors["fg"])
        self.style.configure("TEntry", fieldbackground=colors["field_bg"], foreground=colors["field_fg"])
        self.style.configure("TProgressbar", background=colors["accent"])

        self.style.map("TEntry", fieldbackground=[("readonly", colors["readonly_bg"])])

        self.style.configure("Status.TLabel", background=colors["bg"], foreground=colors["accent"])

        self.root.configure(bg=colors["bg"])

        self.log_text.config(
            bg=colors["log_bg"],
            fg=colors["log_fg"],
            insertbackground=colors["fg"],
        )

    # --- System Tray ---

    def _create_tray_image(self):
        img = Image.new("RGBA", (64, 64), (66, 133, 244, 255))
        draw = ImageDraw.Draw(img)
        # White envelope outline
        draw.rectangle([12, 20, 52, 44], outline="white", width=2)
        draw.line([12, 20, 32, 35], fill="white", width=2)
        draw.line([52, 20, 32, 35], fill="white", width=2)
        return img

    def _start_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Show", self._tray_show, default=True),
            pystray.MenuItem("Exit", self._tray_exit),
        )
        self._tray_icon = pystray.Icon(
            "gmail-cleanup", self._create_tray_image(),
            "Gmail Cleanup Tool", menu
        )
        t = threading.Thread(target=self._tray_icon.run, daemon=True)
        t.start()

    def _tray_show(self, icon=None, item=None):
        self.root.after(0, self._show_window)

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _tray_exit(self, icon=None, item=None):
        self.root.after(0, self._quit)

    def _quit(self):
        self._save_settings()
        if self._tray_icon:
            self._tray_icon.stop()
        self.root.destroy()

    def _on_close(self):
        if HAS_TRAY and self._tray_icon:
            self.root.withdraw()
        else:
            self._save_settings()
            self.root.destroy()

    # --- Logging / Progress ---

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

        # Fetch connected email
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            self.email_var.set(profile["emailAddress"])
        except Exception:
            log.warning("Could not fetch email address")

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
