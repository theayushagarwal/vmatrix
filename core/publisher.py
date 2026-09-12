"""
core/publisher.py
-------------------
Two responsibilities:
  1. Push local slide PNGs to Cloudinary so we have public HTTPS URLs
     (Meta's Graph API refuses localhost/base64 image sources).
  2. Drive the Instagram Graph API's carousel-publishing state machine:
     item containers -> parent carousel container -> publish.
"""

import os
import time
from pathlib import Path

import requests
import cloudinary
import cloudinary.uploader

from .utils import retry_with_backoff, logger

GRAPH_API_VERSION = "v19.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

POLL_INTERVAL_SECONDS = 2
POLL_MAX_ATTEMPTS = 30

# Transient failures worth retrying: network blips, timeouts, and 5xx/429s.
# 4xx errors other than 429 (bad auth, bad request) are not retried — retrying
# a permanently-broken request just burns time before failing anyway.
_RETRYABLE_EXCEPTIONS = (requests.ConnectionError, requests.Timeout, cloudinary.exceptions.Error)


def init_cloudinary():
    cloudinary.config(
        cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
        api_key=os.environ.get("CLOUDINARY_API_KEY"),
        api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
        secure=True,
    )


@retry_with_backoff(max_attempts=4, base_delay=1.5, exceptions=_RETRYABLE_EXCEPTIONS)
def _upload_one(path: Path) -> str:
    result = cloudinary.uploader.upload(
        str(path),
        folder="ai-social-engine",
        resource_type="image",
        overwrite=True,
    )
    return result["secure_url"]


def upload_images_to_cloudinary(image_paths: list[Path]) -> list[str]:
    """
    Uploads local slide PNGs to Cloudinary and returns a list of secure HTTPS
    URLs. Each upload is retried independently with backoff, so one flaky
    request doesn't force a full re-upload of every slide.
    """
    init_cloudinary()
    return [_upload_one(path) for path in image_paths]


def _poll_container_status(container_id: str, access_token: str) -> str:
    """
    Polls a media container until its status_code is FINISHED. Self-healing
    behavior: a transient network error on any single poll doesn't abort the
    whole publish — it's logged and polling continues — and an ERROR status
    from Meta is retried a couple of times (their processing occasionally
    flakes on a container and clears up) before we give up for real.
    """
    status_url = f"{GRAPH_API_BASE}/{container_id}"
    consecutive_errors = 0
    for attempt in range(POLL_MAX_ATTEMPTS):
        try:
            resp = requests.get(
                status_url,
                params={"fields": "status_code", "access_token": access_token},
                timeout=15,
            )
            resp.raise_for_status()
            status = resp.json().get("status_code", "IN_PROGRESS")
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            logger.warning("Poll request failed for %s (attempt %d): %s", container_id, attempt + 1, e)
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        if status == "FINISHED":
            return status
        if status == "ERROR":
            consecutive_errors += 1
            logger.warning(
                "Container %s reported ERROR (occurrence %d/2), retrying poll…",
                container_id, consecutive_errors,
            )
            if consecutive_errors >= 2:
                raise RuntimeError(f"Container {container_id} failed to process.")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"Container {container_id} did not finish within the polling window.")


def publish_to_instagram_carousel(image_urls: list[str], caption: str) -> dict:
    """
    1. Create item containers (is_carousel_item=true) for each image URL.
    2. Poll item status until FINISHED.
    3. Create parent carousel container with children IDs & caption.
    4. Poll parent status until FINISHED.
    5. Publish via media_publish endpoint.
    Returns: dict with post_id and success status.
    """
    ig_user_id = os.environ.get("IG_USER_ID")
    access_token = os.environ.get("IG_ACCESS_TOKEN")
    if not ig_user_id or not access_token:
        raise ValueError("IG_USER_ID / IG_ACCESS_TOKEN are not set.")

    @retry_with_backoff(max_attempts=3, base_delay=2.0, exceptions=(requests.ConnectionError, requests.Timeout))
    def _create_item_container(url: str) -> str:
        resp = requests.post(
            f"{GRAPH_API_BASE}/{ig_user_id}/media",
            data={
                "image_url": url,
                "is_carousel_item": "true",
                "access_token": access_token,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    # 1. Create item containers
    item_container_ids: list[str] = [_create_item_container(url) for url in image_urls]

    # 2. Poll each item container
    for container_id in item_container_ids:
        _poll_container_status(container_id, access_token)

    @retry_with_backoff(max_attempts=3, base_delay=2.0, exceptions=(requests.ConnectionError, requests.Timeout))
    def _create_parent_container() -> str:
        resp = requests.post(
            f"{GRAPH_API_BASE}/{ig_user_id}/media",
            data={
                "media_type": "CAROUSEL",
                "caption": caption,
                "children": ",".join(item_container_ids),
                "access_token": access_token,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    # 3. Create parent carousel container
    parent_container_id = _create_parent_container()

    # 4. Poll parent container
    _poll_container_status(parent_container_id, access_token)

    @retry_with_backoff(max_attempts=3, base_delay=2.0, exceptions=(requests.ConnectionError, requests.Timeout))
    def _publish() -> str | None:
        resp = requests.post(
            f"{GRAPH_API_BASE}/{ig_user_id}/media_publish",
            data={
                "creation_id": parent_container_id,
                "access_token": access_token,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("id")

    # 5. Publish
    post_id = _publish()

    return {"success": True, "post_id": post_id, "container_id": parent_container_id}
