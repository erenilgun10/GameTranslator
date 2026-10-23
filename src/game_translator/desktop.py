import queue
import json
import sqlite3
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .adapters import read_json, safe_path, scan
from .models import Finding, ScanReport, SourceFile
from .providers import DeepLProvider
from .storage import Project
from .tokens import protect
from .jobs import create_job, run_job
from .patching import apply, load_manifest, restore, stage


class Desktop:
    def __init__(self, root):
        self.root = root
        root.title("GameTranslator")
        root.geometry("1100x720")
        root.minsize(820, 520)
        self.events = queue.Queue()
        self.report = None
        self.project = None
        self.busy = False
        self.closing = False
        self.editing_id = None
        self.saved_editor = ("", False, True)
        self.cancel_job = threading.Event()
        bar = ttk.Frame(root, padding=12)
        bar.pack(fill="x")
        self.scan_button = ttk.Button(bar, text="Oyun seç ve tara / Scan game", command=self.select_game)
        self.scan_button.pack(side="left")
        ttk.Button(bar, text="Yeni proje / New project", command=self.new_project).pack(side="left", padx=4)
        ttk.Button(bar, text="Proje aç / Open project", command=self.open_project).pack(side="left")
        self.source_language = tk.StringVar(value="EN")
        self.target_language = tk.StringVar(value="TR")
        ttk.Label(bar, text="Kaynak → Hedef / Source → Target").pack(side="left", padx=8)
        ttk.Entry(bar, textvariable=self.source_language, width=6).pack(side="left")
        ttk.Entry(bar, textvariable=self.target_language, width=6).pack(side="left", padx=4)
        ttk.Button(bar, text="Dili seç / Use target", command=self.switch_target).pack(side="left")
        self.status = tk.StringVar(value="API anahtarı gerekmez / No API key required")
        ttk.Label(root, textvariable=self.status, padding=8).pack(fill="x")
        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)
        self.table = ttk.Treeview(frame, columns=("file", "source"), show="headings", selectmode="browse")
        self.table.heading("file", text="Konum / Location")
        self.table.heading("source", text="Kaynak / Source")
        self.table.column("file", width=300)
        self.table.column("source", width=650)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.table.pack(fill="both", expand=True)
        self.table.bind("<<TreeviewSelect>>", self.select_segment)
        filters = ttk.Frame(root, padding=(12, 0))
        filters.pack(fill="x")
        ttk.Label(filters, text="Filtre / Filter").pack(side="left")
        self.filter_text = tk.StringVar()
        self.filter_text.trace_add("write", lambda *_: self.show_report() if self.report else None)
        ttk.Entry(filters, textvariable=self.filter_text).pack(side="left", fill="x", expand=True, padx=6)
        self.filter_status = tk.StringVar(value="All")
        options = ttk.Combobox(filters, textvariable=self.filter_status, values=("All", "Pending", "Translated", "Reviewed", "Locked"), state="readonly", width=14)
        options.pack(side="left")
        options.bind("<<ComboboxSelected>>", lambda _: self.show_report() if self.report else None)
        ttk.Button(filters, text="Glossary", command=self.edit_glossary).pack(side="left", padx=4)
        ttk.Button(filters, text="Geçmiş / History", command=self.show_history).pack(side="left")
        editor = ttk.Frame(root, padding=12)
        editor.pack(fill="x")
        ttk.Label(editor, text="Çeviri / Translation").pack(anchor="w")
        self.translation_text = tk.Text(editor, height=4, wrap="word", undo=True)
        self.translation_text.pack(fill="x")
        actions = ttk.Frame(editor)
        actions.pack(fill="x", pady=5)
        self.reviewed = tk.BooleanVar(value=False)
        self.locked = tk.BooleanVar(value=True)
        self.review_button = ttk.Checkbutton(actions, text="İncelendi / Reviewed", variable=self.reviewed)
        self.review_button.pack(side="left")
        self.lock_button = ttk.Checkbutton(actions, text="Otomatik çeviriye kilitli / Locked", variable=self.locked)
        self.lock_button.pack(side="left")
        ttk.Button(actions, text="Kaydet / Save", command=self.save).pack(side="left", padx=8)
        ttk.Button(actions, text="Bellekten getir / Recall", command=self.recall).pack(side="left", padx=4)
        ttk.Button(actions, text="DeepL ile çevir / Translate", command=self.translate_selected).pack(side="left")
        patch_bar = ttk.Frame(editor)
        patch_bar.pack(fill="x", pady=4)
        ttk.Button(patch_bar, text="Toplu başlat/devam / Batch", command=self.start_job).pack(side="left")
        ttk.Button(patch_bar, text="Duraklat / Pause", command=self.cancel_job.set).pack(side="left", padx=4)
        ttk.Button(patch_bar, text="Patch hazırla / Stage", command=self.stage_patch).pack(side="left")
        ttk.Button(patch_bar, text="Patch uygula / Apply", command=self.apply_patch).pack(side="left", padx=4)
        ttk.Button(patch_bar, text="Geri al / Restore", command=self.restore_patch).pack(side="left")
        self.details = tk.StringVar(value="")
        ttk.Label(editor, textvariable=self.details, wraplength=1000).pack(fill="x")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self.poll)

    def close(self):
        if self.busy:
            self.closing = True
            self.cancel_job.set()
            self.status.set("İşlemin güvenle bitmesi bekleniyor / Waiting for operation to finish safely")
            return False
        if not self.confirm_unsaved():
            self.closing = False
            return False
        self.cancel_job.set()
        if self.project:
            self.project.close()
            self.project = None
        self.root.destroy()
        return True

    def editor_state(self):
        return (self.translation_text.get("1.0", "end-1c"), self.reviewed.get(), self.locked.get())

    def has_unsaved(self):
        return bool(self.project and self.editing_id and self.editor_state() != self.saved_editor)

    def confirm_unsaved(self):
        if not self.has_unsaved():
            return True
        answer = messagebox.askyesnocancel("GameTranslator", "Değişiklikler kaydedilsin mi? Hayır: taslağı bırak. İptal: düzenlemeye dön.\nSave changes? No: discard draft. Cancel: keep editing.")
        if answer is None:
            return False
        return self.save() if answer else True

    def load_editor(self, segment_id=None):
        self.editing_id = segment_id
        entry = self.project.translation(segment_id) if self.project and segment_id else None
        self.translation_text.delete("1.0", "end")
        if entry:
            self.translation_text.insert("1.0", entry["text"])
        self.translation_text.edit_reset()
        self.reviewed.set(bool(entry and entry["status"] == "Reviewed"))
        self.locked.set(bool(entry["locked"]) if entry else True)
        self.saved_editor = self.editor_state()
        if segment_id:
            segment = next(s for s in self.report.segments if s.id == segment_id)
            self.details.set(segment.text + "\n" + segment.context)
        else:
            self.details.set("")

    def new_project(self):
        if self.busy:
            return
        if not self.report:
            messagebox.showinfo("GameTranslator", "Önce oyun tara / Scan a game first")
            return
        directory = filedialog.asksaveasfilename(title="Yeni proje klasörü / New project directory", defaultextension=".gtproj")
        if directory and self.confirm_unsaved():
            try:
                project = Project.create(Path(directory), self.report, self.source_language.get(), self.target_language.get())
                if self.project:
                    self.project.close()
                self.project = project
                self.load_editor()
                self.show_report()
            except (ValueError, OSError, sqlite3.Error) as exc:
                messagebox.showerror("GameTranslator", str(exc))

    def open_project(self):
        if self.busy:
            return
        directory = filedialog.askdirectory(title="Proje klasörü / Project directory")
        if directory and self.confirm_unsaved():
            project = None
            try:
                project = Project(Path(directory))
                report = ScanReport(project.manifest["game"], project.manifest["engine"],
                                         [SourceFile(r[0], r[1]) for r in project.db.execute("SELECT * FROM sources")], project.segments())
                report_path = safe_path(project.directory, "scan-report.json")
                if report_path.is_file():
                    saved_report = read_json(report_path)
                    report.findings = [Finding(**f) for f in saved_report.get("findings", [])]
                    report.skipped = saved_report.get("skipped", 0)
                if self.project:
                    self.project.close()
                self.project = project
                self.report = report
                self.source_language.set(project.source)
                self.target_language.set(project.target)
                self.load_editor()
                self.show_report()
            except Exception as exc:
                if project and project is not self.project:
                    project.close()
                messagebox.showerror("GameTranslator", f"Proje açılamadı / Cannot open project: {type(exc).__name__}")

    def select_segment(self, _event=None):
        selected = self.table.selection()
        if not selected or selected[0] == self.editing_id or self.translation_text.cget("state") == "disabled":
            return
        if not self.confirm_unsaved():
            if self.editing_id and self.table.exists(self.editing_id):
                self.table.selection_set(self.editing_id)
            else:
                self.table.selection_remove(*selected)
            return
        self.load_editor(selected[0])

    def save(self):
        if not self.project or not self.editing_id:
            messagebox.showinfo("GameTranslator", "Proje ve metin seç / Select a project and segment")
            return False
        try:
            text = self.translation_text.get("1.0", "end-1c")
            self.project.save_translation(self.editing_id, text, reviewed=self.reviewed.get(), locked=self.locked.get())
            self.saved_editor = self.editor_state()
            self.status.set(str(self.project.progress()))
            segment = next(s for s in self.report.segments if s.id == self.editing_id)
            self.details.set("Uzun metin: oyun içinde kontrol edin / Long text: check in game" if len(text) > max(80, len(segment.text) * 1.5) else "Kaydedildi / Saved")
            return True
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror("GameTranslator", str(exc))
            return False

    def recall(self):
        if not self.project or not self.editing_id or self.translation_text.cget("state") == "disabled":
            return
        segment = next(s for s in self.report.segments if s.id == self.editing_id)
        text = self.project.recalled(segment)
        if text:
            self.translation_text.delete("1.0", "end")
            self.translation_text.insert("1.0", text)
            self.details.set("Onaylı bellek kaydı getirildi; kaydetmeden önce incele / Approved memory recalled; review before saving")
        else:
            self.details.set("Bu bağlam/dil/glossary için bellek kaydı yok / No memory for this context/language/glossary")

    def translate_selected(self):
        if self.busy:
            return
        selected = self.table.selection()
        if not self.project or not selected:
            return
        if not self.confirm_unsaved():
            return
        segment = next(s for s in self.report.segments if s.id == selected[0])
        entry = self.project.translation(segment.id)
        if entry and entry["locked"]:
            messagebox.showinfo("GameTranslator", "Çeviri kilitli / Translation is locked")
            return
        if not messagebox.askyesno("DeepL", "Seçili metin DeepL'e gönderilecek, ücret doğabilir. Devam?\nSelected text will be sent to DeepL; charges may apply. Continue?"):
            return
        source, target = self.project.source, self.project.target
        project_id = self.project.manifest["id"]
        self.busy = True
        self.cancel_job.clear()
        self.status.set("DeepL…")
        def worker():
            try:
                masked = protect(segment.text)
                result = DeepLProvider().translate_batch([masked.text], source, target)
                self.events.put(("translation", (project_id, segment.id, masked.restore(result.texts[0]))))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def edit_glossary(self):
        if not self.project or self.busy:
            return
        source = simpledialog.askstring("Glossary", "Kaynak terim / Source term")
        if source:
            target = simpledialog.askstring("Glossary", "Hedef terim / Target term")
            if target:
                try:
                    self.project.set_glossary(source, target)
                    self.details.set(str(self.project.glossary()))
                except ValueError as exc:
                    messagebox.showerror("Glossary", str(exc))

    def switch_target(self):
        if self.project and not self.busy:
            if not self.confirm_unsaved():
                self.target_language.set(self.project.target)
                return
            try:
                self.project.set_target(self.target_language.get())
                self.load_editor()
                self.show_report()
            except ValueError as exc:
                self.target_language.set(self.project.target)
                messagebox.showerror("Language", str(exc))

    def stage_patch(self):
        if not self.project or self.busy:
            return
        directory = filedialog.asksaveasfilename(title="Yeni patch klasörü / New patch folder", defaultextension=".patch")
        if directory and self.confirm_unsaved():
            try:
                manifest = stage(self.project, Path(directory))
                preview = tk.Toplevel(self.root)
                preview.title("Patch: semantic diff")
                preview.geometry("900x600")
                text = tk.Text(preview, wrap="word")
                scroll = ttk.Scrollbar(preview, command=text.yview)
                text.configure(yscrollcommand=scroll.set)
                scroll.pack(side="right", fill="y")
                text.pack(fill="both", expand=True)
                text.insert("1.0", json.dumps(manifest, ensure_ascii=False, indent=2))
                text.configure(state="disabled")
                self.details.set(directory)
            except Exception as exc:
                messagebox.showerror("Patch", str(exc))

    def apply_patch(self):
        if not self.project or self.busy:
            return
        directory = filedialog.askdirectory(title="Patch klasörü / Patch folder")
        if not directory:
            return
        try:
            manifest = load_manifest(Path(directory))
            listing = "\n".join(f["path"] for f in manifest["files"][:20])
            game_path = self.project.manifest["game"]
            if not messagebox.askyesno("Patch", f"Oyun / Game: {game_path}\nHedef / Target: {manifest.get('target_language', '?')}\n\nDeğişecek dosyalar / Files to change:\n{listing}\n\nOnaylıyor musun / Approve?"):
                return
            backup = filedialog.asksaveasfilename(title="Yeni yedek klasörü / New backup folder", defaultextension=".backup")
            if backup:
                result = apply(Path(self.project.manifest["game"]), Path(directory), Path(backup), approved=True)
                self.details.set(str(result))
        except Exception as exc:
            messagebox.showerror("Patch", str(exc))

    def restore_patch(self):
        if not self.project or self.busy:
            return
        directory = filedialog.askdirectory(title="Yedek klasörü / Backup folder")
        if directory and messagebox.askyesno("Restore", "Yedekteki özgün dosyalar geri yüklenecek. Onay?\nRestore original files from this backup?"):
            try:
                self.details.set(str(restore(Path(self.project.manifest["game"]), Path(directory), approved=True)))
            except Exception as exc:
                messagebox.showerror("Restore", str(exc))

    def show_history(self):
        if self.project and self.table.selection():
            rows = self.project.db.execute("SELECT updated,text FROM history WHERE segment_id=? AND target=? ORDER BY id DESC LIMIT 10", (self.table.selection()[0], self.project.target)).fetchall()
            messagebox.showinfo("History", "\n".join(f"{r[0]}: {r[1]}" for r in rows) or "Kayıt yok / No history")

    def start_job(self):
        if not self.project or self.busy:
            return
        if not self.confirm_unsaved():
            return
        if not messagebox.askyesno("DeepL", "Bekleyen metinler DeepL'e gönderilir, ücret doğabilir.\nPending texts are sent to DeepL and may incur charges. Continue?"):
            return
        try:
            DeepLProvider().validate_configuration()
            row = self.project.db.execute("SELECT id FROM jobs WHERE target=? AND state!='Completed' ORDER BY created DESC LIMIT 1", (self.project.target,)).fetchone()
            job_id = row[0] if row else create_job(self.project)
        except Exception as exc:
            messagebox.showerror("DeepL", str(exc))
            return
        directory, project_id, target = self.project.directory, self.project.manifest["id"], self.project.target
        self.busy = True
        self.cancel_job.clear()
        def worker():
            project = None
            try:
                project = Project(directory)
                project.target = target
                result = run_job(project, job_id, DeepLProvider(), self.cancel_job,
                                 progress=lambda r: self.events.put(("job_progress", (project_id, r))))
                self.events.put(("job_done", (project_id, result)))
            except Exception as exc:
                self.events.put(("error", str(exc)))
            finally:
                if project:
                    project.close()
        threading.Thread(target=worker, daemon=True).start()

    def select_game(self):
        if self.busy:
            return
        directory = filedialog.askdirectory()
        if directory:
            self.run_scan(Path(directory))

    def run_scan(self, path):
        if self.busy or not self.confirm_unsaved():
            return
        self.busy = True
        self.translation_text.configure(state="disabled")
        self.review_button.configure(state="disabled")
        self.lock_button.configure(state="disabled")
        self.scan_button.configure(state="disabled")
        self.status.set("Taranıyor… / Scanning…")
        def worker():
            try:
                self.events.put(("scan", scan(path)))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def show_report(self):
        self.table.delete(*self.table.get_children())
        for segment in self.report.segments:
            entry = self.project.translation(segment.id) if self.project else None
            query = self.filter_text.get().casefold()
            status = self.filter_status.get()
            if query and query not in (segment.text + segment.context + (entry["text"] if entry else "")).casefold():
                continue
            if status == "Pending" and entry or status in ("Translated", "Reviewed") and (not entry or entry["status"] != status) or status == "Locked" and (not entry or not entry["locked"]):
                continue
            self.table.insert("", "end", iid=segment.id, values=(segment.context, segment.text))
        if self.editing_id and self.table.exists(self.editing_id):
            self.table.selection_set(self.editing_id)
        counts = self.report.to_dict()["counts"]
        self.status.set(f"{self.report.engine} · {counts | self.project.progress() if self.project else counts}")
        if not self.editing_id:
            self.details.set("\n".join(f"{f.file}: {f.reason}" for f in self.report.findings[:5]))

    def poll(self):
        try:
            while True:
                event, result = self.events.get_nowait()
                if event != "job_progress":
                    self.busy = False
                    self.scan_button.configure(state="normal")
                    self.translation_text.configure(state="normal")
                    self.review_button.configure(state="normal")
                    self.lock_button.configure(state="normal")
                if event == "scan":
                    if self.project:
                        self.project.close()
                        self.project = None
                    self.report = result
                    self.load_editor()
                    self.show_report()
                elif event == "translation":
                    self.busy = False
                    try:
                        if not self.project or self.project.manifest["id"] != result[0]:
                            self.status.set("Proje değişti; eski istek kaydedilmedi / Project changed; result discarded")
                            continue
                        self.project.save_translation(result[1], result[2], provider="DeepL", automatic=True)
                        if self.editing_id == result[1] and not self.has_unsaved():
                            self.load_editor(result[1])
                        self.status.set(str(self.project.progress()))
                    except (ValueError, OSError, sqlite3.Error) as exc:
                        messagebox.showerror("GameTranslator", str(exc))
                elif event in ("job_progress", "job_done"):
                    if event == "job_done":
                        self.busy = False
                    if self.project and self.project.manifest["id"] == result[0]:
                        report = result[1]
                        billed = report["billed"] if report["billed"] is not None else "unknown / bilinmiyor"
                        if event == "job_done":
                            self.show_report()
                            self.details.set(str({k: v for k, v in report.items() if k != "items"}))
                        self.status.set(f"{report['state']} · {report['completed']}/{report['total']} · Failed {report['failed']} · Billed chars {billed}")
                else:
                    self.busy = False
                    self.status.set("İşlem başarısız / Operation failed")
                    messagebox.showerror("GameTranslator", result)
        except queue.Empty:
            pass
        if self.closing and not self.busy and self.close():
            return
        self.root.after(100, self.poll)


def main():
    root = tk.Tk()
    smoke_test = "--smoke-test" in sys.argv
    if smoke_test:
        root.withdraw()
    Desktop(root)
    if smoke_test:
        root.update()
        root.destroy()
        return
    root.mainloop()
