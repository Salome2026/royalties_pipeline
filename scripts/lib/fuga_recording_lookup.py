"""Conservative release/video checks; no credentials or request URLs in evidence."""
import os
import re
import unicodedata
from datetime import date

import requests


def normalized(value):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().lower()).split())


class RecordingLookup:
    def __init__(self):
        self.token = None
        self.cache = {}
        self.unavailable = False

    def verify(self, code, title, artists, video_ids):
        key = (code, tuple(video_ids))
        if key in self.cache:
            return self.cache[key]
        result = None
        youtube_key = os.getenv("YOUTUBE_API_KEY")
        client, secret = os.getenv("SPOTIFY_CLIENT_ID"), os.getenv("SPOTIFY_CLIENT_SECRET")
        if self.unavailable or not all([youtube_key, client, secret]):
            return None
        try:
            if not self.token:
                response = requests.post("https://accounts.spotify.com/api/token", auth=(client, secret), data={"grant_type": "client_credentials"}, timeout=15)
                response.raise_for_status()
                self.token = response.json()["access_token"]
            response = requests.get("https://api.spotify.com/v1/search", headers={"Authorization": "Bearer " + self.token}, params={"q": "isrc:" + code, "type": "track", "limit": 10}, timeout=15)
            response.raise_for_status()
            tracks = [track for track in response.json().get("tracks", {}).get("items", []) if track.get("external_ids", {}).get("isrc", "").upper() == code and normalized(track.get("name")) == normalized(title) and {normalized(a["name"]) for a in track.get("artists", [])} & {normalized(a) for a in artists}]
            # Several editions are acceptable only when duration and release date agree.
            signatures = {(track["duration_ms"], track["album"].get("release_date")) for track in tracks}
            if len(signatures) != 1:
                return None
            track = tracks[0]
            release_date = date.fromisoformat(track["album"]["release_date"])
            response = requests.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "snippet,contentDetails", "id": ",".join(video_ids), "key": youtube_key}, timeout=15)
            response.raise_for_status()
            items = response.json().get("items", [])
            if {item["id"] for item in items} != set(video_ids):
                return None
            for item in items:
                duration = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", item["contentDetails"]["duration"])
                if not duration:
                    return None
                seconds = sum(int(part or 0) * multiplier for part, multiplier in zip(duration.groups(), [3600, 60, 1]))
                if abs(seconds - track["duration_ms"] / 1000) > 7 or abs((date.fromisoformat(item["snippet"]["publishedAt"][:10]) - release_date).days) > 2:
                    return None
                video_title = normalized(item["snippet"]["title"])
                if normalized(title) not in video_title:
                    return None
                for version in ["remix", "live", "vivo", "acustico", "sped up", "slowed", "instrumental"]:
                    if (version in video_title) != (version in normalized(title)):
                        return None
            result = {"basis": "exact_isrc_release_and_official_video_metadata", "release_url": track.get("external_urls", {}).get("spotify"), "release_date": release_date.isoformat(), "duration_ms": track["duration_ms"], "videos": [{"id": item["id"], "title": item["snippet"]["title"], "published_at": item["snippet"]["publishedAt"], "duration": item["contentDetails"]["duration"]} for item in items], "audio_fingerprint_comparison_performed": False}
        except requests.RequestException:
            # Stop provider requests on failures/quota limits. A later ingestion retries.
            self.unavailable = True
        except (ValueError, KeyError, TypeError):
            # An incomplete release is not a provider outage for other recordings.
            result = None
        self.cache[key] = result
        return result
