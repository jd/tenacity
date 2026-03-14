import asyncio
import functools
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest
from tenacity import Retrying
from tenacity import retry
from tenacity import RetryError
from tenacity import stop_after_attempt
from tenacity import wait_fixed
from tenacity.asyncio import AsyncRetrying


ROOT = pathlib.Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "tests" / "typing_samples"
UPDATED_WAIT_SECONDS = 0.1

POSITIVE_SAMPLES = [
    "decorator_factory_async.py",
    "decorator_factory_sync.py",
    "decorator_raw_async.py",
    "decorator_raw_sync.py",
    "wraps_async.py",
    "wraps_sync.py",
]

NEGATIVE_SAMPLES = [
    "decorator_factory_async_negative.py",
    "decorator_factory_async_retry_with_negative.py",
    "decorator_factory_sync_negative.py",
    "decorator_factory_sync_retry_with_negative.py",
    "decorator_raw_async_negative.py",
    "decorator_raw_async_retry_with_negative.py",
    "decorator_raw_sync_negative.py",
    "decorator_raw_sync_retry_with_negative.py",
    "wraps_async_negative.py",
    "wraps_async_retry_with_negative.py",
    "wraps_sync_negative.py",
    "wraps_sync_retry_with_negative.py",
]


def pyright_command():
    if importlib.util.find_spec("pyright") is not None:
        return [sys.executable, "-m", "pyright"]
    if os.name == "nt":
        candidate_names = ("pyright", "pyright.exe", "pyright.cmd")
    else:
        candidate_names = ("pyright",)
    for name in candidate_names:
        cli = shutil.which(name)
        if cli is not None:
            return [cli]
    raise AssertionError("pyright must be available as a Python module or CLI")


def _sync_noop_sleep(seconds):
    return None


async def _async_noop_sleep(seconds):
    return None


