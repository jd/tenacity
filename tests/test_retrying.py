import pytest


def test_retrying():
    try:
        from retrying import retry
    except ImportError:
        assert False, "Failed to import retrying"
