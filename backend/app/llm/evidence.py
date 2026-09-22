"""Bounded test evidence for model prompts, with failure details before warnings."""
import re


def failure_excerpt(output: str, limit: int = 4000) -> str:
    text = str(output)
    warning = re.search(r"(?m)^=+ warnings summary =+", text)
    if warning:
        text = text[:warning.start()].rstrip()
    if len(text) <= limit:
        return text
    marker = "\n... output omitted ...\n"
    head = (limit - len(marker)) * 3 // 4
    tail = limit - len(marker) - head
    return text[:head] + marker + text[-tail:]
