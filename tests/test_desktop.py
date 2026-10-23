import tkinter as tk

import pytest

from game_translator.adapters import scan
from game_translator.desktop import Desktop


def test_desktop_renders_inventory(game):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("A display server is required for desktop smoke")
    root.withdraw()
    try:
        app = Desktop(root)
        app.report = scan(game)
        app.show_report()
        root.update()
        assert len(app.table.get_children()) == 17
    finally:
        root.destroy()
