import threading
import time
import tracemalloc

from conftest import make_game
from game_translator.adapters import scan
from game_translator.jobs import create_job, run_job
from game_translator.storage import Project
from test_jobs import SyntheticProvider


def test_ten_thousand_segments_pause_reopen_resume(tmp_path):
    game = make_game(tmp_path / "large-mz", count=2500)
    tracemalloc.start()
    started = time.perf_counter()
    report = scan(game)
    scan_seconds = time.perf_counter() - started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert len(report.segments) == 10013
    directory = tmp_path / "large-project"
    project = Project.create(directory, report)
    job_id = create_job(project)
    cancel = threading.Event()
    assert run_job(project, job_id, SyntheticProvider(cancel), cancel, batch_size=50)["completed"] == 50
    project.close()
    project = Project(directory)
    result = run_job(project, job_id, SyntheticProvider(), batch_size=50)
    assert result["completed"] == 10013 and result["state"] == "Completed"
    assert project.progress()["Pending"] == 0
    project.close()
    print(f"Synthetic benchmark: segments=10013 scan_s={scan_seconds:.3f} scan_peak_mib={peak_bytes / 1024 / 1024:.2f} total_s={time.perf_counter() - started:.3f}")
