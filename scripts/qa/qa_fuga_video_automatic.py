import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import polars as pl
from polars.testing import assert_frame_equal
from lib.fuga_video_automatic import resolve_extended, apply_automatic_extended
from lib.fuga_recording_lookup import RecordingLookup


class AutomaticVideoTests(unittest.TestCase):
    def catalog(self):
        return pl.DataFrame([
            {"catalog_key": "ISRC:ARAAA2600001", "video_ids": "", "track_title": "Nueva cancion", "artist_statement": "Artista", "amount_usd": 100., "units": 20., "song_level_rows": 3},
            {"catalog_key": "VIDEO:newVideo123", "video_ids": "newVideo123", "track_title": "Nueva cancion", "artist_statement": "Artista", "amount_usd": 12., "units": 2., "song_level_rows": 1}])

    def metadata(self, principal="ARAAA2600001"):
        return pl.DataFrame([{"YouTube Asset ISRC": "ARBBB2600002", "YouTube Video ID": "newVideo123", "principal_asset_isrc": principal, "source_file": "209912-youtube_extended.csv", "economic_role": "supplementary_metadata_only", "YouTube Asset Title": "Nueva cancion", "YouTube Asset Artists": "Artista"}])

    def resolve(self, metadata=None, lookup=None):
        return resolve_extended(self.catalog(), metadata if metadata is not None else self.metadata(), {"version": 1, "entries": [], "aliases": []}, lookup=lookup)

    def test_future_unknown_isrc_confirms_native_bridge_without_merging_financial_rows(self):
        catalog, outcomes = self.resolve()
        self.assertEqual(outcomes[0]["audio_relationship_status"], "confirmed")
        self.assertEqual(catalog.height, 2)
        for field in ["catalog_key", "amount_usd", "units", "song_level_rows"]:
            self.assertEqual(catalog[field].to_list(), self.catalog()[field].to_list())
        self.assertEqual(outcomes[0]["catalog_key"], "VIDEO:newVideo123")

    def test_ambiguous_native_bridge_is_closed_without_approval(self):
        _, outcomes = self.resolve(pl.concat([self.metadata(), self.metadata("ARCCC2600003")]))
        self.assertEqual(outcomes[0]["audio_relationship_status"], "not_linked")
        self.assertTrue(outcomes[0]["review_closed"])
        self.assertFalse(outcomes[0]["requires_user_confirmation"])

    def test_missing_audio_never_creates_a_song(self):
        result, outcomes = self.resolve(self.metadata("ARCCC2600003"))
        self.assertEqual(result.height, 2)
        self.assertIsNone(outcomes[0]["confirmed_audio_isrc"])

    def test_title_match_requires_external_evidence(self):
        _, outcomes = self.resolve(self.metadata(None))
        self.assertEqual(outcomes[0]["audio_relationship_status"], "not_linked")

    def test_external_release_match_automatically_confirms(self):
        lookup = Mock()
        lookup.verify.return_value = {"basis": "exact_isrc_release_and_official_video_metadata"}
        result, outcomes = self.resolve(self.metadata(None), lookup)
        self.assertEqual(outcomes[0]["confirmed_audio_isrc"], "ARAAA2600001")
        lookup.verify.assert_called_once()
        self.assertEqual(result["amount_usd"].sum(), 112.)

    def test_collaborations_and_official_video_decoration_match_without_fuzzy_aliases(self):
        lookup = Mock()
        lookup.verify.return_value = {"basis": "exact_isrc_release_and_official_video_metadata"}
        catalog = self.catalog().with_columns(pl.lit("Artista and Invitado").alias("artist_statement"))
        metadata = self.metadata(None).with_columns(pl.lit("Artista; Invitado").alias("YouTube Asset Artists"), pl.lit("Nueva cancion - Artista, Invitado (Video Oficial)").alias("YouTube Asset Title"))
        _, outcomes = resolve_extended(catalog, metadata, {"version": 1, "entries": [], "aliases": []}, lookup)
        self.assertEqual(outcomes[0]["audio_relationship_status"], "confirmed")
        lookup.verify.assert_called_once_with("ARAAA2600001", "Nueva cancion", ["Artista", "Invitado"], ["newVideo123"])

    def test_provider_failure_closes_without_user_confirmation(self):
        lookup = Mock()
        lookup.verify.return_value = None
        _, outcomes = self.resolve(self.metadata(None), lookup)
        self.assertFalse(outcomes[0]["requires_user_confirmation"])

    def test_repeated_processing_is_idempotent(self):
        once, _ = self.resolve()
        twice, _ = resolve_extended(once, self.metadata(), {"version": 1, "entries": [], "aliases": []})
        assert_frame_equal(once, twice)

    def test_normal_disk_workflow_persists_evidence_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "warehouse/registry").mkdir(parents=True)
            (root / "warehouse/marts").mkdir()
            (root / "warehouse/registry/fuga_video_catalog_decisions.json").write_text(json.dumps({"version": 1, "entries": [], "aliases": []}))
            metadata_path = root / "warehouse/marts/fuga_youtube_extended_metadata.parquet"
            self.metadata().write_parquet(metadata_path)
            once = apply_automatic_extended(self.catalog(), root)
            evidence = pl.read_parquet(metadata_path)["automatic_resolution_json"][0]
            self.assertEqual(json.loads(evidence)[0]["confirmed_audio_isrc"], "ARAAA2600001")
            assert_frame_equal(once, apply_automatic_extended(once, root))

    def test_multiple_catalog_matches_are_not_confirmed(self):
        catalog = pl.concat([self.catalog(), self.catalog().head(1).with_columns(pl.lit("ISRC:ARDDD2600004").alias("catalog_key"), pl.lit("newVideo123").alias("video_ids"))])
        _, outcomes = resolve_extended(catalog, self.metadata(), {"version": 1, "entries": [], "aliases": []})
        self.assertEqual(outcomes[0]["audio_relationship_status"], "not_linked")
        self.assertIsNone(outcomes[0]["catalog_key"])

    def test_http_quota_failure_does_not_raise_or_expose_credentials(self):
        import requests
        with patch.dict("os.environ", {"YOUTUBE_API_KEY": "private", "SPOTIFY_CLIENT_ID": "private", "SPOTIFY_CLIENT_SECRET": "private"}), patch("lib.fuga_recording_lookup.requests.post", side_effect=requests.RequestException("private")):
            lookup = RecordingLookup()
            self.assertIsNone(lookup.verify("ARAAA2600001", "Nueva cancion", ["Artista"], ["newVideo123"]))
            self.assertTrue(lookup.unavailable)

    def provider_check(self, seconds=180, video_title="Artista - Nueva cancion (Video Oficial)", code="ARAAA2600001"):
        token = Mock(); token.json.return_value = {"access_token": "private"}
        release = Mock(); release.json.return_value = {"tracks": {"items": [{"external_ids": {"isrc": code}, "name": "Nueva cancion", "artists": [{"name": "Artista"}], "duration_ms": 180000, "album": {"release_date": "2026-11-01"}, "external_urls": {"spotify": "https://open.spotify.com/track/example"}}]}}
        video = Mock(); video.json.return_value = {"items": [{"id": "newVideo123", "snippet": {"title": video_title, "publishedAt": "2026-11-02T00:00:00Z"}, "contentDetails": {"duration": f"PT{seconds}S"}}]}
        with patch.dict("os.environ", {"YOUTUBE_API_KEY": "private", "SPOTIFY_CLIENT_ID": "private", "SPOTIFY_CLIENT_SECRET": "private"}), patch("lib.fuga_recording_lookup.requests.post", return_value=token), patch("lib.fuga_recording_lookup.requests.get", side_effect=[release, video]):
            return RecordingLookup().verify("ARAAA2600001", "Nueva cancion", ["Artista"], ["newVideo123"])

    def test_provider_confirms_coherent_release(self):
        self.assertEqual(self.provider_check()["basis"], "exact_isrc_release_and_official_video_metadata")

    def test_provider_rejects_duration_discrepancy(self):
        self.assertIsNone(self.provider_check(seconds=202))

    def test_provider_rejects_live_version(self):
        self.assertIsNone(self.provider_check(video_title="Artista - Nueva cancion EN VIVO"))

    def test_provider_rejects_other_isrc_despite_same_title(self):
        self.assertIsNone(self.provider_check(code="ARCCC2600003"))


if __name__ == "__main__":
    unittest.main()
