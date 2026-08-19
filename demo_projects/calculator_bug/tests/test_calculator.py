"""
Deterministic unit test for Phase 4 calculator bug fixture.
"""

from calculator import add


def test_add():
    assert add(2, 3) == 5
