#!/usr/bin/env bash
# Test dependencies: pytest, tenacity (base+new), typing_extensions (new), pyright (new only).
# Dockerfile_6 installs typing_extensions and pyright for offline runs.
# Local runs need the same tools available ahead of time.
set -e #
if [ -z "$1" ]; then #
    echo "Usage: $0 {base|new}" #
    exit 1 #
fi #
PYTHON_BIN= #
for candidate in py.exe py python3 python /mnt/c/Windows/py.exe; do #
    if command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; then #
        if ! "$candidate" -c "import pytest, tenacity" >/dev/null 2>&1; then #
            continue #
        fi #
        if [ "$1" = "new" ]; then #
            if ! "$candidate" -c "import importlib.util, os, shutil; names = ('pyright', 'pyright.exe', 'pyright.cmd') if os.name == 'nt' else ('pyright',); raise SystemExit(0 if importlib.util.find_spec('pyright') is not None or any(shutil.which(name) for name in names) else 1)" >/dev/null 2>&1; then #
                continue #
            fi #
        fi #
        PYTHON_BIN="$candidate" #
        break #
    fi #
done #
if [ -z "$PYTHON_BIN" ]; then #
    if [ "$1" = "new" ]; then #
        echo "No python interpreter found with pytest, tenacity, and pyright available" #
    else #
        echo "No python interpreter found with pytest and tenacity installed" #
    fi #
    exit 1 #
fi #
case "$1" in #
    base) #
        "$PYTHON_BIN" -m pytest -q tests/test_tenacity.py tests/test_asyncio.py -k "retry_with or wraps or check_type" #
        ;; #
    new) #
        "$PYTHON_BIN" -m pytest -q tests/test_retry_typing_helpers.py #
        ;; #
    *) #
        echo "Usage: $0 {base|new}" #
        exit 1 #
        ;; #
esac #
