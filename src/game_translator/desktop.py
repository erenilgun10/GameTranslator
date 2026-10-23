import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .adapters import scan


class Desktop:
    def __init__(self, root):
        self.root = root
        root.title("GameTranslator")
        root.geometry("1100x720")
        root.minsize(820, 520)
        self.events = queue.Queue()
        self.report = None
        bar = ttk.Frame(root, padding=12)
        bar.pack(fill="x")
        self.scan_button = ttk.Button(bar, text="Oyun seç ve tara / Scan game", command=self.select_game)
        self.scan_button.pack(side="left")
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
        self.root.after(100, self.poll)

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
        self.status.set(f"{self.report.engine} · {counts}")

    def poll(self):
        try:
            while True:
                event, result = self.events.get_nowait()
                self.scan_button.configure(state="normal")
                if event == "scan":
                    self.report = result
                    self.show_report()
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
