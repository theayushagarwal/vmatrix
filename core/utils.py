"""
core/utils.py
--------------
Small shared "self-healing" primitives used across the pipeline:

- `retry_with_backoff`: a decorator that retries a flaky call (network blip,
  rate limit, transient 5xx) with exponential backoff instead of letting one
  bad request kill the whole generation/publish run.
- `validate_png`: a cheap sanity check that a rendered screenshot is actually
  a real image at the expected size, not a blank/near-blank frame caused by
  a template error, a missing font, or a page that never painted.
"""

import time
import random
import functools
import logging
from pathlib import Path

logger = logging.getLogger("ai_social_engine")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class RenderValidationError(RuntimeError):
    """Raised when a rendered screenshot fails the post-render sanity check."""


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 12.0,
    exceptions: tuple = (Exception,),
):
    """
    Decorator: retries the wrapped function on failure with exponential
    backoff + jitter. Re-raises the last exception if every attempt fails.

    Usage:
        @retry_with_backoff(max_attempts=4, exceptions=(requests.RequestException,))
        def call_flaky_api(...): ...
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt == max_attempts:
                        logger.error(
                            "%s failed after %d attempts: %s", func.__name__, attempt, e
                        )
                        raise
                    delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
                    delay += random.uniform(0, delay * 0.25)  # jitter
                    logger.warning(
                        "%s failed (attempt %d/%d): %s — retrying in %.1fs",
                        func.__name__, attempt, max_attempts, e, delay,
                    )
                    time.sleep(delay)
            raise last_exc  # pragma: no cover - unreachable safeguard

        return wrapper

    return decorator


def validate_png(
    path: Path,
    expected_width: int | None = None,
    expected_height: int | None = None,
    min_std_dev: float = 3.0,
) -> None:
    """
    Sanity-checks a rendered PNG so a silently-broken render (missing CSS,
    a template exception swallowed by the browser, a blank white/black
    frame) never gets uploaded and published as if it were a good slide.

    Raises RenderValidationError if the file is missing, isn't a valid
    image, doesn't match the expected pixel dimensions, or looks like a
    near-uniform blank frame (very low pixel variance = almost certainly a
    broken layout, since a real designed slide has text, gradients, and
    panel edges).
    """
    from PIL import Image, ImageStat

    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        raise RenderValidationError(f"Render produced no file: {path}")

    try:
        img = Image.open(path)
        img.verify()
        img = Image.open(path)  # reopen after verify() invalidates the handle
    except Exception as e:
        raise RenderValidationError(f"Render is not a valid image ({path}): {e}")

    if expected_width and expected_height:
        if img.size != (expected_width, expected_height):
            raise RenderValidationError(
                f"Render size mismatch for {path}: got {img.size}, "
                f"expected ({expected_width}, {expected_height})"
            )

    stat = ImageStat.Stat(img.convert("L"))
    if stat.stddev[0] < min_std_dev:
        raise RenderValidationError(
            f"Render for {path} looks blank/near-uniform (stddev={stat.stddev[0]:.2f}). "
            "This usually means the HTML template failed to paint (broken CSS, "
            "missing template variable, or an unhandled slide type)."
        )
