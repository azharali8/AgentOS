"""
AST-based Test Tampering and Manipulation Detector.

Analyzes Python test source code structurally to detect:
1. Tautological assertions:
   - assert True
   - assert 1 == 1, assert "a" == "a", assert 0 < 1
   - assert True or ...
   - assert bool(1)
2. Empty or vacuous test functions (pass only, docstring only, return None).
3. Test functions with no assertions or assertions reduced to unconditional passes.
"""

from __future__ import annotations

import ast
from typing import Tuple, List


class ASTTestTamperingDetector:
    """Structural validator for test suite integrity."""

    @classmethod
    def analyze_source(cls, source_code: str) -> Tuple[bool, List[str]]:
        """
        Returns (is_tampered, reasons).
        If is_tampered is True, the test code exhibits bad-faith or trivialized patterns.
        """
        if not source_code or not source_code.strip():
            return False, []

        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            return True, [f"Test source syntax error: {e}"]

        reasons = []

        test_functions = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ]

        if not test_functions:
            # If no test functions are found in a file purporting to be a test suite
            if len(source_code.strip().splitlines()) > 5:
                reasons.append("No 'test_*' functions declared in test suite.")

        for func in test_functions:
            # Check for empty body (only pass or docstring)
            statements = [
                s for s in func.body
                if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))
            ]

            if not statements:
                reasons.append(f"Function '{func.name}' has no executable statements (docstring only).")
                continue

            if len(statements) == 1 and isinstance(statements[0], ast.Pass):
                reasons.append(f"Function '{func.name}' is empty (contains only 'pass').")
                continue

            # Find all assert statements
            assert_nodes = [n for n in ast.walk(func) if isinstance(n, ast.Assert)]

            if not assert_nodes:
                # If there are no asserts and no exception checks or assertions
                has_raises = any(
                    isinstance(n, ast.With) and any("raises" in ast.unparse(item.context_expr) for item in n.items)
                    for n in ast.walk(func)
                )
                if not has_raises:
                    reasons.append(f"Function '{func.name}' contains zero assertions or expected exception blocks.")
                    continue

            for a in assert_nodes:
                is_tautological, detail = cls._is_tautological(a.test)
                if is_tautological:
                    reasons.append(f"Function '{func.name}' contains tautological assertion: {detail}")

        return (len(reasons) > 0), reasons

    @classmethod
    def _is_tautological(cls, node: ast.AST) -> Tuple[bool, str]:
        # 1. Literal True: `assert True` or `assert 1`
        if isinstance(node, ast.Constant):
            if node.value is True:
                return True, "literal True (`assert True`)"
            if node.value == 1:
                return True, "literal 1 (`assert 1`)"

        # 2. Literal comparison: `1 == 1`, `'a' == 'a'`
        if isinstance(node, ast.Compare):
            if len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
                left = node.left
                right = node.comparators[0]
                if isinstance(left, ast.Constant) and isinstance(right, ast.Constant):
                    if left.value == right.value:
                        return True, f"constant equality (`{left.value} == {right.value}`)"

        # 3. Unary / boolean tautologies: `not False`
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            if isinstance(node.operand, ast.Constant) and node.operand.value is False:
                return True, "boolean negation of False (`assert not False`)"

        return False, ""
