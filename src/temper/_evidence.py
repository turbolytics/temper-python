"""The evidence file: append-only, one file per process, one write per line."""

import json
import os
import re
import secrets
from pathlib import Path

_SEPARATORS = (",", ":")


def encode(record):
    """One record as one UTF-8 line, keys in the order given, compact."""
    try:
        return (json.dumps(record, separators=_SEPARATORS, ensure_ascii=False) + "\n").encode("utf-8")
    except UnicodeEncodeError:
        # A lone surrogate (an odd test id) cannot be UTF-8; JSON can still escape it.
        return (json.dumps(record, separators=_SEPARATORS, ensure_ascii=True) + "\n").encode("utf-8")


class Writer:
    """Appends records to ``<level>-<pid>-<8 hex>.jsonl`` in a directory.

    The file is created on the first record, never opened for truncation, and
    never shared: a forked child opens its own.
    """

    def __init__(self, directory, level):
        self._dir = Path(directory)
        self._level = level
        self._fd = None
        self._pid = None

    def ensure_directory(self):
        self._dir.mkdir(parents=True, exist_ok=True)

    def write(self, record):
        data = encode(record)
        fd = self._open()
        written = os.write(fd, data)
        while written < len(data):  # a short write is rare; finish the line
            written += os.write(fd, data[written:])

    def close(self):
        if self._fd is not None and self._pid == os.getpid():
            os.close(self._fd)
        self._fd = None

    def _open(self):
        pid = os.getpid()
        if self._fd is not None and self._pid == pid:
            return self._fd
        self._fd = None  # inherited across a fork: leave the parent's file alone
        self.ensure_directory()
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", self._level)
        name = f"{safe}-{pid}-{secrets.token_hex(4)}.jsonl"
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL
        self._fd = os.open(self._dir / name, flags, 0o644)
        self._pid = pid
        return self._fd
