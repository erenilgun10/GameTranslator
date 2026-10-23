# GameTranslator

RPG Maker MV/MZ file translation for Windows. **1.0 release candidate**: synthetic
tests pass; clean-machine and real-game human acceptance are still pending.
Only synthetic fixtures are included. No copyrighted games, assets or API keys.

Python 3.12+, SQLite and Tkinter. No GPU, model download or runtime pip dependency.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m game_translator gui
```

[Türkçe](README.tr.md) · [Safety](docs/patch-safety.md) · [Formats](docs/supported-formats.md)

Scan without changing source files, save projects in SQLite, edit/review/lock
translations, optionally translate with DeepL, reuse scoped memory and glossary,
pause/resume jobs, stage an auditable patch, and restore exact-byte backups.
Multiple target languages stay isolated. No OCR, overlay or mandatory local AI.

[Windows downloads](https://github.com/erenilgun10/GameTranslator/releases) ·
[User guide and CLI](docs/user-guide.md) · [Verified phases](docs/development-roadmap.md)

Windows portable package: extract ZIP, verify its `.sha256`, launch
`GameTranslator.exe`. Optional folder installer: run the bundled
`Install-GameTranslator.ps1`; it refuses to overwrite an existing installation.
Unsigned executables may trigger Windows SmartScreen. No administrator is required.

For a pinned development toolchain, install `requirements-dev.txt` then run
`python -m pip install --no-build-isolation -e .`. Build on Windows with
`powershell -File scripts/build_windows.ps1`. Build tools are pinned, but binaries
are not promised bit-for-bit identical across Windows/Python versions.
