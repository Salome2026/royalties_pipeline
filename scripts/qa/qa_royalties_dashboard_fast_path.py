from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import polars as pl

from app import vpo_corp_api as api
from scripts.lib import catalog_report_filter
from scripts.lib.text_search import contains_prepared_search_expr, contains_search_expr


def dashboard_fixture(path: Path) -> None:
    rows = [
        ("FUGA", "a", "2026-01", "2025-12", 100.0, 10.0, 2, "Flor", "Tema A", "YouTube", "video", "master", "AR", "stream", "L1", "flor tema a"),
        ("FUGA", "a", "2026-02", "2026-01", 50.0, 5.0, 1, "Flor", "Tema B", "Spotify", "audio", "master", "AR", "stream", "L1", "flor tema b"),
        ("ADA", "b", "2026-02", "2026-02", 25.0, 3.0, 3, "Ana", "Tema C", "YouTube", "video", "ugc", "US", "stream", "L2", "ana tema c"),
    ]
    columns = [
        "source", "account", "statement_period", "transaction_month", "amount_usd",
        "units", "raw_rows", "artist", "title", "dsp", "monetization_normalized",
        "content_origin_normalized", "territory", "sale_type", "label", "search_text",
    ]
    pl.DataFrame(rows, schema=columns, orient="row").write_parquet(path)


def check_dashboard(path: Path) -> None:
    policy = {"report_personalization": {}, "policy_version": "qa", "updated_at": None}
    with (
        patch.object(api, "VPO_LOCAL_MARTS_DIR", None),
        patch.object(api, "ensure_marts", return_value={api.ROYALTIES_DASHBOARD_SUMMARY_FILE: path}),
        patch.object(api, "load_distributor_policy_document", return_value=policy),
        patch.object(api, "apply_report_net_personalization", side_effect=lambda frame, *args, **kwargs: frame),
    ):
        result = api.royalties_dashboard(period_mode="all", x_vpo_api_key=api.VPO_API_KEY)
        assert result["totals"]["amount_usd"] == 175.0
        assert result["totals"]["rows"] == 6
        assert result["period_months"] == ["2026-01", "2026-02"]
        assert result["monthly"] == [
            {"month": "2026-01", "amount_usd": 100.0, "units": 10.0, "rows": 2},
            {"month": "2026-02", "amount_usd": 75.0, "units": 8.0, "rows": 4},
        ]
        assert result["youtube"]["totals"]["amount_usd"] == 125.0
        youtube_sources = {row["name"]: row for row in result["youtube"]["monetization"]}
        assert youtube_sources["video"]["percentage"] == 100.0
        assert result["rankings"]["sources"][0]["percentage"] == round(150 / 175 * 100, 2)

        by_source = api.royalties_dashboard(source="ADA", period_mode="all", x_vpo_api_key=api.VPO_API_KEY)
        assert by_source["totals"]["amount_usd"] == 25.0
        assert by_source["totals"]["rows"] == 3
        assert by_source["youtube"]["totals"]["amount_usd"] == 25.0

        by_keyword = api.royalties_dashboard(keyword="Flor Tema", period_mode="all", x_vpo_api_key=api.VPO_API_KEY)
        assert by_keyword["totals"]["amount_usd"] == 150.0
        assert by_keyword["totals"]["rows"] == 3

        by_transaction = api.royalties_dashboard(
            start_month="2026-02", end_month="2026-02", period_basis="transaction_month",
            x_vpo_api_key=api.VPO_API_KEY,
        )
        assert by_transaction["totals"]["amount_usd"] == 25.0

        empty = api.royalties_dashboard(keyword="no existe", x_vpo_api_key=api.VPO_API_KEY)
        assert empty["totals"]["amount_usd"] == 0.0
        assert empty["period_months"] == []

        with patch.object(api, "apply_report_net_personalization", side_effect=AssertionError("cache miss")):
            repeated = api.royalties_dashboard(period_mode="all", x_vpo_api_key=api.VPO_API_KEY)
            assert repeated == result

    adjusted_policy = {
        "report_personalization": {"enabled": True}, "policy_version": "qa-adjusted",
        "updated_at": None,
        "entries": [{"source": "fuga", "account": "a", "report_net_adjustment_pct": 10}],
    }
    with (
        patch.object(api, "VPO_LOCAL_MARTS_DIR", None),
        patch.object(api, "ensure_marts", return_value={api.ROYALTIES_DASHBOARD_SUMMARY_FILE: path}),
        patch.object(api, "load_distributor_policy_document", return_value=adjusted_policy),
        patch.object(catalog_report_filter, "load_distributor_policy_document", side_effect=AssertionError("duplicate policy read")),
    ):
        adjusted = api.royalties_dashboard(period_mode="all", x_vpo_api_key=api.VPO_API_KEY)
        assert adjusted["totals"]["amount_usd"] == 160.0


def check_prepared_search() -> None:
    samples = pl.DataFrame({
        "search_text": [
            "flor alvarez tema a", "flor_alvarez tema b", "flor-alvarez tema c",
            "flor álvarez tema d", "flo-r alv-arez tema e", "ardl12600043",
            "ar-dl1 2600043", "ana tema c", None,
        ]
    })
    for query in ["flor", "alvarez", "flor alvarez", "AR-DL12600043", "ana", "tema-c"]:
        old = samples.filter(contains_search_expr(pl.col("search_text"), query))["search_text"].to_list()
        prepared = samples.filter(contains_prepared_search_expr(pl.col("search_text"), query))["search_text"].to_list()
        assert prepared == old, (query, old, prepared)


class FakeBlob:
    def __init__(self) -> None:
        self.name = "marts/royalties_dashboard_summary.parquet"
        self.generation = 1
        self.downloads = 0

    def reload(self, client=None) -> None:
        return None

    def download_to_filename(self, filename: str, client=None, if_generation_match=None) -> None:
        assert if_generation_match == self.generation
        self.downloads += 1
        Path(filename).write_bytes(f"generation-{self.generation}".encode("ascii"))


class FakeClient:
    def __init__(self, blob: FakeBlob) -> None:
        self.blob_value = blob

    def bucket(self, name: str):
        return self

    def blob(self, name: str) -> FakeBlob:
        return self.blob_value


def check_generation_cache(cache_dir: Path) -> None:
    blob = FakeBlob()
    filename = api.ROYALTIES_DASHBOARD_SUMMARY_FILE
    with (
        patch.object(api, "VPO_LOCAL_MARTS_DIR", None),
        patch.object(api, "VPO_API_CACHE_DIR", cache_dir),
        patch.object(api, "GCS_BUCKET", "qa-bucket"),
        patch.object(api, "gcs_client", return_value=FakeClient(blob)),
    ):
        first = api.ensure_marts(filenames=[filename], verify_generation=True)[filename]
        assert first.read_bytes() == b"generation-1"
        api.ensure_marts(filenames=[filename], verify_generation=True)
        assert blob.downloads == 1

        blob.generation = 2
        api.ensure_marts(filenames=[filename], verify_generation=True)
        assert first.read_bytes() == b"generation-2"
        assert blob.downloads == 2
        assert first.with_name(f"{filename}.generation").read_text(encoding="ascii") == "2"


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_dir:
        root = Path(temporary_dir)
        fixture = root / "dashboard.parquet"
        dashboard_fixture(fixture)
        check_dashboard(fixture)
        check_prepared_search()
        check_generation_cache(root / "cache")
    print("OK: dashboard totals, filters, YouTube percentages and GCS generation cache")


if __name__ == "__main__":
    main()
