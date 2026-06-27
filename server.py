# -*- coding: utf-8 -*-
"""
Unsplash MCP Server

An MCP server for fetching photos from Unsplash with proper attribution.
Runs as an HTTP proxy — users connect via URL, no API key setup required.
"""

import os
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, List, Dict, Union

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request
from starlette.requests import Request
from starlette.responses import JSONResponse

load_dotenv()

UNSPLASH_API_BASE = "https://api.unsplash.com"

# Rate limiting: max requests per IP per hour
RATE_LIMIT = 30
RATE_WINDOW = 3600  # seconds

# In-memory store: {ip: [timestamp, ...]}
_rate_store: Dict[str, list] = defaultdict(list)


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    window_start = now - RATE_WINDOW
    timestamps = [t for t in _rate_store[ip] if t > window_start]
    if len(timestamps) >= RATE_LIMIT:
        raise ValueError(
            f"Rate limit reached ({RATE_LIMIT} requests/hour per IP). Please try again later."
        )
    timestamps.append(now)
    _rate_store[ip] = timestamps


def _enforce_rate_limit() -> None:
    """Resolve the caller's IP from the HTTP request and enforce the limit.

    No-op when not running under the HTTP transport (e.g. stdio/local),
    where there is no request to rate-limit.
    """
    try:
        request = get_http_request()
    except RuntimeError:
        return
    client = request.headers.get("x-forwarded-for")
    if client:
        ip = client.split(",")[0].strip()
    elif request.client:
        ip = request.client.host
    else:
        ip = "unknown"
    _check_rate_limit(ip)


mcp = FastMCP(
    "Unsplash MCP Server",
    instructions=(
        "Provides search and retrieval of Unsplash photos via the Unsplash API "
        "(https://unsplash.com/documentation). Each photo result includes "
        "attribution_text and attribution_html, which Unsplash's API guidelines "
        "require to be shown alongside the image. The track_download tool records a "
        "download event with Unsplash, which their guidelines require when a user "
        "saves or downloads a photo at full resolution."
    ),
)


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    """Lightweight health check for deployment platforms (Railway, etc.)."""
    return JSONResponse({"status": "ok", "server": "unsplash-mcp"})


@dataclass
class UnsplashPhoto:
    id: str
    description: Optional[str]
    alt_description: Optional[str]
    urls: Dict[str, str]
    width: int
    height: int
    color: str
    blur_hash: Optional[str]
    photographer_name: str
    photographer_username: str
    photographer_url: str
    photo_url: str
    attribution_text: str
    attribution_html: str


def _get_access_key() -> str:
    access_key = os.getenv("UNSPLASH_ACCESS_KEY")
    if not access_key:
        raise ValueError(
            "Server misconfigured: missing UNSPLASH_ACCESS_KEY. "
            "Contact the server administrator."
        )
    return access_key


def _get_headers() -> Dict[str, str]:
    return {
        "Accept-Version": "v1",
        "Authorization": f"Client-ID {_get_access_key()}"
    }


def _photo_to_dataclass(photo: dict) -> UnsplashPhoto:
    user = photo["user"]
    photographer_name = user.get("name", user["username"])
    photographer_username = user["username"]
    utm = "unsplash_mcp"
    photographer_url = f"https://unsplash.com/@{photographer_username}?utm_source={utm}&utm_medium=referral"
    photo_url = photo["links"]["html"] + f"?utm_source={utm}&utm_medium=referral"
    attribution_text = f"Photo by {photographer_name} on Unsplash"
    attribution_html = (
        f'Photo by <a href="{photographer_url}">{photographer_name}</a> '
        f'on <a href="https://unsplash.com/?utm_source={utm}&utm_medium=referral">Unsplash</a>'
    )
    return UnsplashPhoto(
        id=photo["id"],
        description=photo.get("description"),
        alt_description=photo.get("alt_description"),
        urls=photo["urls"],
        width=photo["width"],
        height=photo["height"],
        color=photo.get("color", "#000000"),
        blur_hash=photo.get("blur_hash"),
        photographer_name=photographer_name,
        photographer_username=photographer_username,
        photographer_url=photographer_url,
        photo_url=photo_url,
        attribution_text=attribution_text,
        attribution_html=attribution_html,
    )


