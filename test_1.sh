#!/usr/bin/env bash
set -e

if [ -z "$1" ]; then
    echo "Usage: $0 {base|new}"
    exit 1
fi

PYTHON_BIN=
for candidate in py.exe py python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c "import pytest, tenacity" >/dev/null 2>&1; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "No python interpreter found with pytest and tenacity installed"
    exit 1
fi

case "$1" in
    base)
        "$PYTHON_BIN" -m pytest tests/test_tenacity.py::TestMockingSleep::test_decorated tests/test_tenacity.py::TestMockingSleep::test_decorated_retry_with -x -q --tb=short
        ;;
    new)
        "$PYTHON_BIN" -m pytest tests/test_sleep_patchable.py -x -q --tb=short
        ;;
    *)
        echo "Usage: $0 {base|new}"
        exit 1
        ;;
esac
