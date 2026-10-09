"""Serialize project selection and task admission in the single-process engine."""
from functools import wraps
from threading import RLock
from inspect import signature

workspace_transition_lock = RLock()


def workspace_transition(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with workspace_transition_lock:
            return function(*args, **kwargs)
    wrapped.__signature__ = signature(function, eval_str=True)
    return wrapped
