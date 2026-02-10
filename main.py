import logging
import os
import tkinter as tk

from config import CREDENTIALS_DIR, OUTPUT_DIR
from gui import GmailCleanupGUI


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    os.makedirs(CREDENTIALS_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    root = tk.Tk()
    GmailCleanupGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
