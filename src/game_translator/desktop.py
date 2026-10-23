import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .adapters import scan
from .models import ScanReport, SourceFile
from .providers import DeepLProvider
from .storage import Project
from .tokens import protect


class Desktop:
    def __init__(self, root):
        self.root = root
        root.title("GameTranslator")
        root.geometry("1100x720")
        root.minsize(820, 520)
        self.events = queue.Queue()
        self.report = None
        self.project = None
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
        editor = ttk.Frame(root, padding=12)
        editor.pack(fill="x")
        ttk.Label(editor, text="Çeviri / Translation").pack(anchor="w")
        self.translation_text = tk.Text(editor, height=4, wrap="word", undo=True)
        self.translation_text.pack(fill="x")
        actions = ttk.Frame(editor)
        actions.pack(fill="x", pady=5)
        self.reviewed = tk.BooleanVar(value=False)
        self.locked = tk.BooleanVar(value=True)
        ttk.Checkbutton(actions, text="İncelendi / Reviewed", variable=self.reviewed).pack(side="left")
        ttk.Checkbutton(actions, text="Otomatik çeviriye kilitli / Locked", variable=self.locked).pack(side="left")
        ttk.Button(actions, text="Kaydet / Save", command=self.save).pack(side="left", padx=8)
        ttk.Button(actions, text="DeepL ile çevir / Translate", command=self.translate_selected).pack(side="left")
        self.details = tk.StringVar(value="")
        ttk.Label(editor, textvariable=self.details, wraplength=1000).pack(fill="x")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self.poll)

    def close(self):
        if self.project:
            self.project.close()
        self.root.destroy()

    def new_project(self):
        if not self.report:
            messagebox.showinfo("GameTranslator", "Önce oyun tara / Scan a game first")
            return
        directory = filedialog.asksaveasfilename(title="Yeni proje klasörü / New project directory", defaultextension=".gtproj")
        if directory:
            try:
                project = Project.create(Path(directory), self.report, self.source_language.get(), self.target_language.get())
                if self.project:
                    self.project.close()
                self.project = project
                self.show_report()
            except (ValueError, OSError) as exc:
                messagebox.showerror("GameTranslator", str(exc))

    def open_project(self):
        directory = filedialog.askdirectory(title="Proje klasörü / Project directory")
        if directory:
            try:
                project = Project(Path(directory))
                if self.project:
                    self.project.close()
                self.project = project
                self.source_language.set(project.source)
                self.target_language.set(project.target)
                self.report = ScanReport(project.manifest["game"], project.manifest["engine"],
                                         [SourceFile(r[0], r[1]) for r in project.db.execute("SELECT * FROM sources")], project.segments())
                self.show_report()
            except Exception as exc:
                messagebox.showerror("GameTranslator", f"Proje açılamadı / Cannot open project: {type(exc).__name__}")

    def select_segment(self, _event=None):
        selected = self.table.selection()
        if not selected:
            return
        segment = next(s for s in self.report.segments if s.id == selected[0])
        entry = self.project.translation(segment.id) if self.project else None
        self.translation_text.delete("1.0", "end")
        if entry:
            self.translation_text.insert("1.0", entry["text"])
        self.reviewed.set(bool(entry and entry["status"] == "Reviewed"))
        self.locked.set(bool(entry["locked"]) if entry else True)
        self.details.set(segment.text + "\n" + segment.context)

    def save(self):
        selected = self.table.selection()
        if not self.project or not selected:
            messagebox.showinfo("GameTranslator", "Proje ve metin seç / Select a project and segment")
            return
        try:
            text = self.translation_text.get("1.0", "end-1c")
            self.project.save_translation(selected[0], text, reviewed=self.reviewed.get(), locked=self.locked.get())
            self.status.set(str(self.project.progress()))
            segment = next(s for s in self.report.segments if s.id == selected[0])
            self.details.set("Uzun metin: oyun içinde kontrol edin / Long text: check in game" if len(text) > max(80, len(segment.text) * 1.5) else "Kaydedildi / Saved")
        except (ValueError, OSError) as exc:
            messagebox.showerror("GameTranslator", str(exc))

    def translate_selected(self):
        selected = self.table.selection()
        if not self.project or not selected:
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
        self.status.set("DeepL…")
        def worker():
            try:
                masked = protect(segment.text)
                result = DeepLProvider().translate_batch([masked.text], source, target)
                self.events.put(("translation", (project_id, segment.id, masked.restore(result.texts[0]))))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def select_game(self):
        directory = filedialog.askdirectory()
        if directory:
            self.run_scan(Path(directory))

    def run_scan(self, path):
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
            self.table.insert("", "end", iid=segment.id, values=(segment.context, segment.text))
        counts = self.report.to_dict()["counts"]
        self.status.set(f"{self.report.engine} · {self.project.progress() if self.project else counts}")
        self.details.set("\n".join(f"{f.file}: {f.reason}" for f in self.report.findings[:5]))

    def poll(self):
        try:
            while True:
                event, result = self.events.get_nowait()
                self.scan_button.configure(state="normal")
                if event == "scan":
                    if self.project:
                        self.project.close()
                        self.project = None
                    self.report = result
                    self.show_report()
                elif event == "translation":
                    try:
                        if not self.project or self.project.manifest["id"] != result[0]:
                            self.status.set("Proje değişti; eski istek kaydedilmedi / Project changed; result discarded")
                            continue
                        self.project.save_translation(result[1], result[2], provider="DeepL", automatic=True)
                        self.select_segment()
                        self.status.set(str(self.project.progress()))
                    except (ValueError, OSError) as exc:
                        messagebox.showerror("GameTranslator", str(exc))
                else:
                    self.status.set("İşlem başarısız / Operation failed")
                    messagebox.showerror("GameTranslator", result)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)


def main():
    root = tk.Tk()
    Desktop(root)
    root.mainloop()
