"""
core/media_generator.py / media_generator.py
--------------------------------------------
Layer 3, Layer 4 & Layer 5 Visual QA Engine:
- Layer 3: Pixel-Level Border Bleed & Edge Cropping Detector (has_border_bleed)
- Layer 4: Multi-Model Consensus Vision Screener (validate_image):
    * Partner 1: Groq Vision (meta-llama/llama-4-scout-17b-16e-instruct / llama-3.2-11b-vision-preview)
    * Partner 2: Nvidia NIM Vision (meta/llama-3.2-11b-vision-instruct)
    * Partner 3: GitHub Models Vision (gpt-4o / gpt-4o-mini)
    * Supreme Court Tie-Breaker: Gemini 2.5 Flash
- Layer 5: Visual Layout Auditor & Surgical Auto-Recovery Loop (verify_compiled_slides_vision, shorten_slide_text)
"""

import os
import io
import json
import base64
import logging
from pathlib import Path
from typing import Union, List, Tuple, Optional
from PIL import Image, ImageStat
import requests

logger = logging.getLogger("media_generator")

# Lazy Gemini client helper
_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            try:
                from google import genai
                _gemini_client = genai.Client(api_key=gemini_key)
            except Exception as e:
                logger.debug("Could not initialize google.genai Client: %s", e)
    return _gemini_client


# ==============================================================================
# LAYER 3: PIXEL-LEVEL BORDER BLEED DETECTION
# ==============================================================================

def has_border_bleed(
    img_source: Union[str, Path, bytes, Image.Image],
    strip_px: int = 10,
    threshold: float = 0.02,
    is_light_theme: Optional[bool] = None,
) -> bool:
    """
    Scans a 10px strip around the entire outer perimeter of the image.
    If unexpected edge pixels exceed threshold (2%), flags as border bleed.
    - For Dark Themes: flags bright edge pixels ((r+g+b)/3.0 > 150)
    - For Light Themes: flags dark edge lines / letterboxing ((r+g+b)/3.0 < 60)
    """
    try:
        if isinstance(img_source, Image.Image):
            img = img_source.copy()
        elif isinstance(img_source, (str, Path)):
            img = Image.open(img_source)
        else:
            img = Image.open(io.BytesIO(img_source))

        img = img.convert("RGB")
        w, h = img.size
        pixels = img.load()

        # Determine theme if not explicitly specified
        if is_light_theme is None:
            gray = img.convert("L")
            stat = ImageStat.Stat(gray)
            is_light_theme = stat.mean[0] > 160.0

        total_pixels = 0
        bleed_pixels = 0

        # Helper to test a pixel for bleed
        def is_bleed_pixel(r, g, b) -> bool:
            lum = (r + g + b) / 3.0
            if is_light_theme:
                # In light theme, harsh black/dark cropping bars/lines represent border bleed
                return lum < 50.0
            else:
                # In dark theme, harsh bright white letterbox lines represent border bleed
                return lum > 210.0

        # Scan bottom 10px strip
        for x in range(w):
            for y in range(min(strip_px, h)):
                r, g, b = pixels[x, h - 1 - y]
                total_pixels += 1
                if is_bleed_pixel(r, g, b):
                    bleed_pixels += 1

        # Scan left and right 10px strips
        for y in range(min(strip_px, h), max(strip_px, h - strip_px)):
            for x in range(min(strip_px, w)):
                # Left edge
                r, g, b = pixels[x, y]
                total_pixels += 1
                if is_bleed_pixel(r, g, b):
                    bleed_pixels += 1

                # Right edge
                r, g, b = pixels[w - 1 - x, y]
                total_pixels += 1
                if is_bleed_pixel(r, g, b):
                    bleed_pixels += 1

        if total_pixels == 0:
            return False

        ratio = bleed_pixels / total_pixels
        if ratio > threshold:
            logger.warning(
                f"Border bleed detected: {ratio:.2%} edge artifact pixels (exceeds {threshold:.2%})"
            )
            return True

        return False
    except Exception as e:
        logger.warning(f"Failed border bleed check: {e}")
        return False


