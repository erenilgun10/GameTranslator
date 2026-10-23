import json
from pathlib import Path

import pytest


def make_game(root: Path, engine="MZ", count=1):
    """All content is synthetic; these are not playable copyrighted games."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "js").mkdir()
    (root / "data").mkdir()
    marker = "rmmz_core.js" if engine == "MZ" else "rpg_core.js"
    (root / "js" / marker).write_text("// Synthetic engine marker, no runtime code\n", encoding="utf-8")
    commands = [
        {"code": 401, "indent": 0, "parameters": [r"Welcome, \N[2]! You have \V[1] coins."]},
        {"code": 102, "indent": 0, "parameters": [["Enter", "Leave"], 0, 0, 2, 0]},
        {"code": 405, "indent": 0, "parameters": ["A synthetic story."]},
        {"code": 355, "indent": 0, "parameters": ["$gameVariables.setValue(21, 'Press Start');"]},
        {"code": 655, "indent": 0, "parameters": ["console.log('Do not translate');"]},
        {"code": 357, "indent": 0, "parameters": ["TextPicture", "set", "Text", {"text": "Plugin text"}]},
    ]
    events = [None] + [{"id": i + 1, "name": "Internal event", "list": commands} for i in range(count)]
    files = {
        "CommonEvents.json": events,
        "Map001.json": {"displayName": "Moon Village", "note": "<Choice Width: 320>", "events": [None, {"id": 1, "name": "Internal", "pages": [{"list": commands}]}]},
        "Items.json": [None, {"id": 1, "name": "Potion", "description": "Restores health.", "iconIndex": 2, "note": "<code:21>", "damage": {"formula": "a.atk * 2"}}],
        "System.json": {"gameTitle": "Synthetic Adventure", "currencyUnit": "Coins", "terms": {"basic": ["Level", "HP"], "messages": {"victory": "%1 won!"}}, "elements": ["", "Fire"], "switches": ["", "Internal"], "variables": ["", "Internal"], "title1Name": "img/titles1/Example.png"},
        "Unknown.json": {"text": "Unsupported schema"},
    }
    for name, data in files.items():
        (root / "data" / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "js" / "plugins.js").write_text("// Synthetic plugin configuration; skip safely\n", encoding="utf-8")
    return root


@pytest.fixture
def game(tmp_path):
    return make_game(tmp_path / "synthetic-mz")
