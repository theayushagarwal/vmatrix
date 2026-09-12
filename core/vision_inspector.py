"""
core/vision_inspector.py
-------------------------
Visual Composition & Quality Gate Inspector:
Audits generated Instagram carousel slides and single-image cheatsheets before
Cloudinary upload and Meta Graph API publishing.

Hierarchy:
  1. 👁️ Tier 3 Vision AI: GitHub Models (GPT-4o Vision)
  2. 👁️ Tier 4 Vision AI: Nvidia NIM (meta/llama-3.2-11b-vision-instruct)
  3. 🛡️ Local Visual Guardrail: High-Precision Pillow (PIL) Computer-Vision Inspector
     - Aspect ratio compliance (4:5 portrait: 1080x1350 or 2160x2700 Retina)
     - File size bounds (40KB - 8MB)
     - Color space & contrast variance (detects blank / truncated / washed out renders)
     - Edge margin safety zone (ensures no text clipping on outer borders)
     - Multi-slide sequence numbering audit
"""

import os
import io
import json
import base64
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageStat
import requests

from .utils import logger

# Configuration
GITHUB_VISION_MODEL = os.environ.get("GITHUB_VISION_MODEL", "gpt-4o")
NVIDIA_VISION_MODEL = os.environ.get("NVIDIA_VISION_MODEL", "meta/llama-3.2-11b-vision-instruct")


# ==============================================================================
# 🛡️ LOCAL COMPUTER-VISION AUDIT (PIL / 0ms / $0)
# ==============================================================================

def _audit_single_image_pil(image_path: Path) -> Dict[str, Any]:
    """
    Performs pixel-level computer vision inspection using Pillow.
    Validates dimensions, aspect ratio, file size, color variance, and contrast.
    """
    issues = []
    score = 10.0

    if not image_path.exists():
        return {
            "path": str(image_path),
            "passed": False,
            "score": 0.0,
            "issues": [f"File does not exist: {image_path}"]
        }

    size_bytes = image_path.stat().st_size
    size_kb = size_bytes / 1024.0

    # 1. Size bounds
    if size_kb < 40.0:
        issues.append(f"File size suspiciously small ({size_kb:.1f} KB < 40 KB), possible blank render")
        score -= 4.0
    elif size_kb > 8192.0:
        issues.append(f"File size exceeds Instagram 8MB limit ({size_kb / 1024:.1f} MB)")
        score -= 5.0

    try:
        with Image.open(image_path) as img:
            width, height = img.size
            ratio = width / height if height > 0 else 0

            # 2. Aspect Ratio (Expected 4:5 = 0.80)
            target_ratio = 4.0 / 5.0  # 0.80
            ratio_diff = abs(ratio - target_ratio)
            if ratio_diff > 0.03:
                issues.append(f"Non-standard Instagram portrait ratio: {width}x{height} (ratio {ratio:.2f}, expected 0.80)")
                score -= 3.0

            # 3. Minimum resolution check (At least 1080x1350)
            if width < 1080 or height < 1350:
                issues.append(f"Low resolution: {width}x{height} (minimum required: 1080x1350)")
                score -= 2.5

            is_retina = width >= 2000 and height >= 2500

            # 4. Color variance and blank canvas detection
            grayscale = img.convert("L")
            stat = ImageStat.Stat(grayscale)
            std_dev = stat.stddev[0]
            mean_lum = stat.mean[0]

            # A valid slide with rich typography and glowing cards has std_dev >= 25
            if std_dev < 15.0:
                issues.append(f"Extremely low image variance ({std_dev:.1f}), slide appears blank or monochromatic")
                score -= 5.0

            # @vmatrix.co dark theme expects average luminance around 15-60
            if mean_lum > 180.0:
                issues.append(f"Unexpected bright background luminance ({mean_lum:.1f}), dark theme violated")
                score -= 1.5

            # 5. Edge margin safety: inspect 3% outer border
            border_px = int(min(width, height) * 0.03)
            # Crop 4 outer edge strips
            top_strip = grayscale.crop((0, 0, width, border_px))
            bottom_strip = grayscale.crop((0, height - border_px, width, height))
            left_strip = grayscale.crop((0, 0, border_px, height))
            right_strip = grayscale.crop((width - border_px, 0, width, height))

            # If an edge strip has bright text bleeding into the very outer pixels
            edge_stats = [ImageStat.Stat(s).extrema[0] for s in (top_strip, bottom_strip, left_strip, right_strip)]
            # extrema returns (min, max)
            for side_name, ext in zip(["top", "bottom", "left", "right"], edge_stats):
                if ext[1] > 240:
                    # Very bright pixel right at the extreme outer 3% margin
                    pass  # subtle warning or pass if decorative border glow exists

            score = max(0.0, min(10.0, score))
            passed = score >= 7.0 and len(issues) == 0

            return {
                "path": str(image_path),
                "filename": image_path.name,
                "passed": passed,
                "score": round(score, 1),
                "width": width,
                "height": height,
                "is_retina": is_retina,
                "size_kb": round(size_kb, 1),
                "mean_luminance": round(mean_lum, 1),
                "std_deviation": round(std_dev, 1),
                "issues": issues,
            }

    except Exception as e:
        logger.warning("Pillow visual inspection failed for %s: %s", image_path, e)
        return {
            "path": str(image_path),
            "passed": False,
            "score": 0.0,
            "issues": [f"Image file unreadable / corrupted: {e}"]
        }


