"""Display existing report evidence without changing economic identities."""
import re


YOUTUBE_CHANNEL_LABEL = "YouTube · video/canal"


def youtube_video_url(code: object, code_type: object) -> str | None:
    if not isinstance(code, str) or not isinstance(code_type, str) or code_type != "Video ID":
        return None
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", code):
        return None
    return f"https://www.youtube.com/watch?v={code}"
