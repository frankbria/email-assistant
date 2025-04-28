# main_with_db_populate.py

import sys
import subprocess
import logging

logger = logging.getLogger(__name__)


def populate_db():
    logger.debug("Populating database...")
    subprocess.run(["python", "populate_db_script.py"], check=True)


def start_uvicorn():
    logger.debug("Starting Uvicorn...")
    subprocess.run(
        ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
        check=True,
    )


if __name__ == "__main__":
    if "--populate_db" in sys.argv:
        populate_db()
        sys.argv.remove("--populate_db")
    start_uvicorn()
