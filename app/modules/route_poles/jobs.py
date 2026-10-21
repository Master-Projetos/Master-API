"""Progress of the backbone uploads.

Kept in memory, per process: it is only for watching an upload, so a restart
(or another worker) loses it. The result itself is the stored backbone.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

MAX_JOBS = 100


class JobStatus(StrEnum):
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'


@dataclass
class BackboneJob:
    filename: str
    id: UUID = field(default_factory=uuid4)
    status: JobStatus = JobStatus.RUNNING
    stage: str = 'queued'
    cities_done: int = 0
    cities_total: int = 0
    current_city: str | None = None
    error: str | None = None
    backbone_id: UUID | None = None
    backbone_code: str | None = None
    # The licensed poles sent with the routes, if any
    licensed_code: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

    def progress(
        self, stage: str, done: int, total: int, city: str | None
    ) -> None:
        self.stage = stage
        self.cities_done = done
        self.cities_total = total
        self.current_city = city

    def complete(self, backbone_id: UUID, backbone_code: str) -> None:
        self.backbone_id = backbone_id
        self.backbone_code = backbone_code
        self.stage = 'completed'
        self.current_city = None
        self._finish(JobStatus.COMPLETED)

    def fail(self, error: str) -> None:
        self.error = error
        self._finish(JobStatus.FAILED)

    def _finish(self, status: JobStatus) -> None:
        self.status = status
        self.finished_at = datetime.now(UTC)


_jobs: dict[UUID, BackboneJob] = {}


def create_job(filename: str) -> BackboneJob:
    job = BackboneJob(filename)
    _jobs[job.id] = job
    # Dicts keep the insertion order, so the first finished one is the oldest
    finished = [j.id for j in _jobs.values() if j.finished_at]
    for job_id in finished[: max(0, len(_jobs) - MAX_JOBS)]:
        del _jobs[job_id]
    return job


def get_job(job_id: UUID) -> BackboneJob | None:
    return _jobs.get(job_id)
