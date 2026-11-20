"""Fixtures resolve the same whichever test files are run together (#175)."""

import subprocess
import sys
from pathlib import Path

TESTS = Path(__file__).parent
BACKEND = TESTS.parent


def test_every_fixture_resolves_when_a_directorys_files_are_split_on_the_command_line() -> None:
    # pytest 9 binds a conftest's fixtures to the first node it builds for that directory,
    # so naming a directory's files on either side of another file collects the directory
    # twice; the second half used to lose those fixtures.
    directories = [directory for directory in sorted(TESTS.iterdir()) if len(sorted(directory.glob("test_*.py"))) >= 2]
    first_halves = [str(sorted(directory.glob("test_*.py"))[0]) for directory in directories]
    second_halves = [str(path) for directory in directories for path in sorted(directory.glob("test_*.py"))[1:]]
    command = [sys.executable, "-m", "pytest", "--setup-plan", "-q", "-p", "no:cacheprovider"]
    command += [*first_halves, str(TESTS / "test_send.py"), *second_halves]

    finished = subprocess.run(command, cwd=BACKEND, capture_output=True, text=True, timeout=300, check=False)

    assert "not found" not in finished.stdout, finished.stdout[-3000:]
    assert finished.returncode == 0, finished.stdout[-3000:]
