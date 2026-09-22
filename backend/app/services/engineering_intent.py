"""Conservative intent and test-result semantics shared by planning and execution."""
import re


def engineering_intent(instruction: str) -> str:
    text = instruction.lower().strip()
    # A recommendation is read-only; it does not authorize applying a fix.
    text = re.sub(r"(?:suggest|recommend|provide|describe|explain) (?:a |the )?fix(?: recommendation)?", "explain", text)
    text = re.sub(r"(?:do not|don't|without) (?:fix|change|modify)[^,.]*", "", text)
    if re.search(r"\b(fix|repair|resolve)\b|make .*tests? pass", text):
        return "fix"
    if re.search(r"\b(diagnos\w*|debug\w*)\b|find .*bugs?|explain .*fail|why .*fail", text):
        return "diagnose"
    if re.match(r"^(run|execute) (the |full |all )*(tests|test suite)\b", text):
        return "test"
    return "implement"


def valid_test_result(result) -> bool:
    r = result.model_dump() if hasattr(result, "model_dump") else result
    evidence = r.get("evidence", {})
    data = evidence.get("test_results", {})
    if evidence.get("execution_failed") or data.get("timed_out") or data.get("error"):
        return False
    code = data.get("exit_code")
    if code in (0, 1):
        return True
    # Pytest collection errors contain actionable repository failure evidence.
    return code == 2 and (data.get("counts", {}).get("errors") or 0) > 0


def failed_test_result(result) -> bool:
    r = result.model_dump() if hasattr(result, "model_dump") else result
    return r.get("agent_type") == "testing" and valid_test_result(r) and r.get("evidence", {}).get("passed") is False
