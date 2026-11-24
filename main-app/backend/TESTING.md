# Backend tests

Create a clean virtual environment, then install `python -m pip install -r requirements-test.txt` from this directory. The test requirements include the main application and admin backend dependencies because the voice configuration tests import both applications in isolated subprocesses.

Run `python -m pytest app/tests`. The voice subprocesses use temporary directories and an in-memory default database; their migration cases create only temporary synthetic databases.
