import threading

from game_translator.adapters import scan
from game_translator.jobs import create_job, run_job
from game_translator.providers import BatchResult, ProviderCapabilities, ProviderError
from game_translator.storage import Project
from game_translator.tokens import protect


class SyntheticProvider:
    capabilities = ProviderCapabilities("synthetic-test-only")

    def __init__(self, cancel=None):
        self.calls = 0
        self.cancel = cancel

    def translate_batch(self, texts, source, target, cancel):
        self.calls += 1
        if self.cancel:
            self.cancel.set()
        return BatchResult(["[SYNTHETIC] " + t for t in texts], sum(map(len, texts)))


def test_pause_close_resume_no_loss(game, tmp_path):
    directory = tmp_path / "project"
    project = Project.create(directory, scan(game))
    job_id = create_job(project)
    cancel = threading.Event()
    partial = run_job(project, job_id, SyntheticProvider(cancel), cancel, batch_size=3)
    assert partial["state"] == "Paused" and partial["completed"] == 3
    project.close()
    project = Project(directory)
    provider = SyntheticProvider()
    final = run_job(project, job_id, provider, batch_size=3)
    assert final["state"] == "Completed" and final["completed"] == 17
    assert provider.calls == 5
    assert project.progress()["Translated"] == 17
    project.close()


def test_glossary_and_memory_scopes(game, tmp_path):
    project = Project.create(tmp_path / "project", scan(game))
    project.set_glossary("Potion", "İksir")
    segment = next(s for s in project.segments() if s.text == "Potion")
    masked = protect(segment.text, project.glossary())
    assert masked.restore(masked.text) == "İksir"
    project.save_translation(segment.id, "İksir", reviewed=True)
    assert project.recalled(segment) == "İksir"
    project.target = "DE"
    assert project.recalled(segment) is None
    project.target = "TR"
    project.set_glossary("Potion", "Şifa")
    assert project.recalled(segment) is None
    project.close()


def test_provider_failure_and_retry_preserve_source(game, tmp_path):
    class Failing(SyntheticProvider):
        def translate_batch(self, *args):
            raise ProviderError("Synthetic failure")
    project = Project.create(tmp_path / "project", scan(game))
    job_id = create_job(project)
    failed = run_job(project, job_id, Failing())
    assert failed["failed"] == 17 and project.progress()["Translated"] == 0
    assert run_job(project, job_id, SyntheticProvider())["completed"] == 17
    project.close()
