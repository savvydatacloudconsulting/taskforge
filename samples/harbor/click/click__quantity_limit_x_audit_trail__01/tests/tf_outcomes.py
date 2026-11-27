"""A tiny pytest plugin: write the outcome of every test to the JSON file named in TF_OUTCOMES.

It is copied into each exported task as tests/tf_outcomes.py. Standard library only.
"""

import json
import os

_outcomes = {}


def pytest_runtest_logreport(report):
    if report.failed:
        _outcomes[report.nodeid] = "failed"
    elif report.skipped:  # includes expected failures (xfail)
        _outcomes.setdefault(report.nodeid, "skipped")
    elif report.when == "call":
        _outcomes.setdefault(report.nodeid, "passed")


def pytest_sessionfinish(session):
    target = os.environ.get("TF_OUTCOMES")
    if target and not hasattr(session.config, "workerinput"):
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(_outcomes, handle)
