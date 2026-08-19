"""
Deterministic demo fixture for Phase 4 autonomous software engineering testing.
"""

def add(a: int, b: int) -> int:
    # Intentional deterministic bug: subtraction instead of addition
    return a - b
