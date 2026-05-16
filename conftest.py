"""Project-wide pytest reporting glue for coverage, benchmarks, and Allure."""

from __future__ import annotations

import json
import os
import platform
import shutil
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

PROJECT_NAME = "knightspiral"
REPORTS_DIR = Path("reports")
ALLURE_RESULTS_DIR = REPORTS_DIR / "allure-results"
ALLURE_REPORT_DIR = REPORTS_DIR / "allure-report"
ALLURE_HISTORY_DIR = REPORTS_DIR / "allure-history"
COVERAGE_HTML_DIR = REPORTS_DIR / "coverage-html"
COVERAGE_XML_PATH = REPORTS_DIR / "coverage.xml"
BENCHMARK_JSON_PATH = REPORTS_DIR / "benchmark.json"
ARTIFACT_MANIFEST_PATH = REPORTS_DIR / "artifacts.json"

try:
    import pytest_benchmark  # noqa: F401
except ImportError:  # pragma: no cover - only used in stripped-down local environments.
    @pytest.fixture
    def benchmark() -> None:
        """Skip benchmark tests when pytest-benchmark is not installed."""
        pytest.skip("pytest-benchmark is not installed")


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register project-level reporting options."""
    group = parser.getgroup("knightspiral-reporting")
    group.addoption(
        "--allure-command",
        action="store",
        default=os.environ.get("ALLURE_COMMAND", "allure"),
        help="Allure 3 command used for post-test report generation.",
    )
    group.addoption(
        "--no-allure-generate",
        action="store_true",
        default=False,
        help="Skip automatic Allure HTML report generation after pytest finishes.",
    )


@pytest.fixture(autouse=True)
def _allure_runtime_labels(request: pytest.FixtureRequest) -> None:
    """Apply stable Allure labels without making tests depend on Allure at import time."""
    try:
        import allure
    except ImportError:
        return

    module_name = request.node.module.__name__ if request.node.module is not None else "unknown"
    file_path = Path(str(request.node.fspath))
    environment = "github" if os.environ.get("GITHUB_ACTIONS") == "true" else "local"

    allure.dynamic.label("project", PROJECT_NAME)
    allure.dynamic.label("language", "python")
    allure.dynamic.label("environment", environment)
    allure.dynamic.parent_suite(PROJECT_NAME)

    if "benchmarks" in file_path.parts:
        allure.dynamic.suite("benchmarks")
        allure.dynamic.feature("Performance")
        allure.dynamic.severity(allure.severity_level.NORMAL)
        return

    suite_name = module_name.rsplit(".", 1)[-1].removeprefix("test_").replace("_", " ").title()
    allure.dynamic.suite("tests")
    allure.dynamic.sub_suite(suite_name)

    if "cli" in module_name:
        allure.dynamic.feature("CLI")
    elif "matrix" in module_name:
        allure.dynamic.feature("Matrix Runner")
    elif "game" in module_name:
        allure.dynamic.feature("Simulation")
    elif "spiral" in module_name:
        allure.dynamic.feature("Spiral Indexing")
    else:
        allure.dynamic.feature("Core")


def pytest_configure(config: pytest.Config) -> None:
    """Create report directories before plugins start writing artifacts."""
    for path in (REPORTS_DIR, ALLURE_RESULTS_DIR, ALLURE_REPORT_DIR, ALLURE_HISTORY_DIR, COVERAGE_HTML_DIR):
        path.mkdir(parents=True, exist_ok=True)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Write Allure metadata and generate the configured Allure report."""
    results_dir = _resolve_allure_results_dir(session.config)
    results_dir.mkdir(parents=True, exist_ok=True)
    _write_environment_file(results_dir)
    _write_executor_file(results_dir, exitstatus)
    _write_categories_file(results_dir)
    _write_artifact_manifest(exitstatus)

    if session.config.getoption("--no-allure-generate"):
        return

    if not any(results_dir.glob("*-result.json")):
        return

    _generate_allure_report(session.config, results_dir)


def _resolve_allure_results_dir(config: pytest.Config) -> Path:
    """Resolve the active Allure results directory from pytest/allure options."""
    for attr_name in ("allure_report_dir", "alluredir"):
        value = getattr(config.option, attr_name, None)
        if value:
            return Path(str(value))

    return ALLURE_RESULTS_DIR


def _git_value(*args: str) -> str:
    """Return a Git command value, or a local fallback."""
    try:
        completed = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "local"

    value = completed.stdout.strip()
    return value if value else "local"


def _properties_escape(value: str) -> str:
    """Escape text for Java .properties files."""
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace("=", "\\=")


