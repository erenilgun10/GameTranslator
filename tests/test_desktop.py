import tkinter as tk

import pytest

from game_translator.adapters import scan
from game_translator.desktop import Desktop
from game_translator.storage import Project
from game_translator.jobs import create_job, job_report


@pytest.fixture
def editor(game, tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("A display server is required for desktop smoke")
    root.withdraw()
    app = Desktop(root)
    app.report = scan(game)
    app.project = Project.create(tmp_path / "editor-project", app.report)
    app.show_report()
    segment = next(s for s in app.report.segments if s.text == "Potion")
    app.table.selection_set(segment.id)
    app.select_segment()
    yield app, segment
    if app.project:
        app.project.close()
    try:
        root.destroy()
    except tk.TclError:
        pass


def test_cancel_segment_change_keeps_draft(editor, monkeypatch):
    app, segment = editor
    monkeypatch.setattr("game_translator.desktop.messagebox.askyesnocancel", lambda *a, **k: None)
    app.translation_text.insert("1.0", "İksir taslağı")
    other = next(s for s in app.report.segments if s.text == "Enter")
    app.table.selection_set(other.id)
    app.select_segment()
    assert app.table.selection() == (segment.id,)
    assert app.translation_text.get("1.0", "end-1c") == "İksir taslağı"


def test_undo_does_not_cross_segments(editor):
    app, _ = editor
    app.translation_text.insert("1.0", "İksir")
    app.save()
    other = next(s for s in app.report.segments if s.text == "Enter")
    app.table.selection_set(other.id)
    app.select_segment()
    try:
        app.translation_text.edit_undo()
    except tk.TclError:
        pass
    assert app.translation_text.get("1.0", "end-1c") == ""


def test_filter_does_not_change_draft_save_target(editor, monkeypatch):
    app, segment = editor
    monkeypatch.setattr("game_translator.desktop.messagebox.showinfo", lambda *a, **k: None)
    app.translation_text.insert("1.0", "İksir")
    app.filter_text.set("Enter")
    app.save()
    assert app.project.translation(segment.id)["text"] == "İksir"


def test_cancel_target_change_keeps_language_and_draft(editor, monkeypatch):
    app, _ = editor
    monkeypatch.setattr("game_translator.desktop.messagebox.askyesnocancel", lambda *a, **k: None)
    app.translation_text.insert("1.0", "İksir")
    app.target_language.set("DE")
    app.switch_target()
    assert app.project.target == "TR"
    assert app.target_language.get() == "TR"
    assert app.translation_text.get("1.0", "end-1c") == "İksir"


def test_bad_project_report_keeps_current_project(editor, tmp_path, monkeypatch):
    app, segment = editor
    original = app.project
    candidate = Project.create(tmp_path / "broken-report", app.report)
    candidate.close()
    (candidate.directory / "scan-report.json").write_text("broken", encoding="utf-8")
    monkeypatch.setattr("game_translator.desktop.filedialog.askdirectory", lambda **k: str(candidate.directory))
    monkeypatch.setattr("game_translator.desktop.messagebox.showerror", lambda *a, **k: None)
    app.open_project()
    assert app.project is original
    assert app.project.translation(segment.id) is None


def test_scan_blocks_project_changes(editor, monkeypatch):
    app, _ = editor
    class PendingThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr("game_translator.desktop.threading.Thread", PendingThread)
    app.run_scan(app.project.directory)
    assert app.busy


def test_close_waits_for_worker_checkpoint(editor):
    app, _ = editor
    app.busy = True
    app.close()
    assert app.cancel_job.is_set()
    assert app.root.winfo_exists()
    app.events.put(("job_done", (app.project.manifest["id"], {
        "state": "Paused", "completed": 0, "total": 0, "failed": 0, "billed": 0})))
    app.poll()
    with pytest.raises(tk.TclError):
        app.root.winfo_exists()


def test_background_translation_preserves_other_draft(editor):
    app, segment = editor
    other = next(s for s in app.report.segments if s.text == "Enter")
    app.translation_text.insert("1.0", "İksir taslağı")
    app.events.put(("translation", (app.project.manifest["id"], other.id, "Gir")))
    app.poll()
    assert app.project.translation(other.id)["text"] == "Gir"
    assert app.project.translation(segment.id) is None
    assert app.translation_text.get("1.0", "end-1c") == "İksir taslağı"


@pytest.mark.parametrize("save_changes", [True, False])
def test_segment_change_saves_or_discards_as_requested(editor, monkeypatch, save_changes):
    app, segment = editor
    monkeypatch.setattr("game_translator.desktop.messagebox.askyesnocancel", lambda *a, **k: save_changes)
    app.translation_text.insert("1.0", "İksir")
    other = next(s for s in app.report.segments if s.text == "Enter")
    app.table.selection_set(other.id)
    app.select_segment()
    entry = app.project.translation(segment.id)
    assert (entry["text"] if entry else None) == ("İksir" if save_changes else None)
    assert app.translation_text.get("1.0", "end-1c") == ""


def test_failed_save_keeps_draft_and_target(editor, monkeypatch):
    app, _ = editor
    monkeypatch.setattr("game_translator.desktop.messagebox.askyesnocancel", lambda *a, **k: True)
    monkeypatch.setattr("game_translator.desktop.messagebox.showerror", lambda *a, **k: None)
    # A new RPG control token is invalid for this source.
    app.translation_text.insert("1.0", r"İksir \V[99]")
    app.target_language.set("DE")
    app.switch_target()
    assert app.project.target == "TR"
    assert app.translation_text.get("1.0", "end-1c") == r"İksir \V[99]"


def test_review_flag_change_is_unsaved(editor, monkeypatch):
    app, segment = editor
    app.translation_text.insert("1.0", "İksir")
    app.save()
    app.reviewed.set(True)
    monkeypatch.setattr("game_translator.desktop.messagebox.askyesnocancel", lambda *a, **k: None)
    assert app.close() is False
    assert app.root.winfo_exists()
    assert app.project.translation(segment.id)["status"] == "Translated"


def test_scan_failure_keeps_draft_and_project(editor, monkeypatch):
    app, segment = editor
    original = app.project
    monkeypatch.setattr("game_translator.desktop.messagebox.showerror", lambda *a, **k: None)
    app.translation_text.insert("1.0", "İksir")
    app.translation_text.configure(state="disabled")
    app.busy = True
    app.events.put(("error", "Unsupported game"))
    app.poll()
    assert not app.busy
    assert app.project is original
    assert app.translation_text.cget("state") == "normal"
    app.save()
    assert app.project.translation(segment.id)["text"] == "İksir"


def test_batch_completion_preserves_draft(editor):
    app, segment = editor
    app.translation_text.insert("1.0", "İksir taslağı")
    job_id = create_job(app.project)
    app.events.put(("job_done", (app.project.manifest["id"], job_report(app.project, job_id))))
    app.poll()
    assert app.translation_text.get("1.0", "end-1c") == "İksir taslağı"
    app.save()
    assert app.project.translation(segment.id)["text"] == "İksir taslağı"


def test_closing_waits_until_translation_is_persisted(editor):
    app, segment = editor
    directory = app.project.directory
    app.busy = True
    app.close()
    app.events.put(("translation", (app.project.manifest["id"], segment.id, "İksir")))
    app.poll()
    reopened = Project(directory)
    try:
        assert reopened.translation(segment.id)["text"] == "İksir"
    finally:
        reopened.close()


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
        job_id = create_job(app.project)
        with app.project.db:
            app.project.db.execute("UPDATE jobs SET billing_complete=0 WHERE id=?", (job_id,))
        app.events.put(("job_done", (app.project.manifest["id"], job_report(app.project, job_id))))
        app.poll()
        assert "unknown / bilinmiyor" in app.status.get()
    finally:
        app.project.close()
        root.destroy()
