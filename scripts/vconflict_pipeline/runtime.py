"""Local cross-process coordination. Case JSON remains the source of results."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .core import PipelineError, atomic_write_json, load_case
from .settings import PROJECT_ROOT

RUNTIME_DIR = PROJECT_ROOT / "artifacts" / "pipeline_runtime"


def path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


class FileLock:
    """Persistent lock inode; never unlink it while another process may use it."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open("a+b")
        if not path.stat().st_size:
            self.stream.write(b"\0")
            self.stream.flush()
        self.locked = False

    def acquire(self, blocking: bool = True) -> bool:
        while True:
            try:
                self.stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.locked = True
                return True
            except (BlockingIOError, PermissionError):
                if not blocking:
                    return False
                time.sleep(0.05)
            except OSError as exc:
                # Windows reports lock contention as EACCES/EDEADLK.
                if exc.errno not in (11, 13, 36):
                    raise
                if not blocking:
                    return False
                time.sleep(0.05)

    def close(self):
        if self.locked:
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        self.stream.close()
        self.locked = False

    def __enter__(self):
        try:
            self.acquire()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *_):
        self.close()


def case_lock(path: Path) -> FileLock:
    name = hashlib.sha256(path_key(path).encode()).hexdigest()
    return FileLock(RUNTIME_DIR / "cases" / (name + ".lock"))


