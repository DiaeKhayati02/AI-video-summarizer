import os
import re
from urllib.parse import parse_qs, urlparse

import requests
import urllib3
from youtube_transcript_api import NoTranscriptFound, RequestBlocked, TranscriptsDisabled, YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class TranscriptUnavailableError(Exception):
    """Raised when a video has no transcript we can fetch."""


class TranscriptFetchBlockedError(Exception):
    """Raised when YouTube is blocking this server's IP, not when a video lacks captions."""


def _build_transcript_api() -> YouTubeTranscriptApi:
    # A residential/rotating proxy is the only reliable workaround for YouTube
    # blocking transcript requests from cloud-host IPs. Unset both env vars
    # locally, where an unproxied residential IP already works fine.

    # TRANSCRIPT_PROXY_URL: a generic "http://user:pass@host:port" proxy, e.g.
    # a scraping API's proxy-mode endpoint (ScraperAPI etc.). These typically
    # intercept TLS, so certificate verification has to be disabled on the
    # session too -- that's an inherent tradeoff of this kind of proxy, not a
    # bug here.
    proxy_url = os.environ.get("TRANSCRIPT_PROXY_URL")
    if proxy_url:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        session = requests.Session()
        session.verify = False
        return YouTubeTranscriptApi(
            proxy_config=GenericProxyConfig(http_url=proxy_url, https_url=proxy_url),
            http_client=session,
        )

    # WEBSHARE_PROXY_USERNAME/PASSWORD: specifically a *residential* Webshare
    # plan -- their free/datacenter proxies get blocked the same way an
    # unproxied cloud host does.
    username = os.environ.get("WEBSHARE_PROXY_USERNAME")
    password = os.environ.get("WEBSHARE_PROXY_PASSWORD")
    if username and password:
        return YouTubeTranscriptApi(
            proxy_config=WebshareProxyConfig(proxy_username=username, proxy_password=password)
        )

    return YouTubeTranscriptApi()


def extract_video_id(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")

    video_id = None
    if host == "youtu.be":
        video_id = parsed.path.lstrip("/")
    elif host == "youtube.com":
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.path.startswith("/embed/"):
            video_id = parsed.path.removeprefix("/embed/")

    if not video_id or not VIDEO_ID_RE.match(video_id):
        raise ValueError(f"Could not extract a YouTube video ID from URL: {url}")
    return video_id


def fetch_transcript(video_id: str) -> tuple[str, int]:
    """Returns (full transcript text, approximate video duration in seconds)."""
    try:
        snippets = list(_build_transcript_api().fetch(video_id))
    except RequestBlocked as exc:
        raise TranscriptFetchBlockedError(
            "YouTube is blocking transcript requests from this server's IP address. "
            "This happens to almost all cloud-hosted backends and isn't specific to this video."
        ) from exc
    except (TranscriptsDisabled, NoTranscriptFound) as exc:
        raise TranscriptUnavailableError("This video has no available transcript.") from exc

    text = " ".join(snippet.text for snippet in snippets)
    duration_seconds = int(snippets[-1].start + snippets[-1].duration) if snippets else 0
    return text, duration_seconds


def fetch_oembed_metadata(url: str) -> dict:
    """Best-effort title/channel lookup via YouTube's public oEmbed endpoint (no API key needed)."""
    try:
        response = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        return {"title": data.get("title"), "channel_name": data.get("author_name")}
    except requests.RequestException:
        return {"title": None, "channel_name": None}