def _write_environment_file(results_dir: Path) -> None:
    """Write launch-level metadata for Allure's environment block."""
    values = {
        "project": PROJECT_NAME,
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "branch": os.environ.get("GITHUB_REF_NAME") or _git_value("rev-parse", "--abbrev-ref", "HEAD"),
        "commit": os.environ.get("GITHUB_SHA") or _git_value("rev-parse", "--short", "HEAD"),
        "coverage_html": str(COVERAGE_HTML_DIR / "index.html"),
        "coverage_xml": str(COVERAGE_XML_PATH),
        "benchmark_json": str(BENCHMARK_JSON_PATH),
    }
    lines = [f"{_properties_escape(key)} = {_properties_escape(value)}" for key, value in values.items()]
    (results_dir / "environment.properties").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_executor_file(results_dir: Path, exitstatus: int) -> None:
    """Write CI/local executor metadata for Allure."""
    is_github = os.environ.get("GITHUB_ACTIONS") == "true"
    build_order = int(os.environ.get("GITHUB_RUN_NUMBER", int(time.time())))
    repository = os.environ.get("GITHUB_REPOSITORY", "local/knightspiral")
    run_id = os.environ.get("GITHUB_RUN_ID", str(build_order))
    build_url = f"https://github.com/{repository}/actions/runs/{run_id}" if is_github else ""
    executor_type = "github" if is_github else "local"
    executor_name = "GitHub Actions" if is_github else "Local pytest"
    payload = {
        "name": executor_name,
        "type": executor_type,
        "reportName": "KnightSpiral Quality Report",
        "buildName": f"{executor_name} #{build_order}",
        "buildOrder": build_order,
        "buildUrl": build_url,
        "reportUrl": os.environ.get("ALLURE_REPORT_URL", ""),
        "pytestExitStatus": exitstatus,
    }
    (results_dir / "executor.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_categories_file(results_dir: Path) -> None:
    """Write compatibility categories for Allure result consumers."""
    categories: list[dict[str, Any]] = [
        {
            "name": "Benchmark failures",
            "matchedStatuses": ["failed", "broken"],
            "messageRegex": ".*benchmark.*",
        },
        {
            "name": "Coverage failures",
            "matchedStatuses": ["failed", "broken"],
            "messageRegex": ".*(coverage|cov|Coverage).*",
        },
        {
            "name": "Assertion failures",
            "matchedStatuses": ["failed"],
            "traceRegex": ".*AssertionError.*",
        },
        {
            "name": "Broken tests",
            "matchedStatuses": ["broken"],
        },
    ]
    (results_dir / "categories.json").write_text(json.dumps(categories, indent=2), encoding="utf-8")


def _write_artifact_manifest(exitstatus: int) -> None:
    """Write a compact report artifact manifest."""
    artifacts = {
        "exitstatus": exitstatus,
        "allure_results": str(ALLURE_RESULTS_DIR),
        "allure_report": str(ALLURE_REPORT_DIR),
        "allure_history": str(ALLURE_HISTORY_DIR / "history.jsonl"),
        "coverage_html": str(COVERAGE_HTML_DIR / "index.html"),
        "coverage_xml": str(COVERAGE_XML_PATH),
        "benchmark_json": str(BENCHMARK_JSON_PATH),
    }
    ARTIFACT_MANIFEST_PATH.write_text(json.dumps(artifacts, indent=2), encoding="utf-8")


def _generate_allure_report(config: pytest.Config, results_dir: Path) -> None:
    """Generate the Allure HTML report when the Allure CLI is available."""
    allure_command = str(config.getoption("--allure-command"))
    command_prefix = shlex.split(allure_command)
    if not command_prefix:
        command_prefix = ["allure"]

    resolved = shutil.which(command_prefix[0])
    command_prefix[0] = resolved or command_prefix[0]
    command = [*command_prefix, "generate", str(results_dir)]

    try:
        completed = subprocess.run(command, check=False, text=True, capture_output=True)
    except OSError as error:
        terminal = config.pluginmanager.get_plugin("terminalreporter")
        if terminal is not None:
            terminal.write_line(f"Allure report skipped: {error}", red=True)
        return

    terminal = config.pluginmanager.get_plugin("terminalreporter")
    if terminal is None:
        return

    if completed.returncode == 0:
        terminal.write_line(f"Allure report written to {ALLURE_REPORT_DIR}", green=True)
        return

    terminal.write_line("Allure report generation failed.", red=True)
    if completed.stdout.strip():
        terminal.write_line(completed.stdout.strip())
    if completed.stderr.strip():
        terminal.write_line(completed.stderr.strip(), red=True)
