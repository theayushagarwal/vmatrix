import os
import hashlib
import base64
import tempfile
import requests
from pathlib import Path
from typing import Optional, Tuple, Callable

# Common aliases mapping tool names/slugs to canonical SimpleIcons slugs
SIMPLEICONS_ALIASES = {
    "gemini": "googlegemini",
    "chatgpt": "openai",
    "gpt4": "openai",
    "gpt": "openai",
    "claude": "anthropic",
    "copilot": "githubcopilot",
    "nextjs": "nextdotjs",
    "postgres": "postgresql",
    "fastapi": "fastapi",
    "docker": "docker",
    "redis": "redis",
    "python": "python",
    "github": "github",
    "vscode": "visualstudiocode",
    "git": "git",
    "supabase": "supabase",
    "tailwind": "tailwindcss",
    "react": "react",
    "vue": "vuedotjs",
    "angular": "angular",
    "aws": "amazonwebservices",
    "cloudflare": "cloudflare",
    "vercel": "vercel",
    "qdrant": "qdrant",
    "ollama": "ollama",
    "huggingface": "huggingface",
    "linux": "linux",
}

# Domain mapping fallbacks for tools that aren't on SimpleIcons
DOMAIN_FALLBACKS = {
    "groq": "groq.com",
    "cartesia": "cartesia.ai",
    "cerebras": "cerebras.ai",
    "deepseek": "deepseek.com",
    "cursor": "cursor.com",
    "cursorpro": "cursor.com",
    "pinecone": "pinecone.io",
    "pineconeserverless": "pinecone.io",
    "continue": "continue.dev",
    "continuedev": "continue.dev",
    "vllm": "vllm.ai",
    "langchain": "langchain.com",
    "llamaindex": "llamaindex.ai",
}


def resolve_logo(
    tool_name: str,
    brand_slug: str = "",
    domain: str = "",
    output_dir: Optional[Path] = None,
    idx: int = 0,
    suffix: str = "",
    generate_image_callback: Optional[Callable] = None,
    custom_prompt: Optional[str] = None,
) -> Tuple[str, bool]:
    """
    The Secret Backend Engine: 4-Tier Logo Resolver.
    
    Tier 1: Custom local AI generated badge (if requested)
    Tier 2: SimpleIcons official CDN (https://cdn.simpleicons.org/{slug})
    Tier 3: jsDelivr NPM Raw SVG Fallback / Logo.dev
    Tier 4: Google High-Res Favicon API (domain lookup with >800 bytes validation)
    Tier 5: Graceful styled 2-letter monogram
    
    Returns:
        (resolved_logo_src, is_local_file)
    """
    clean_name = (tool_name or "").strip()
    if not brand_slug:
        brand_slug = clean_name.lower().replace(" ", "").replace(".", "")
    slug = brand_slug.lower().strip().replace(" ", "")
    slug = SIMPLEICONS_ALIASES.get(slug, slug)

    if not suffix:
        suffix = f"{slug}_{idx}"

    if output_dir is None:
        output_dir = Path(tempfile.gettempdir()) / "ai_social_logos"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Tier 1: Custom AI Image Callback (if requested) ───────────────────
    if generate_image_callback and custom_prompt:
        try:
            ai_path = output_dir / f"ai_logo_{suffix}.png"
            res_path = generate_image_callback(custom_prompt, ai_path)
            if res_path and Path(res_path).exists():
                return Path(res_path).absolute().as_uri(), True
        except Exception:
            pass

    # ── Tier 2: Check SimpleIcons Official CDN ────────────────────────────
    candidate_slugs = [slug]
    first_word = clean_name.split()[0].lower().replace(".", "") if clean_name else ""
    if first_word and first_word != slug:
        candidate_slugs.append(SIMPLEICONS_ALIASES.get(first_word, first_word))

    for c_slug in candidate_slugs:
        simple_icons_url = f"https://cdn.simpleicons.org/{c_slug}"
        try:
            r = requests.head(simple_icons_url, timeout=2.0)
            if r.status_code == 200:
                return simple_icons_url, False
        except Exception:
            pass

    # ── Tier 3: jsDelivr / Logo.dev Fallback ──────────────────────────────
    logodev_token = os.environ.get("LOGODEV_PUBLISHABLE_KEY") or "pk_Sq5GhYXkQpK2aOCI-cbM-A"
    target_domain = domain or DOMAIN_FALLBACKS.get(slug) or DOMAIN_FALLBACKS.get(first_word, f"{first_word or slug}.com")
    clean_domain = target_domain.replace("https://", "").replace("http://", "").split("/")[0].strip()

    if logodev_token and clean_domain:
        logodev_url = f"https://img.logo.dev/{clean_domain}?token={logodev_token}&size=128&format=png"
        try:
            r = requests.head(logodev_url, timeout=2.0)
            if r.status_code == 200:
                return logodev_url, False
        except Exception:
            pass

    # ── Tier 4: Fetch Google Favicon API using Domain ──────────────────────
    if clean_domain:
        favicon_url = f"https://www.google.com/s2/favicons?domain={clean_domain}&sz=128"
        try:
            r = requests.get(favicon_url, timeout=3.5)
            # Check it's not Google's blank grey globe fallback (which is ~726 bytes)
            if r.status_code == 200 and len(r.content) > 800:
                logo_path = output_dir / f"logo_{suffix}.png"
                logo_path.write_bytes(r.content)
                b64_data = base64.b64encode(r.content).decode("ascii")
                return f"data:image/png;base64,{b64_data}", True
        except Exception:
            pass

    # ── Tier 5: Return slug/name so template renders monogram letters ─────
    return slug or clean_name[:2].upper(), False


def resolve_logo_url(
    tool_name: str,
    brand_slug: str = "",
    domain: str = "",
    output_dir: Optional[Path] = None,
    idx: int = 0,
    suffix: str = "",
) -> str:
    """
    Convenience wrapper returning just the string URL or URI for Jinja templates.
    """
    src, _ = resolve_logo(
        tool_name=tool_name,
        brand_slug=brand_slug,
        domain=domain,
        output_dir=output_dir,
        idx=idx,
        suffix=suffix,
    )
    return src
