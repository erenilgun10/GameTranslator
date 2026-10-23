# GameTranslator

RPG Maker MV/MZ file translation for Windows. Development is phased; see
[the roadmap](docs/development-roadmap.md) for verified capabilities and limits.
Only synthetic fixtures are included. No copyrighted games, assets or API keys.

Python 3.12+, SQLite and Tkinter. No GPU, model download or runtime pip dependency.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest -q
```

[Türkçe](README.tr.md) · [Safety](docs/patch-safety.md) · [Formats](docs/supported-formats.md)
