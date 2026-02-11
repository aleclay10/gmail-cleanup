import logging
import os
import tkinter as tk
from logging.handlers import RotatingFileHandler

from config import CREDENTIALS_DIR, LOG_FILE, OUTPUT_DIR
from gui import GmailCleanupGUI


def main():
    os.makedirs(CREDENTIALS_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    log_format = "%(asctime)s %(levelname)s %(name)s: %(message)s"

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
    )

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger().addHandler(file_handler)

    root = tk.Tk()
    GmailCleanupGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
