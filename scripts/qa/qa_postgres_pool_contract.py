from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import operational_db


class FakeConnection:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FakePool:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection_value = connection
        self.checkouts = 0

    @contextmanager
    def connection(self, timeout: float):
        assert timeout == 10.0
        self.checkouts += 1
        yield self.connection_value


def configure_postgres_environment() -> None:
    os.environ["VPO_OPERATIONAL_DB_DRIVER"] = "postgres"
    os.environ["VPO_OPERATIONAL_DB_PASSWORD"] = "test-only"
    os.environ["VPO_POSTGRES_CONNECT_MODE"] = "local_proxy"
    os.environ["VPO_POSTGRES_POOL_MIN_SIZE"] = "1"
    os.environ["VPO_POSTGRES_POOL_MAX_SIZE"] = "4"
    os.environ["VPO_POSTGRES_POOL_TIMEOUT_SECONDS"] = "10"
    os.environ["VPO_POSTGRES_POOL_MAX_WAITING"] = "16"


def main() -> None:
    configure_postgres_environment()
    settings = operational_db.operational_db_settings()
    assert settings.pool_min_size == 1
    assert settings.pool_max_size == 4
    assert settings.pool_max_size * 4 <= 16

    connection = FakeConnection()
    pool = FakePool(connection)
    original_open = operational_db.open_operational_db_pool
    operational_db.open_operational_db_pool = lambda **_: pool
    try:
        with operational_db.operational_connect() as first:
            assert first is connection
        with operational_db.operational_connect() as second:
            assert second is connection
        assert pool.checkouts == 2
        assert connection.commits == 2
        assert connection.rollbacks == 0

        try:
            with operational_db.operational_connect():
                raise RuntimeError("expected")
        except RuntimeError as exc:
            assert str(exc) == "expected"
        else:
            raise AssertionError("operational_connect did not propagate the error")
        assert connection.rollbacks == 1
    finally:
        operational_db.open_operational_db_pool = original_open

    os.environ["VPO_POSTGRES_POOL_MIN_SIZE"] = "5"
    os.environ["VPO_POSTGRES_POOL_MAX_SIZE"] = "4"
    try:
        operational_db.operational_db_settings()
    except operational_db.OperationalDbConfigError:
        pass
    else:
        raise AssertionError("invalid pool limits were accepted")

    print("PostgreSQL pool contract OK")


if __name__ == "__main__":
    main()
