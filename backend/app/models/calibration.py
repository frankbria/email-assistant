"""A proposal from a calibration dry run (spec §10.7), shown on the ask-owner card. Kept apart from the job queue so
nothing ever acts on it."""

from pymongo import ASCENDING, IndexModel

from app.models.job import Job, Verb


class CalibrationJob(Job):
    proposed: Verb | None = None  # the AI's verb; None when it asked the owner
    text: str = ""  # the minimized message, for the test set

    class Settings:
        name = "calibration_jobs"
        # one card per message, also when two runs overlap: one reaction must be one test-set line
        indexes = [IndexModel([("owner_id", ASCENDING), ("message_ids", ASCENDING)], unique=True)]