class Runtime:
    def __init__(self, paths, *, exclusive=False):
        self.id = uuid.uuid4().hex
        self.paths = sorted({path_key(p) for p in paths})
        self.exclusive = exclusive
        self.stop = threading.Event()
        self.mutex = threading.RLock()
        self.heartbeat_error = None
        self.life = FileLock(RUNTIME_DIR / "runs" / (self.id + ".lock"))
        self.life.acquire()
        self.db = None
        try:
            self.db = sqlite3.connect(RUNTIME_DIR / "coordination.sqlite3", timeout=30,
                                      isolation_level=None, check_same_thread=False)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, heartbeat REAL);
                CREATE TABLE IF NOT EXISTS cases(path TEXT, run TEXT, exclusive INTEGER,
                    PRIMARY KEY(path,run));
                CREATE TABLE IF NOT EXISTS versions(path TEXT PRIMARY KEY, version INTEGER);
                CREATE TABLE IF NOT EXISTS tasks(key TEXT PRIMARY KEY, owner TEXT, token TEXT,
                    state TEXT, error TEXT);
                CREATE TABLE IF NOT EXISTS subscribers(key TEXT, run TEXT, PRIMARY KEY(key,run));
                CREATE TABLE IF NOT EXISTS resources(key TEXT PRIMARY KEY, capacity INTEGER,
                    rpm REAL, next_start REAL, cooldown REAL);
                CREATE TABLE IF NOT EXISTS users(resource TEXT, run TEXT, PRIMARY KEY(resource,run));
                CREATE TABLE IF NOT EXISTS permits(token TEXT, resource TEXT, run TEXT,
                    deadline REAL, PRIMARY KEY(token,resource));
                CREATE TABLE IF NOT EXISTS waiters(resource TEXT, run TEXT, touched REAL,
                    last_grant REAL, PRIMARY KEY(resource,run));
                CREATE TABLE IF NOT EXISTS demands(run TEXT, lane TEXT, resources TEXT,
                    touched REAL, PRIMARY KEY(run,lane));
            """)
            with self.transaction() as db:
                self._reap(db)
                for path in self.paths:
                    conflict = db.execute(
                        "SELECT run FROM cases WHERE path=? AND (exclusive=1 OR ?=1)",
                        (path, int(exclusive))).fetchone()
                    if conflict:
                        raise PipelineError(f"Case is busy with an incompatible run: {path} "
                                            f"(run {conflict['run']}). No request or clear was started.")
                db.execute("INSERT INTO runs VALUES (?,?)", (self.id, time.time()))
                db.executemany("INSERT INTO cases VALUES (?,?,?)",
                               [(p, self.id, int(exclusive)) for p in self.paths])
                db.executemany("INSERT OR IGNORE INTO versions VALUES (?,0)",
                               [(p,) for p in self.paths])
        except BaseException as exc:
            if self.db is not None:
                self.db.close()
            self.life.close()
            if isinstance(exc, sqlite3.Error):
                raise PipelineError(f"Could not initialize runtime coordination: {exc}") from exc
            raise
        self.thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.thread.start()

    @contextlib.contextmanager
    def transaction(self):
        with self.mutex:
            try:
                self.db.execute("BEGIN IMMEDIATE")
                yield self.db
                self.db.execute("COMMIT")
            except BaseException as exc:
                if self.db.in_transaction:
                    self.db.execute("ROLLBACK")
                if isinstance(exc, sqlite3.Error):
                    raise PipelineError(f"Runtime coordination failed: {exc}") from exc
                raise

    def _forget(self, db, run):
        for table in ("cases", "subscribers", "users", "waiters", "demands"):
            db.execute(f"DELETE FROM {table} WHERE run=?", (run,))
        db.execute("DELETE FROM runs WHERE id=?", (run,))
        db.execute("DELETE FROM tasks WHERE owner=? AND state='running'", (run,))
        db.execute("DELETE FROM tasks WHERE NOT EXISTS "
                   "(SELECT 1 FROM subscribers s WHERE s.key=tasks.key)")

    def _reap(self, db):
        for row in db.execute("SELECT id FROM runs").fetchall():
            if row['id'] == self.id:
                continue
            probe = FileLock(RUNTIME_DIR / "runs" / (row['id'] + ".lock"))
            try:
                if probe.acquire(False):
                    self._forget(db, row['id'])
            finally:
                probe.close()
        # A dead process may still have a request executing at the provider.
        db.execute("DELETE FROM permits WHERE deadline<=? AND run NOT IN (SELECT id FROM runs)",
                   (time.time(),))

    def _heartbeat(self):
        while not self.stop.wait(5):
            try:
                with self.transaction() as db:
                    db.execute("UPDATE runs SET heartbeat=? WHERE id=?", (time.time(), self.id))
                    self._reap(db)
            except Exception as exc:
                self.heartbeat_error = str(exc)
                return

    def check(self):
        if self.heartbeat_error:
            raise PipelineError(f"Runtime coordination failed: {self.heartbeat_error}")

    def versions(self):
        with self.mutex:
            return {row['path']: row['version'] for row in self.db.execute(
                "SELECT v.path,v.version FROM versions v JOIN cases c ON c.path=v.path WHERE c.run=?",
                (self.id,))}

    def changed(self, path):
        with self.transaction() as db:
            db.execute("UPDATE versions SET version=version+1 WHERE path=?", (path_key(path),))

    def claim(self, key):
        """Caller holds the case lock and has just checked the authoritative JSON."""
        self.check()
        with self.transaction() as db:
            db.execute("INSERT OR IGNORE INTO subscribers VALUES (?,?)", (key, self.id))
            row = db.execute("SELECT * FROM tasks WHERE key=?", (key,)).fetchone()
            if row and row['state'] == 'failed':
                return 'failed', row['error']
            if row and row['state'] == 'running':
                return ('owned', row['token']) if row['owner'] == self.id else ('waiting', None)
            token = uuid.uuid4().hex
            db.execute("INSERT OR REPLACE INTO tasks VALUES (?,?,?,'running',NULL)",
                       (key, self.id, token))
            return 'owned', token

    def owns(self, key, token):
        with self.mutex:
            return self.db.execute(
                "SELECT 1 FROM tasks WHERE key=? AND owner=? AND token=? AND state='running'",
                (key, self.id, token)).fetchone() is not None

    def finish(self, key, token, error=None):
        with self.transaction() as db:
            cursor = db.execute(
                "UPDATE tasks SET state=?,error=? WHERE key=? AND owner=? AND token=? AND state='running'",
                ('failed' if error else 'done', error, key, self.id, token))
            if cursor.rowcount != 1:
                raise PipelineError("Task ownership changed before commit acknowledgement")

    def configure(self, resources):
        """resources: key -> (capacity, rpm); capacity=0 is an RPM-only resource."""
        with self.transaction() as db:
            self._reap(db)
            for key, (capacity, rpm) in resources.items():
                row = db.execute("SELECT * FROM resources WHERE key=?", (key,)).fetchone()
                used = db.execute("SELECT 1 FROM users WHERE resource=? UNION ALL "
                                  "SELECT 1 FROM permits WHERE resource=? LIMIT 1", (key, key)).fetchone()
                if row and used and (row['capacity'] != capacity or row['rpm'] != rpm):
                    raise PipelineError(f"Shared limit configuration conflicts for {key}: "
                                        f"active concurrency={row['capacity']}, rpm={row['rpm']}; "
                                        f"requested concurrency={capacity}, rpm={rpm}.")
                if not row or not used:
                    db.execute("INSERT OR REPLACE INTO resources VALUES (?,?,?,0,0)",
                               (key, capacity, rpm))
                db.execute("INSERT OR IGNORE INTO users VALUES (?,?)", (key, self.id))

    def reserve(self, keys, timeout, *, lane='default', fairness_key=None):
        now = time.time()
        with self.transaction() as db:
            db.execute("INSERT INTO demands VALUES (?,?,?,?) ON CONFLICT(run,lane) "
                       "DO UPDATE SET resources=excluded.resources,touched=excluded.touched",
                       (self.id, lane, json.dumps(keys), now))
            for key in keys:
                db.execute("INSERT INTO waiters VALUES (?,?,?,0) ON CONFLICT(resource,run) "
                           "DO UPDATE SET touched=excluded.touched", (key, self.id, now))
            limits = {r['key']: r for r in db.execute(
                "SELECT r.*, (SELECT COUNT(*) FROM permits p WHERE p.resource=r.key) AS active FROM resources r")}

            def available(resource_keys):
                return all((not limits[k]['capacity'] or limits[k]['active'] < limits[k]['capacity'])
                           and max(limits[k]['next_start'], limits[k]['cooldown']) <= now
                           for k in resource_keys)

            if not available(keys):
                return None
            # An older QA waiter blocked by its own RPM must not hold up a ready
            # Judge on their shared OpenRouter resource. Evaluate the whole demand.
            eligible = {}
            for demand in db.execute("SELECT * FROM demands WHERE touched>?", (now - 2,)):
                required = json.loads(demand['resources'])
                if available(required):
                    for key in required:
                        eligible.setdefault(key, set()).add(demand['run'])
            # One service root arbitrates the whole atomic bundle. Independently
            # ordering every sublimit could create a cyclic wait (QA vs Judge).
            root = fairness_key or keys[0]
            first = next((r for r in db.execute(
                "SELECT run FROM waiters WHERE resource=? AND touched>? ORDER BY last_grant,run",
                (root, now - 2)) if r['run'] in eligible.get(root, set())), None)
            if first and first['run'] != self.id:
                return None
            token = uuid.uuid4().hex
            for key in keys:
                row = db.execute("SELECT rpm FROM resources WHERE key=?", (key,)).fetchone()
                db.execute("UPDATE resources SET next_start=? WHERE key=?",
                           (now + 60 / row['rpm'] if row['rpm'] else now, key))
                db.execute("UPDATE waiters SET last_grant=? WHERE resource=? AND run=?", (now, key, self.id))
                db.execute("INSERT INTO permits VALUES (?,?,?,?)", (token, key, self.id, now + timeout))
            db.execute("UPDATE demands SET touched=0 WHERE run=? AND lane=?", (self.id, lane))
            return token

    def release(self, token, *, cooldown_keys=(), delay=0):
        with self.transaction() as db:
            db.execute("DELETE FROM permits WHERE token=? AND run=?", (token, self.id))
            for key in cooldown_keys:
                db.execute("UPDATE resources SET cooldown=MAX(cooldown,?) WHERE key=?",
                           (time.time() + delay, key))

    def withdraw(self, keys):
        with self.transaction() as db:
            for key in keys:
                db.execute("UPDATE waiters SET touched=0 WHERE resource=? AND run=?", (key, self.id))

    def occupancy(self):
        with self.mutex:
            rows = self.db.execute("SELECT r.key,r.capacity,r.rpm,r.next_start,r.cooldown,"
                                   "(SELECT COUNT(*) FROM permits p WHERE p.resource=r.key) AS active "
                                   "FROM resources r JOIN users u ON u.resource=r.key WHERE u.run=?", (self.id,))
            return [dict(r) for r in rows]

    def snapshot(self, paths, workers=4):
        with contextlib.ExitStack() as stack:
            for path in sorted(paths, key=path_key):
                stack.enter_context(case_lock(path))
            with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
                return list(zip(paths, pool.map(load_case, paths)))

    def commit(self, path, key, token, merge):
        with case_lock(path):
            if not self.owns(key, token):
                raise PipelineError("Refusing a result from an expired task owner")
            case = load_case(path)
            merge(case)
            atomic_write_json(path, case)
            self.changed(path)
            self.finish(key, token)
            return case

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join()
        try:
            with self.transaction() as db:
                self._forget(db, self.id)
        finally:
            self.db.close()
            self.life.close()
