"""Backup restore is deliberately non-destructive: restore into an empty ledger."""
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from .protocol import ProtocolError


def restore(root, source):
    root, source = Path(root).resolve(), Path(source).resolve()
    state = root / '.specalign'
    destination = state / 'state.sqlite3'
    if destination.exists():
        raise ProtocolError('Restore requires an empty ledger; restore into a fresh project copy')
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ProtocolError('Invalid SQLite backup')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'snapshots', 'reviews', 'state', 'deliveries'}.issubset(tables):
            raise ProtocolError('Not a Spec Align backup')
        state.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix='restore-', dir=state)
        os.close(descriptor)
        try:
            with closing(sqlite3.connect(name)) as copy:
                db.backup(copy)
            # Exclusive creation avoids replacing a ledger created concurrently.
            os.link(name, destination)
        finally:
            Path(name).unlink(missing_ok=True)
    return {'restored': str(destination)}

