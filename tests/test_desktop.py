import tkinter as tk

import pytest

from game_translator.adapters import scan
from game_translator.desktop import Desktop
from game_translator.storage import Project


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


def test_desktop_edit_filter_and_target_switch(game, tmp_path, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("A display server is required for desktop smoke")
    root.withdraw()
    app = Desktop(root)
    try:
        app.report = scan(game)
        app.project = Project.create(tmp_path / "desktop-project", app.report)
        app.show_report()
        segment = next(s for s in app.report.segments if s.text == "Potion")
        app.table.selection_set(segment.id)
        app.select_segment()
        app.translation_text.insert("1.0", "İksir")
        app.reviewed.set(True)
        app.save()
        assert app.project.translation(segment.id)["text"] == "İksir"
        app.translation_text.delete("1.0", "end")
        app.recall()
        assert app.translation_text.get("1.0", "end-1c") == "İksir"
        app.filter_text.set("Potion")
        assert len(app.table.get_children()) == 1
        app.target_language.set("DE")
        app.switch_target()
        assert app.project.translation(segment.id) is None
        assert app.translation_text.get("1.0", "end-1c") == ""
        root.update_idletasks()
        assert root.winfo_reqwidth() <= 1400
    finally:
        app.project.close()
        root.destroy()