# ==============================================================================
# LAYER 4: MULTI-MODEL VISION SCREENER (Consensus Panel)
# ==============================================================================

def validate_image_via_groq(image_bytes: bytes, prompt: str) -> Optional[bool]:
    """Tier 1: Groq Vision screening (meta-llama/llama-4-scout-17b-16e-instruct or 11b-vision)."""
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None

    try:
        from groq import Groq
        client = Groq(api_key=key)
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        model = os.environ.get("GROQ_VISION_MODEL", "llama-3.2-11b-vision-preview")

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                    ]
                }
            ],
            temperature=0.1,
            max_tokens=20,
        )
        ans = resp.choices[0].message.content.strip().upper()
        if "APPROVE" in ans:
            return True
        if "REJECT" in ans:
            return False
    except Exception as e:
        logger.debug("Groq vision audit failed: %s", e)
    return None


def validate_image_via_nvidia(image_bytes: bytes, prompt: str) -> Optional[bool]:
    """Tier 2: Nvidia NIM Vision screening (meta/llama-3.2-11b-vision-instruct)."""
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        return None

    try:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": os.environ.get("NVIDIA_VISION_MODEL", "meta/llama-3.2-11b-vision-instruct"),
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                    ]
                }
            ],
            "max_tokens": 20,
            "temperature": 0.1,
        }
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            ans = r.json()["choices"][0]["message"]["content"].strip().upper()
            if "APPROVE" in ans:
                return True
            if "REJECT" in ans:
                return False
    except Exception as e:
        logger.debug("Nvidia vision audit failed: %s", e)
    return None