@functools.lru_cache(maxsize=None)
def run_pyright(sample_name):
    sample_path = SAMPLE_DIR / sample_name
    completed = subprocess.run(
        pyright_command() + ["--outputjson", str(sample_path)],
        capture_output=True,
        check=False,
        cwd=ROOT,
        text=True,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            "pyright did not return JSON\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        ) from exc
    payload["returncode"] = completed.returncode
    payload["stderr"] = completed.stderr
    return payload


def error_diagnostics(sample_name):
    return [
        diagnostic
        for diagnostic in run_pyright(sample_name)["generalDiagnostics"]
        if diagnostic["severity"] == "error"
    ]


def error_messages(sample_name):
    return [diagnostic["message"] for diagnostic in error_diagnostics(sample_name)]


@functools.lru_cache(maxsize=None)
def expected_error_lines(sample_name):
    sample_path = SAMPLE_DIR / sample_name
    marked_lines = {
        line_number
        for line_number, line in enumerate(
            sample_path.read_text(encoding="utf-8").splitlines(), start=1
        )
        if "# EXPECTED_PYRIGHT_ERROR" in line
    }
    assert marked_lines, f"{sample_name} must mark an expected pyright error line"
    return marked_lines


def error_lines(sample_name):
    return {
        diagnostic["range"]["start"]["line"] + 1
        for diagnostic in error_diagnostics(sample_name)
    }


def format_diagnostics(sample_name):
    return "\n".join(
        f"{diagnostic['range']['start']['line'] + 1}: {diagnostic['message']}"
        for diagnostic in error_diagnostics(sample_name)
    )


@pytest.mark.parametrize("sample_name", POSITIVE_SAMPLES)
def test_pyright_positive_samples_have_no_errors(sample_name):
    payload = run_pyright(sample_name)
    assert payload["returncode"] == 0, "\n".join(error_messages(sample_name))


@pytest.mark.parametrize("sample_name", NEGATIVE_SAMPLES)
def test_pyright_negative_samples_only_fail_for_intended_mismatch(sample_name):
    payload = run_pyright(sample_name)
    assert payload["returncode"] != 0
    assert error_lines(sample_name) == expected_error_lines(sample_name), (
        "Unexpected pyright error locations:\n" + format_diagnostics(sample_name)
    )


def _build_sync_wrapped(entrypoint):
    def target(value: int) -> int:
        return value + 1

    if entrypoint == "decorator_factory":

        @retry(stop=stop_after_attempt(1), wait=wait_fixed(0))
        def wrapped(value: int) -> int:
            return value + 1

        return wrapped

    if entrypoint == "decorator_raw":
        return retry(target)

    if entrypoint == "wraps":
        return Retrying(stop=stop_after_attempt(1), wait=wait_fixed(0)).wraps(target)

    raise AssertionError(f"unsupported entrypoint: {entrypoint}")


def _build_async_wrapped(entrypoint):
    async def target(value: int) -> int:
        return value + 1

    if entrypoint == "decorator_factory":

        @retry(stop=stop_after_attempt(1), wait=wait_fixed(0))
        async def wrapped(value: int) -> int:
            return value + 1

        return wrapped

    if entrypoint == "decorator_raw":
        return retry(target)

    if entrypoint == "wraps":
        return AsyncRetrying(stop=stop_after_attempt(1), wait=wait_fixed(0)).wraps(
            target
        )

    raise AssertionError(f"unsupported entrypoint: {entrypoint}")


def _build_sync_flaky(entrypoint):
    attempts = {"count": 0}

    def target() -> int:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise ValueError("boom")
        return attempts["count"]

    if entrypoint == "decorator_factory":

        @retry(stop=stop_after_attempt(1), wait=wait_fixed(0))
        def wrapped() -> int:
            return target()

        return wrapped, attempts

    if entrypoint == "decorator_raw":
        return retry(target), attempts

    if entrypoint == "wraps":
        return Retrying(stop=stop_after_attempt(1), wait=wait_fixed(0)).wraps(target), attempts

    raise AssertionError(f"unsupported entrypoint: {entrypoint}")


def _build_async_flaky(entrypoint):
    attempts = {"count": 0}

    async def target() -> int:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise ValueError("boom")
        return attempts["count"]

    if entrypoint == "decorator_factory":

        @retry(stop=stop_after_attempt(1), wait=wait_fixed(0))
        async def wrapped() -> int:
            return await target()

        return wrapped, attempts

    if entrypoint == "decorator_raw":
        return retry(target), attempts

    if entrypoint == "wraps":
        return AsyncRetrying(stop=stop_after_attempt(1), wait=wait_fixed(0)).wraps(target), attempts

    raise AssertionError(f"unsupported entrypoint: {entrypoint}")


@pytest.mark.parametrize("entrypoint", ["decorator_factory", "decorator_raw", "wraps"])
def test_retry_with_returns_distinct_sync_callable(entrypoint):
    wrapped = _build_sync_wrapped(entrypoint)
    reconfigured = wrapped.retry_with(stop=stop_after_attempt(2))
    chained = reconfigured.retry_with(wait=wait_fixed(3))

    assert reconfigured is not wrapped
    assert chained is not reconfigured
    assert chained is not wrapped
    assert wrapped(1) == 2
    assert reconfigured(1) == 2
    assert chained(1) == 2


@pytest.mark.parametrize("entrypoint", ["decorator_factory", "decorator_raw", "wraps"])
def test_retry_with_returns_distinct_async_callable(entrypoint):
    wrapped = _build_async_wrapped(entrypoint)
    reconfigured = wrapped.retry_with(stop=stop_after_attempt(2))
    chained = reconfigured.retry_with(wait=wait_fixed(3))

    assert reconfigured is not wrapped
    assert chained is not reconfigured
    assert chained is not wrapped
    assert asyncio.run(wrapped(1)) == 2
    assert asyncio.run(reconfigured(1)) == 2
    assert asyncio.run(chained(1)) == 2


@pytest.mark.parametrize("entrypoint", ["decorator_factory", "decorator_raw", "wraps"])
def test_retry_with_updated_stop_takes_effect_sync(entrypoint):
    wrapped, attempts = _build_sync_flaky(entrypoint)

    attempts["count"] = 0
    if entrypoint == "decorator_raw":
        assert wrapped() == 2
        assert attempts["count"] == 2

        attempts["count"] = 0
        reconfigured = wrapped.retry_with(stop=stop_after_attempt(1))

        with pytest.raises(RetryError):
            reconfigured()
        assert attempts["count"] == 1
        return

    with pytest.raises(RetryError):
        wrapped()
    assert attempts["count"] == 1

    attempts["count"] = 0
    reconfigured = wrapped.retry_with(stop=stop_after_attempt(2))

    assert reconfigured() == 2
    assert attempts["count"] == 2


@pytest.mark.parametrize("entrypoint", ["decorator_factory", "decorator_raw", "wraps"])
def test_retry_with_updated_wait_takes_effect_sync(entrypoint):
    wrapped, attempts = _build_sync_flaky(entrypoint)
    wait_reconfigured = wrapped.retry_with(
        stop=stop_after_attempt(2),
        wait=wait_fixed(UPDATED_WAIT_SECONDS),
        sleep=_sync_noop_sleep,
    )

    assert wait_reconfigured() == 2
    assert attempts["count"] == 2
    assert wait_reconfigured.statistics["idle_for"] == pytest.approx(
        UPDATED_WAIT_SECONDS
    )


@pytest.mark.parametrize("entrypoint", ["decorator_factory", "decorator_raw", "wraps"])
def test_retry_with_updated_stop_takes_effect_async(entrypoint):
    wrapped, attempts = _build_async_flaky(entrypoint)

    attempts["count"] = 0
    if entrypoint == "decorator_raw":
        assert asyncio.run(wrapped()) == 2
        assert attempts["count"] == 2

        attempts["count"] = 0
        reconfigured = wrapped.retry_with(stop=stop_after_attempt(1))

        with pytest.raises(RetryError):
            asyncio.run(reconfigured())
        assert attempts["count"] == 1
        return

    with pytest.raises(RetryError):
        asyncio.run(wrapped())
    assert attempts["count"] == 1

    attempts["count"] = 0
    reconfigured = wrapped.retry_with(stop=stop_after_attempt(2))

    assert asyncio.run(reconfigured()) == 2
    assert attempts["count"] == 2


@pytest.mark.parametrize("entrypoint", ["decorator_factory", "decorator_raw", "wraps"])
def test_retry_with_updated_wait_takes_effect_async(entrypoint):
    wrapped, attempts = _build_async_flaky(entrypoint)
    wait_reconfigured = wrapped.retry_with(
        stop=stop_after_attempt(2),
        wait=wait_fixed(UPDATED_WAIT_SECONDS),
        sleep=_async_noop_sleep,
    )

    assert asyncio.run(wait_reconfigured()) == 2
    assert attempts["count"] == 2
    assert wait_reconfigured.statistics["idle_for"] == pytest.approx(
        UPDATED_WAIT_SECONDS
    )
