from __future__ import annotations

import sys
from pathlib import Path

from fastapi.responses import Response


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vpo_corp_api import build_health_payload


def main() -> None:
    import app.vpo_corp_api as api

    original_db = api.operational_db_healthcheck
    original_local = api.VPO_LOCAL_MARTS_DIR
    original_cache = api.MART_RELEASE_CACHE
    original_cache_config = api.MART_RELEASE_CACHE_CONFIG
    original_ensure = api.ensure_marts

    class FakeCache:
        def __init__(self, *, fallback: bool = False, error: str | None = None) -> None:
            self.fallback = fallback
            self.error = error

        def status(self) -> dict:
            return {
                "active_release_id": "release-test",
                "active_cache_key": "release-test-generation",
                "source_mode": "manifest",
                "manifest_generation": "123",
                "activated_at": "2026-09-16T00:00:00",
                "using_stale_fallback": self.fallback,
                "last_error": self.error,
                "auxiliary_generations": {},
            }

    try:
        api.VPO_LOCAL_MARTS_DIR = None
        api.operational_db_healthcheck = lambda: {"status": "ok"}
        api.MART_RELEASE_CACHE = FakeCache()
        api.MART_RELEASE_CACHE_CONFIG = (
            str(api.VPO_API_CACHE_DIR.resolve()),
            api.GCS_BUCKET,
            api.GCS_PREFIX,
        )
        api.ensure_marts = lambda **_: {}
        assert build_health_payload()["status"] == "ok"

        ready_response = Response()
        assert api.readiness(ready_response)["status"] == "ok"
        assert ready_response.status_code == 200

        api.MART_RELEASE_CACHE = FakeCache(fallback=True)
        fallback = build_health_payload()
        assert fallback["status"] == "degraded"
        assert "mart_cache_fallback" in fallback["issues"]

        api.MART_RELEASE_CACHE = FakeCache(error="download failed")
        cache_error = build_health_payload()
        assert cache_error["status"] == "degraded"
        assert "mart_cache_error" in cache_error["issues"]

        api.MART_RELEASE_CACHE = FakeCache()
        api.operational_db_healthcheck = lambda: {"status": "error"}
        database_error = build_health_payload()
        assert database_error["status"] == "degraded"
        assert "operational_db" in database_error["issues"]

        degraded_response = Response()
        assert api.readiness(degraded_response)["status"] == "degraded"
        assert degraded_response.status_code == 503
    finally:
        api.operational_db_healthcheck = original_db
        api.VPO_LOCAL_MARTS_DIR = original_local
        api.MART_RELEASE_CACHE = original_cache
        api.MART_RELEASE_CACHE_CONFIG = original_cache_config
        api.ensure_marts = original_ensure

    print("OPS health contract OK")


if __name__ == "__main__":
    main()
