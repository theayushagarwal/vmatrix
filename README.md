# ⚡ ai-social-engine

**An autonomous social media engine that discovers trending topics across 4 real-time data feeds and turns any topic into a published Instagram carousel — in under 5 seconds of AI compute.**

No design tool. No copywriter. No manual export-and-upload. Pick a breaking trend from the live radar (or type your own topic), and the pipeline plans the content, designs on-brand visuals, and publishes live.

---

## 🏆 The Pitch

Educational Instagram pages live and die by a brutal content treadmill: research what's trending, write punchy copy, design five on-brand slides, export them, upload them, write a caption, and publish — every single day. `ai-social-engine` collapses that entire pipeline into one flow:

**Real-Time Feeds In → Structured Plan (Gemini 2.5 Flash) → Rendered 4:5 Retina Slides (Playwright + HTML/CSS) → Live Instagram Post (Meta Graph API), end to end, with a live-updating Streamlit control room.**

---

## 📡 4 Core Content & Topic Data Feeds

The engine continuously monitors 4 live signals for high-signal topic discovery:

1. 📈 **Google Trends**: Real-time and daily search spikes in India (`geo=IN`) and Global/US (`geo=US`).
2. 🤖 **TechCrunch AI**: Breaking AI startup funding rounds, product launches, and venture news.
3. 🏢 **VentureBeat AI**: Enterprise AI architectures, new LLM models, and AI research breakthroughs.
4. 💻 **Hacker News**: Trending developer tools, coding libraries, and viral open-source GitHub repositories.

---

## 🧠 Architecture

```
┌─────────────────────────────────┐
│   4 Core Data Feeds             │
│  (Google Trends, TechCrunch AI, │
│   VentureBeat AI, Hacker News)  │
└────────────────┬────────────────┘
                 │
                 ▼
┌────────────────────────────────┐     ┌───────────────────┐     ┌──────────────────┐     ┌────────────────────┐
│      Streamlit Control Room    │ ──▶ │  Gemini 2.5 Flash │ ──▶ │  Playwright HTML  │ ──▶ │ Cloudinary + Meta   │
│            app.py              │     │  core/generator.py│     │  core/renderer.py │     │  core/publisher.py  │
│    (Radar, JSON, Preview)      │     │  (structured JSON │     │  (Jinja2 template │     │  (host images, drive│
│                                │     │   content plan)   │     │   → 1080x1350 PNG)│     │   carousel publish) │
└────────────────────────────────┘     └───────────────────┘     └──────────────────┘     └────────────────────┘
```

**Why this stack:**
- **4 Live Feeds (`core/feeds.py`)** with direct RSS and API ingestion for real-time trend discovery.
- **Gemini 2.5 Flash** with native `response_mime_type="application/json"` — no brittle regex parsing of markdown-fenced JSON, schema enforced by the model.
- **Playwright + Jinja2 + Tailwind** for rendering — real CSS (blur, gradients, grid) at true Retina resolution (`device_scale_factor=2`).
- **Cloudinary** as the media bridge — Meta's Graph API requires public HTTPS image URLs.
- **Meta Graph API's carousel state machine** — item containers → parent container → publish, each step polled until `FINISHED`.

---

## 🩹 Self-Healing by Design

Auto-publishing to a live social account means a silent failure is worse than a loud one. `core/utils.py` centralizes two safety nets used everywhere in the pipeline:

- **Retry with exponential backoff** — every network call (feed gathering, Gemini generation, Cloudinary upload, each step of the Instagram container/publish flow) is wrapped in `retry_with_backoff`.
- **Render validation, not blind trust** — every screenshot is checked against expected pixel dimensions and pixel-variance before acceptance.
- **Graceful UI recovery** — targeted retries in Streamlit without burning unnecessary AI compute.

---

## 📂 Project Structure

```text
ai-social-engine/
├── requirements.txt
├── .env.example
├── README.md
├── core/
│   ├── __init__.py
│   ├── feeds.py           # 4 core feeds (Google Trends, TechCrunch AI, VentureBeat, Hacker News)
│   ├── generator.py       # Gemini 2.5 Flash structured content planner
│   ├── renderer.py        # Playwright HTML-to-Image 4:5 slide renderer
│   ├── publisher.py       # Cloudinary uploader & Meta Graph API publisher
│   └── utils.py           # Retry decorator & image validation
├── templates/
│   ├── carousel_slide.html       # Glassmorphic dark-mode educational slide
│   └── single_infographic.html   # Cheatsheet/comparison grid infographic
└── app.py                 # Streamlit control room UI with Live Topic Radar
```

---

## 🚀 Quickstart

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Configure environment
cp .env.example .env
# fill in GEMINI_API_KEY, CLOUDINARY_*, IG_USER_ID, IG_ACCESS_TOKEN

# 3. Run the demo
streamlit run app.py
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Topic Data Gathering | Google Trends RSS, TechCrunch AI RSS, VentureBeat AI RSS, Hacker News API |
| Content Intelligence | Gemini 2.5 Flash, structured JSON output |
| Rendering | Playwright (headless Chromium), Jinja2, Tailwind CSS |
| Media Hosting | Cloudinary |
| Publishing | Meta / Instagram Graph API (carousel containers) |
| Demo UI | Streamlit |