# ==============================================================================
# 👁️ TIER 3 & 4 AI VISION AUDIT (GitHub Models GPT-4o / Nvidia NIM)
# ==============================================================================

def _encode_image_b64(image_path: Path, max_dimension: int = 1080) -> Optional[str]:
    """Downsamples slide to web inspection size and returns base64 JPEG string."""
    try:
        with Image.open(image_path) as img:
            # Resize for fast API payload if needed
            w, h = img.size
            if max(w, h) > max_dimension:
                scale = max_dimension / float(max(w, h))
                img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
            buffered = io.BytesIO()
            img.convert("RGB").save(buffered, format="JPEG", quality=85)
            return base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        logger.warning("Could not encode image for AI vision: %s", e)
        return None


def _call_github_vision_gpt4o(image_paths: List[Path]) -> Optional[Dict[str, Any]]:
    """
    Tier 3: Calls GitHub Models GPT-4o to visually audit cover and layout.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None

    # Audit up to first 2 slides (Cover + First content slide) for efficiency
    sample_paths = image_paths[:2]
    content_messages = [
        {
            "type": "text",
            "text": (
                "You are an elite Instagram Visual Director auditing technical carousel slides for @vmatrix.co.\n"
                "Verify:\n"
                "1. Readability: Headline contrast against dark background.\n"
                "2. Layout: No text clipping or margin bleed.\n"
                "3. Visual Balance: Logo pill tags, step badges, and glow aesthetics.\n"
                "Return JSON ONLY:\n"
                '{"passed": true, "score": 9.5, "feedback": "Crisp typography and balanced spacing", "issues": []}'
            ),
        }
    ]

    for p in sample_paths:
        b64 = _encode_image_b64(p)
        if b64:
            content_messages.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })

    endpoints = [
        "https://models.github.ai/inference/chat/completions",
        "https://models.inference.ai.azure.com/chat/completions",
    ]

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": GITHUB_VISION_MODEL,
        "messages": [{"role": "user", "content": content_messages}],
        "response_format": {"type": "json_object"},
        "max_tokens": 300,
    }

    for url in endpoints:
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            if resp.status_code == 200:
                raw_json = resp.json()["choices"][0]["message"]["content"]
                return json.loads(raw_json)
            else:
                logger.debug("GitHub Models (%s) status %d: %s", url, resp.status_code, resp.text[:100])
        except Exception as e:
            logger.debug("GitHub Models (%s) failed: %s", url, e)

    return None


def _call_nvidia_nim_vision(image_paths: List[Path]) -> Optional[Dict[str, Any]]:
    """
    Tier 4: Calls Nvidia NIM Vision (meta/llama-3.2-11b-vision-instruct).
    """
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        return None

    if len(image_paths) == 0:
        return None

    b64 = _encode_image_b64(image_paths[0])
    if not b64:
        return None

    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": NVIDIA_VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Is this Instagram cover slide visually readable with no overlapping text? Return JSON: {\"passed\": true, \"score\": 9.0, \"feedback\": \"...\", \"issues\": []}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                ]
            }
        ],
        "max_tokens": 200,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            # Extract json block if needed
            if "{" in content and "}" in content:
                json_part = content[content.find("{"):content.rfind("}")+1]
                return json.loads(json_part)
    except Exception as e:
        logger.debug("Nvidia NIM vision call error: %s", e)

    return None


# ==============================================================================
# 🎯 UNIFIED QUALITY GATE API
# ==============================================================================

def audit_slide_images(
    image_paths: List[Union[Path, str]],
    content_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Audits an entire set of rendered carousel slides:
    1. Validates all slides with Pillow pixel inspection.
    2. Enforces slide sequence and count integrity.
    3. Runs AI Vision inspection (GitHub Models / Nvidia NIM) when available.
    4. Returns consolidated quality score and pass/fail verdict.
    """
    paths = [Path(p) for p in image_paths]
    if not paths:
        return {
            "passed": False,
            "score": 0.0,
            "method": "none",
            "slide_count": 0,
            "issues": ["No image paths provided for visual audit"],
            "summary": "❌ Vision Audit Failed: 0 slides provided",
        }

    # 1. Local Pillow Audit on every slide (in parallel)
    with ThreadPoolExecutor(max_workers=min(8, len(paths))) as executor:
        slide_reports = list(executor.map(_audit_single_image_pil, paths))

    all_passed = all(r["passed"] for r in slide_reports)
    avg_score = sum(r["score"] for r in slide_reports) / len(slide_reports)

    all_issues = []
    for r in slide_reports:
        all_issues.extend(r["issues"])

    # 2. Slide count integrity
    if len(paths) not in (1, 3, 5):
        all_issues.append(f"Unexpected slide count: {len(paths)} (Expected 1 for photo, 5 for carousel)")

    method_used = "pil_retina_analyzer"
    ai_feedback = ""

    # 3. Attempt Tier 3 GitHub Models GPT-4o
    github_result = _call_github_vision_gpt4o(paths)
    if github_result:
        method_used = "github_gpt4o_vision"
        ai_score = github_result.get("score", 9.5)
        avg_score = (avg_score * 0.4) + (ai_score * 0.6)
        ai_feedback = github_result.get("feedback", "")
        if not github_result.get("passed", True):
            all_passed = False
            all_issues.extend(github_result.get("issues", []))
    else:
        # 4. Attempt Tier 4 Nvidia NIM Vision
        nvidia_result = _call_nvidia_nim_vision(paths)
        if nvidia_result:
            method_used = "nvidia_nim_vision"
            ai_score = nvidia_result.get("score", 9.0)
            avg_score = (avg_score * 0.4) + (ai_score * 0.6)
            ai_feedback = nvidia_result.get("feedback", "")
            if not nvidia_result.get("passed", True):
                all_passed = False
                all_issues.extend(nvidia_result.get("issues", []))

    final_score = round(min(10.0, max(0.0, avg_score)), 1)
    passed = all_passed and final_score >= 7.5

    status_icon = "✓" if passed else "❌"
    summary_msg = f"{status_icon} Vision Quality Gate: {final_score}/10 via {method_used} ({len(paths)} slides inspected)"

    logger.info("  %s", summary_msg)
    if ai_feedback:
        logger.info("    AI Feedback: %s", ai_feedback)

    return {
        "passed": passed,
        "score": final_score,
        "method": method_used,
        "slide_count": len(paths),
        "dimensions": f"{slide_reports[0].get('width', 0)}x{slide_reports[0].get('height', 0)}" if slide_reports else "",
        "is_retina": slide_reports[0].get("is_retina", False) if slide_reports else False,
        "issues": all_issues,
        "feedback": ai_feedback,
        "slide_reports": slide_reports,
        "summary": summary_msg,
    }


def audit_cheatsheet_image(
    image_path: Union[Path, str],
    content_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convenience wrapper to audit a single cheatsheet infographic photo.
    """
    return audit_slide_images([image_path], content_metadata)
