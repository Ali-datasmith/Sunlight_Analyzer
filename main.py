"""Entry point for Sunlight & Shadow Analyzer (SSA).

Run directly via:
    python main.py
Or in VS Code by clicking the Run button (F5 / Run Python File).
"""

import tkinter as tk
from ui import App


def main() -> None:
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
