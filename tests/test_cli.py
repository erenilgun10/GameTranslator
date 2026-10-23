import json

from game_translator.cli import main


def test_scan_cli(game, capsys):
    main(["scan", str(game)])
    report = json.loads(capsys.readouterr().out)
    assert report["engine"] == "MZ"
    assert report["counts"]["Extracted"] == 17