@mcp.tool(
    title="Search Unsplash Photos",
    annotations={"readOnlyHint": True, "openWorldHint": True},
)
async def search_photos(
    query: str,
    page: Union[int, str] = 1,
    per_page: Union[int, str] = 10,
    order_by: str = "relevant",
    color: Optional[str] = None,
    orientation: Optional[str] = None,
    content_filter: str = "low",
) -> List[UnsplashPhoto]:
    """
    Search for photos on Unsplash by keyword.

    Calls the Unsplash GET /search/photos endpoint
    (https://unsplash.com/documentation#search-photos). Read-only.

    Returns photos with full attribution data. Each photo includes
    attribution_text and attribution_html ready to embed in content.

    Args:
        query: Search keyword(s), e.g. "mountain landscape", "coffee shop"
        page: Page number for pagination (default: 1)
        per_page: Results per page, 1-30 (default: 10)
        order_by: "relevant" (best match) or "latest" (newest first)
        color: black_and_white, black, white, yellow, orange, red,
               purple, magenta, green, teal, or blue
        orientation: landscape, portrait, or squarish
        content_filter: "low" (default) or "high" (stricter safety)

    Returns:
        List of photos, each with urls (raw/full/regular/small/thumb),
        dimensions, dominant color, blur_hash, and attribution strings.
    """
    _enforce_rate_limit()
    try:
        page_int = max(1, int(page))
    except (ValueError, TypeError):
        page_int = 1
    try:
        per_page_int = min(max(1, int(per_page)), 30)
    except (ValueError, TypeError):
        per_page_int = 10

    params = {
        "query": query,
        "page": page_int,
        "per_page": per_page_int,
        "order_by": order_by,
        "content_filter": content_filter,
    }
    if color:
        params["color"] = color
    if orientation:
        params["orientation"] = orientation

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{UNSPLASH_API_BASE}/search/photos",
                params=params,
                headers=_get_headers(),
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            return [_photo_to_dataclass(p) for p in data["results"]]
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise ValueError("Server API key is invalid. Contact the administrator.")
        elif e.response.status_code == 403:
            raise ValueError("Unsplash rate limit exceeded. Please try again later.")
        raise ValueError(f"Unsplash API error {e.response.status_code}: {e.response.text}")
    except httpx.TimeoutException:
        raise ValueError("Request timed out. Please try again.")
    except Exception as e:
        raise ValueError(f"Failed to search photos: {e}")


@mcp.tool(
    title="Get Random Unsplash Photos",
    annotations={"readOnlyHint": True, "openWorldHint": True},
)
async def get_random_photos(
    query: Optional[str] = None,
    count: Union[int, str] = 1,
    orientation: Optional[str] = None,
    content_filter: str = "low",
) -> List[UnsplashPhoto]:
    """
    Get random photos from Unsplash, optionally filtered by keyword.

    Calls the Unsplash GET /photos/random endpoint
    (https://unsplash.com/documentation#get-a-random-photo). Read-only.

    Useful for hero images, backgrounds, or when you want variety
    rather than a specific search result.

    Args:
        query: Optional keyword filter (e.g. "nature", "technology")
        count: Number of photos to return, 1-30 (default: 1)
        orientation: landscape, portrait, or squarish
        content_filter: "low" (default) or "high" (stricter safety)

    Returns:
        List of photos with full attribution data.
    """
    _enforce_rate_limit()
    try:
        count_int = min(max(1, int(count)), 30)
    except (ValueError, TypeError):
        count_int = 1

    params: Dict[str, Union[str, int]] = {
        "count": count_int,
        "content_filter": content_filter,
    }
    if query:
        params["query"] = query
    if orientation:
        params["orientation"] = orientation

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{UNSPLASH_API_BASE}/photos/random",
                params=params,
                headers=_get_headers(),
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return [_photo_to_dataclass(p) for p in data]
            return [_photo_to_dataclass(data)]
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise ValueError("Server API key is invalid. Contact the administrator.")
        elif e.response.status_code == 403:
            raise ValueError("Unsplash rate limit exceeded. Please try again later.")
        raise ValueError(f"Unsplash API error {e.response.status_code}: {e.response.text}")
    except httpx.TimeoutException:
        raise ValueError("Request timed out. Please try again.")
    except Exception as e:
        raise ValueError(f"Failed to get random photos: {e}")


@mcp.tool(
    title="Track Unsplash Photo Download",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
)
async def track_download(photo_id: str) -> str:
    """
    Records a photo download event with Unsplash (required by API guidelines).

    Calls the Unsplash GET /photos/{id}/download endpoint
    (https://unsplash.com/documentation#track-a-photo-download). Unsplash's API
    terms require this whenever a user downloads or saves a photo at full
    resolution. Returns the direct download URL for the full-resolution image.

    Args:
        photo_id: The photo ID from a previous search_photos or get_random_photos result

    Returns:
        Direct download URL for the full-resolution photo
    """
    _enforce_rate_limit()
    if not photo_id or not photo_id.strip():
        raise ValueError("photo_id is required")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{UNSPLASH_API_BASE}/photos/{photo_id}/download",
                headers=_get_headers(),
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            url = data.get("url")
            if not url:
                raise ValueError(
                    f"Unsplash returned no download URL for photo {photo_id}."
                )
            return url
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise ValueError("Server API key is invalid. Contact the administrator.")
        elif e.response.status_code == 404:
            raise ValueError(f"Photo not found: {photo_id}")
        elif e.response.status_code == 403:
            raise ValueError("Unsplash rate limit exceeded. Please try again later.")
        raise ValueError(f"Unsplash API error {e.response.status_code}: {e.response.text}")
    except httpx.TimeoutException:
        raise ValueError("Request timed out. Please try again.")
    except Exception as e:
        raise ValueError(f"Failed to track download: {e}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
        path="/mcp",
    )
