import threading
import uuid

from .providers import ProviderError
from .storage import now
from .tokens import protect, validate_translation


def create_job(project):
    job_id, timestamp = str(uuid.uuid4()), now()
    pending = [s.id for s in project.segments() if project.translation(s.id) is None]
    with project.db:
        project.db.execute("INSERT INTO jobs(id,target,state,created,updated) VALUES (?,?,?,?,?)",
                           (job_id, project.target, "Paused", timestamp, timestamp))
        project.db.executemany("INSERT INTO job_items(job_id,segment_id,state) VALUES (?,?,?)",
                               [(job_id, segment_id, "Pending") for segment_id in pending])
    return job_id


def job_report(project, job_id):
    row = project.db.execute("SELECT * FROM jobs WHERE id=? AND target=?", (job_id, project.target)).fetchone()
    if row is None:
        raise ValueError("Unknown job for current target language")
    result = dict(row)
    result["items"] = [dict(r) for r in project.db.execute("SELECT segment_id,state,error,attempts FROM job_items WHERE job_id=?", (job_id,))]
    result["total"] = len(result["items"])
    result["currency_cost"] = None
    return result


def run_job(project, job_id, provider, cancel=None, batch_size=20, progress=None):
    job_report(project, job_id)
    if not 1 <= batch_size <= provider.capabilities.max_batch:
        raise ValueError("Invalid batch size")
    cancel = cancel or threading.Event()
    segments = {s.id: s for s in project.segments()}
    rows = project.db.execute("SELECT segment_id FROM job_items WHERE job_id=? AND state!='Done' ORDER BY rowid", (job_id,)).fetchall()
    with project.db:
        project.db.execute("UPDATE jobs SET state='Running',updated=? WHERE id=?", (now(), job_id))
    queue = [segments[row[0]] for row in rows]
    try:
        for offset in range(0, len(queue), batch_size):
            if cancel.is_set():
                break
            batch, protected = [], []
            for segment in queue[offset:offset + batch_size]:
                entry = project.translation(segment.id)
                recalled = project.recalled(segment) if not entry else None
                if entry or recalled:
                    if recalled:
                        project.save_translation(segment.id, recalled, provider="memory", automatic=True)
                    with project.db:
                        project.db.execute("UPDATE job_items SET state='Done',error=NULL WHERE job_id=? AND segment_id=?", (job_id, segment.id))
                    continue
                batch.append(segment)
                protected.append(protect(segment.text, project.glossary()))
            if not batch:
                continue
            with project.db:
                project.db.executemany("UPDATE job_items SET attempts=attempts+1 WHERE job_id=? AND segment_id=?", [(job_id, s.id) for s in batch])
            try:
                result = provider.translate_batch([p.text for p in protected], project.source, project.target, cancel)
                if len(result.texts) != len(batch):
                    raise ProviderError("Provider result count mismatch")
                # Usage is recorded even when a paid response fails token validation.
                with project.db:
                    project.db.execute("UPDATE jobs SET billed=billed+? WHERE id=?", (result.billed_characters, job_id))
                for segment, masked, text in zip(batch, protected, result.texts):
                    try:
                        restored = masked.restore(text)
                        validate_translation(segment.text, restored)
                        project.save_translation(segment.id, restored, provider=provider.capabilities.name, automatic=True)
                        with project.db:
                            project.db.execute("UPDATE job_items SET state='Done',error=NULL WHERE job_id=? AND segment_id=?", (job_id, segment.id))
                    except ValueError:
                        with project.db:
                            project.db.execute("UPDATE job_items SET state='Failed',error='Token/translation validation failed' WHERE job_id=? AND segment_id=?", (job_id, segment.id))
            except ProviderError as exc:
                if cancel.is_set():
                    break
                with project.db:
                    project.db.executemany("UPDATE job_items SET state='Failed',error=? WHERE job_id=? AND segment_id=?", [(str(exc), job_id, s.id) for s in batch])
                # Stop on service/auth failures. Resume is an explicit action.
                break
            finally:
                checkpoint(project, job_id, "Running")
            if progress:
                progress(job_report(project, job_id))
    finally:
        pending = project.db.execute("SELECT count(*) FROM job_items WHERE job_id=? AND state='Pending'", (job_id,)).fetchone()[0]
        failed = project.db.execute("SELECT count(*) FROM job_items WHERE job_id=? AND state='Failed'", (job_id,)).fetchone()[0]
        state = "Paused" if cancel.is_set() or pending else ("CompletedWithErrors" if failed else "Completed")
        checkpoint(project, job_id, state)
    return job_report(project, job_id)


def checkpoint(project, job_id, state):
    counts = dict(project.db.execute("SELECT state,count(*) FROM job_items WHERE job_id=? GROUP BY state", (job_id,)).fetchall())
    with project.db:
        project.db.execute("UPDATE jobs SET state=?,completed=?,failed=?,updated=? WHERE id=?",
                           (state, counts.get("Done", 0), counts.get("Failed", 0), now(), job_id))