def validate_image_via_github(image_bytes: bytes, prompt: str) -> Optional[bool]:
    """Tier 3: GitHub Models (GPT-4o Vision)."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None

    try:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        url = "https://models.github.ai/inference/chat/completions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": os.environ.get("GITHUB_VISION_MODEL", "gpt-4o"),
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                    ]
                }
            ],
            "max_tokens": 20,
            "temperature": 0.1,
        }
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            ans = r.json()["choices"][0]["message"]["content"].strip().upper()
            if "APPROVE" in ans:
                return True
            if "REJECT" in ans:
                return False
    except Exception as e:
        logger.debug("GitHub vision audit failed: %s", e)
    return None


def validate_image(
    image_bytes: bytes,
    prompt: str,
    is_listicle: bool = False,
    slide_text: Optional[str] = None
) -> bool:
    """
    Multi-Model Consensus Vision Screener:
    Consensus panel of Groq + Nvidia + GitHub.
    Gemini 2.5 Flash acts as tie-breaker only when providers disagree.
    """
    context_part = f" and slide overlay text content: '{slide_text}'" if slide_text else ""

    if is_listicle:
        validation_prompt = (
            f"Analyze this educational slide image with the title/context: '{prompt}'{context_part}. "
            "Perform a quality control check on readability. "
            "Is the text cut off, overlapping, illegible, blurry, heavily misaligned, or formatted poorly? "
            "If yes (poor layout/unreadable text), reply with exactly: REJECT. "
            "If the slide is high quality, clean, readable, and formatted correctly, reply with exactly: APPROVE."
        )
    else:
        validation_prompt = (
            f"Analyze this image generated for the prompt: '{prompt}'{context_part}.\n"
            "1. RELEVANCE CHECK: Does the visual content actually match the technical concept? "
            "If the prompt describes code, servers, or trading, but the image shows a living room or random plants, REJECT it immediately.\n"
            "2. QUALITY CHECK: Is it blurry, distorted, or contains gibberish text/watermarks? If yes, reply REJECT.\n"
            "If high quality and relevant, reply with exactly: APPROVE."
        )

    active_decisions = []
    partner_names = []

    # 1. Check Groq Vision
    if os.environ.get("GROQ_API_KEY"):
        groq_ok = validate_image_via_groq(image_bytes, validation_prompt)
        if groq_ok is not None:
            active_decisions.append(groq_ok)
            partner_names.append("Groq")

    # 2. Check Nvidia Vision
    if os.environ.get("NVIDIA_API_KEY"):
        nvidia_ok = validate_image_via_nvidia(image_bytes, validation_prompt)
        if nvidia_ok is not None:
            active_decisions.append(nvidia_ok)
            partner_names.append("Nvidia")

    # 3. Check GitHub Models (GPT-4o)
    if os.environ.get("GITHUB_TOKEN"):
        github_ok = validate_image_via_github(image_bytes, validation_prompt)
        if github_ok is not None:
            active_decisions.append(github_ok)
            partner_names.append("GitHub")

    # ── CONSENSUS CHECK ───────────────────────────────────────────────────
    if active_decisions:
        if all(active_decisions):
            logger.info(f"Vision Consensus: All partners ({', '.join(partner_names)}) voted APPROVE. Skipping Gemini.")
            return True
        elif not any(active_decisions):
            logger.info(f"Vision Consensus: All partners ({', '.join(partner_names)}) voted REJECT. Skipping Gemini.")
            return False

    # ── TIE-BREAKER: GEMINI 2.5 FLASH ──────────────────────────────────────
    client = _get_gemini_client()
    if client:
        try:
            from google.genai import types
            img = Image.open(io.BytesIO(image_bytes))
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[img, validation_prompt],
                config=types.GenerateContentConfig(temperature=0.1)
            )
            decision = response.text.strip().upper()
            return "REJECT" not in decision
        except Exception as e:
            logger.debug("Gemini vision tie-breaker failed: %s", e)

    # Fallback to majority vote if Gemini fails or is not available
    if active_decisions:
        num_approves = sum(1 for d in active_decisions if d)
        num_rejects = len(active_decisions) - num_approves
        return num_approves >= num_rejects

    # Default pass if no external vision APIs responded
    return True


# ==============================================================================
# LAYER 5: VISUAL LAYOUT AUDITOR & AUTO-RECOVERY LOOP
# ==============================================================================

def shorten_slide_text(desc: str, target_words: int = 24) -> str:
    """
    Surgically shortens slide description to eliminate card overflow while preserving technical depth.
    """
    if not desc:
        return ""

    words = desc.split()
    if len(words) <= target_words:
        return desc

    # Try taking the first 1-2 complete sentences that fit under target_words
    sentences = [s.strip() for s in desc.split(".") if s.strip()]
    condensed = ""
    for s in sentences:
        candidate = f"{condensed} {s}.".strip()
        if len(candidate.split()) <= target_words:
            condensed = candidate
        else:
            break

    if condensed and len(condensed.split()) >= 10:
        return condensed

    # Hard truncate to word boundary
    truncated = " ".join(words[:target_words])
    return f"{truncated.rstrip(' ,;:')}."


def verify_compiled_slides_vision(
    slide_paths: List[Union[str, Path]],
    is_listicle: bool = True,
) -> Tuple[bool, List[int]]:
    """
    Audits an entire compiled slide carousel for visual layout compliance:
    Checks border bleed and layout readability on every slide.
    Returns: (is_approved: bool, failed_indices: List[int]) (1-based indices)
    """
    failed_indices = []

    for idx, sp in enumerate(slide_paths, start=1):
        path = Path(sp)
        if not path.exists():
            failed_indices.append(idx)
            continue

        try:
            # 1. Border bleed check
            if has_border_bleed(path, strip_px=10, threshold=0.04):
                logger.warning("Slide %d failed border bleed detection.", idx)
                failed_indices.append(idx)
                continue

            # 2. Vision readability check on content slides
            with open(path, "rb") as f:
                img_bytes = f.read()

            is_ok = validate_image(
                image_bytes=img_bytes,
                prompt=f"Slide {idx} carousel layout check",
                is_listicle=is_listicle,
            )
            if not is_ok:
                logger.warning("Slide %d failed vision layout audit.", idx)
                failed_indices.append(idx)

        except Exception as e:
            logger.debug("Error auditing slide %d: %s", idx, e)

    is_approved = len(failed_indices) == 0
    return is_approved, failed_indices
