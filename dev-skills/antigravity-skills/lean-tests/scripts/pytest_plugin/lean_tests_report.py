"""pytest plugin for lean-tests: one JSON line per test phase.

lean_tests.py loads this plugin with `-p lean_tests_report` and puts this
directory in front of the existing PYTHONPATH. LEAN_TESTS_RECORDS names the
output file. LEAN_TESTS_REVERSE=1 reverses the collected tests. Each line
records a node ID, a phase (setup, call, or teardown), the outcome, the
duration, and the exception type name of a failure. The collected record
also lists the fixture names that pytest knows, plugin fixtures included.
When LEAN_TESTS_ADDOPTS names a file, pytest instead writes the addopts of
its configuration there as JSON and exits before collection. Python 3.9 or
newer.
"""

from __future__ import annotations

import json
import os
import time

import pytest

_state: dict = {"config": None, "start": None, "xdist_ids": False}


def _write(record: dict) -> None:
    path = os.environ.get("LEAN_TESTS_RECORDS")
    config = _state["config"]
    # Under pytest-xdist only the controller writes; it receives every report.
    if not path or (config is not None and hasattr(config, "workerinput")):
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config):
    path = os.environ.get("LEAN_TESTS_ADDOPTS")
    if not path:
        return None
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"addopts": config.getini("addopts")}, handle)
    return 0


def pytest_configure(config) -> None:
    _state["config"] = config
    rootdir = getattr(config, "rootpath", None) or getattr(config, "rootdir", "")
    _write({"event": "start", "rootdir": str(rootdir), "pytest_version": pytest.__version__})


@pytest.hookimpl(tryfirst=True)
def pytest_collection(session) -> None:
    _state["start"] = time.perf_counter()


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(session, config, items) -> None:
    if os.environ.get("LEAN_TESTS_REVERSE") == "1":
        items.reverse()


def pytest_collection_finish(session) -> None:
    start = _state["start"]
    seconds = None if start is None else time.perf_counter() - start
    definitions = getattr(getattr(session, "_fixturemanager", None), "_arg2fixturedefs", None)
    _write({
        "event": "collected",
        "seconds": seconds,
        "nodeids": [item.nodeid for item in session.items],
        "fixtures": None if definitions is None else sorted(definitions),
    })


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_node_collection_finished(node, ids) -> None:
    if not _state["xdist_ids"]:
        _state["xdist_ids"] = True
        _write({"event": "collected", "seconds": None, "nodeids": list(ids)})


def pytest_collectreport(report) -> None:
    if report.failed:
        _write({"event": "collect-error", "nodeid": report.nodeid})


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if call.excinfo is not None and report.failed:
        report.lean_tests_exception = call.excinfo.typename


def pytest_runtest_logreport(report) -> None:
    _write({
        "nodeid": report.nodeid,
        "when": report.when,
        "outcome": report.outcome,
        "seconds": report.duration,
        "exception": getattr(report, "lean_tests_exception", None),
        "xfail": hasattr(report, "wasxfail"),
    })
