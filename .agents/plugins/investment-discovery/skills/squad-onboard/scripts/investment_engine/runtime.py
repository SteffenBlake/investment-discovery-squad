"""Serialize central-owner operations across commands; no independent writable worker copies."""

import fcntl
import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from .configuration import private_directory

_HELD = ContextVar('squad_held_locks', default=frozenset())


@contextmanager
def owner_lock(settings, *, create=False):
    path = Path(settings['storage']['database_path']).parent / '.squad-lock'
    if str(path) in _HELD.get():
        yield
        return
    if create:
        private_directory(path.parent)
    if not path.parent.exists():
        raise ValueError('Owner data directory missing; restore state or explicitly initialize')
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Central owner busy; retry this command after the active operation finishes') from exc
        token = _HELD.set(_HELD.get() | {str(path)})
        try:
            yield
        finally:
            _HELD.reset(token)
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)
