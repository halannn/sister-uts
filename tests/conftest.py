# Ringkasan PASS/FAIL per test + durasi + deskripsi.
import logging
import time
import pytest

_CASE_META = {}
_RESULTS = []

def pytest_configure(config):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

def pytest_runtest_setup(item):
    doc = (getattr(item.obj, "__doc__", "") or "").strip()
    _CASE_META[item.nodeid] = {"name": item.name, "doc": doc}

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call":
        _RESULTS.append(
            {
                "nodeid": item.nodeid,
                "name": item.name,
                "outcome": rep.outcome,  # passed/failed/Skipped
                "duration_ms": rep.duration * 1000.0,
                "doc": _CASE_META.get(item.nodeid, {}).get("doc", ""),
            }
        )

def pytest_terminal_summary(terminalreporter, exitstatus, config):
    term = terminalreporter
    term.write_sep("=", "Test Case Results")
    for r in _RESULTS:
        icon = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}[r["outcome"]]
        desc = f" - {r['doc']}" if r["doc"] else ""
        term.write_line(f"{icon:4} {r['name']} ({r['duration_ms']:.1f} ms){desc}")
    term.write_line("")
    counts = {k: len(terminalreporter.stats.get(k, [])) for k in ("passed", "failed", "skipped", "error")}
    term.write_sep("-", f"Summary: passed={counts.get('passed',0)} failed={counts.get('failed',0)} skipped={counts.get('skipped',0)} errors={counts.get('error',0)}")