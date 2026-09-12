# ⚡ ai-social-engine

**An autonomous social media engine that filters 100+ raw trend signals through a 5-Stage AI Funnel and turns winning topics into published Instagram carousels — in under 5 seconds of AI compute.**

No design tool. No copywriter. No manual export-and-upload. Raw noise in, vetted educational carousel live on Instagram.

---

## 🏆 The Pitch

Educational Instagram pages live and die by a brutal content treadmill: research what's trending, filter out noise, write punchy copy, design five on-brand slides, export them, upload them, write a caption, and publish — every single day. `ai-social-engine` collapses that entire pipeline into one autonomous flow:

**100+ Raw Signals In → 5-Stage Filtering Funnel → Structured Plan (Gemini 2.5 Flash) → Rendered 4:5 Retina Slides (Playwright + HTML/CSS) → Live Instagram Post (Meta Graph API).**

---

## 🌪️ 5-Stage Filtering Funnel

When gathering real-time data from search trends and news feeds, 90% of raw headlines are noise, sports, gossip, and clickbait. Our 5-stage funnel refines raw signals into high-converting post topics:

```
                       RAW GATHERED DATA
                (100+ raw news titles & trends)
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 🔴 STAGE 1: Fast Keyword Blacklist (Throw out junk)       │
│ • Cost: $0, 0ms | Drops sports, movies, drama, scandals   │
└─────────────────────────────┬─────────────────────────────┘
                              │ (~30 items left)
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 🟢 STAGE 2: Positive Niche Scoring (Rule-based)           │
│ • Cost: $0, 1ms | Ranks AI, coding, fintech, investing    │
└─────────────────────────────┬─────────────────────────────┘
                              │ (~10 items left)
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 🧠 STAGE 3: Semantic LLM Classifier (Groq / Fast 0.3s)    │
│ • Groq openai/gpt-oss-120b | PURE_AI, PURE_FINANCE, MIXED │
└─────────────────────────────┬─────────────────────────────┘
                              │ (~5 items left)
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 🔄 STAGE 4: Vector Anti-Duplication (Cosine Similarity)   │
│ • Compares 768-dim embedding against 30-day post memory   │
│ • Drops anything > 80% similar to recent posts            │
└─────────────────────────────┬─────────────────────────────┘
                              │ (~2-3 top candidates)
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 🏆 STAGE 5: Format Fit & Actionability Score              │
│ • Verifies 3-5 concrete educational steps can be built    │
└─────────────────────────────┬─────────────────────────────┘
                              ▼
                     WINNING POST TOPIC
```

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
┌─────────────────────────────────┐
│   5-Stage Filtering Funnel      │
│  (core/funnel.py + memory.py)   │
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

---

## 🩹 Self-Healing by Design

- **Multi-Tier Feed Failover** — RSS feeds automatically fall back to resilient search bridges if rate limits (e.g. 429) occur.
- **Multi-Tier Logo Resolvers** — Logo.dev high-res CDN + Brandfetch Brand API + Google Favicons fallback for crisp tool icons.
- **Retry with Exponential Backoff** — all external network calls use exponential backoff + jitter.
- **Render Validation** — Playwright renders are validated for pixel variance to prevent blank frames.
- **Persistent Semantic Memory** — tracks 30-day post history in `data/post_history.json` and Supabase PostgreSQL to prevent repetitive content.

---

## 📂 Project Structure

```text
ai-social-engine/
├── requirements.txt
├── .env.example
├── README.md
├── core/
│   ├── __init__.py
│   ├── feeds.py           # 4 core feeds (Google Trends, TechCrunch, VentureBeat, Hacker News)
│   ├── funnel.py          # 5-Stage filtering funnel (Blacklist, Niche, LLM, Dedup, Actionability)
│   ├── memory.py          # 30-day post history & vector cosine deduplication
│   ├── generator.py       # Groq (openai/gpt-oss-120b) structured content planner
│   ├── renderer.py        # Playwright 4:5 slide renderer + Logo.dev & Brandfetch resolver
│   ├── publisher.py       # Cloudinary uploader & Meta Graph API publisher
│   ├── database.py        # Supabase PostgreSQL storage & memory sync
│   └── utils.py           # Retry decorator & image validation
├── templates/
│   ├── carousel_slide.html       # Glassmorphic dark-mode educational slide
│   └── single_infographic.html   # Cheatsheet/comparison grid infographic
└── app.py                 # Streamlit control room UI with Funnel & Radar
```

---

## 🚀 Quickstart

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Configure environment
cp .env.example .env
# fill in GROQ_API_KEY, LOGODEV_*, BRANDFETCH_*, CLOUDINARY_*, IG_USER_ID, IG_ACCESS_TOKEN

# 3. Run the demo
streamlit run app.py
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Topic Gathering | Google Trends RSS, TechCrunch AI RSS, VentureBeat AI RSS, Hacker News API |
| Filtering Funnel | Regex Blacklist, Lexicon Scorer, Groq (`openai/gpt-oss-120b`), Cosine Memory |
| Content Intelligence | Groq (`openai/gpt-oss-120b`), structured JSON output (Gemini optional fallback) |
| Brand Assets & Logos | Logo.dev CDN, Brandfetch v2 API, Google Favicons |
| Rendering | Playwright (headless Chromium), Jinja2, CSS Glassmorphism (2160x2700 Retina) |
| Database & Cloud | Supabase PostgreSQL & Vector Embeddings |
| Media Hosting | Cloudinary CDN |
| Publishing | Meta / Instagram Graph API (Single Photo & 5-Slide Carousels) |
| Automation | GitHub Actions Cron + Post History Memory Synchronization |
| Demo UI | Streamlit |

---

## ⏰ Automated Publishing Schedule & Weekly Calendar

The autonomous engine publishes **twice per day** timed around peak engagement windows:

| Slot | Time (IST) | Time (UTC) | GitHub Actions Cron | Content Format |
|---|---|---|---|---|
| 🌅 **Morning Slot** | 7:00 AM IST | 01:30 UTC | `30 1 * * *` | 📸 **Single Photo Cheatsheet / Infographic** |
| 🌆 **Evening Slot (Prime)** | 7:00 PM IST | 13:30 UTC | `30 13 * * *` | 🎨 **Deep Educational Carousel / Architecture Flow** |

### 📅 7-Day Weekly Rotation Matrix

| Day | 🌅 Morning Slot (7:00 AM IST) | 🌆 Evening Slot (7:00 PM IST) | Strategy |
|---|---|---|---|
| **Monday (0)** | 📸 Single Photo Cheatsheet | 📱 5-Slide Tool Listicle | Clean start to the week: Quick tip + 5-slide tool listicle |
| **Tuesday (1)** | 📸 Single Photo Cheatsheet | 🎨 Educational Carousel | Narrative educational breakdown |
| **Wednesday (2)** | 📸 Single Photo Cheatsheet | 📱 5-Slide Tool Listicle | Mid-week boost: Single photo cheatsheet + educational list |
| **Thursday (3)** | 📸 Single Photo Cheatsheet | 🗺️ Architecture Flowchart | Deep technical day: System architecture flow diagram |
| **Friday (4)** | 📸 Single Photo Cheatsheet | 📱 5-Slide Tool Listicle | Weekend prep: Productivity / code cheatsheet + tool listicle |
| **Saturday (5)** | 📸 Single Photo Cheatsheet | 🗺️ Architecture Flowchart | Complex system flow diagram & architecture blueprint |
| **Sunday (6)** | 📸 Single Photo Cheatsheet | 📱 5-Slide Tool Listicle | Weekly recap cheatsheet + educational tool listicle |

### 🛡️ Production Deduplication Guardrails
1. **15-Post Rule**: Topic embedding cannot exceed 0.70 cosine similarity with any of the previous 15 posts.
2. **24h Trend Cooldown**: Topic embedding cannot exceed 0.65 similarity with any post published within the last 24 hours.
3. **30-Day General Memory**: Topic embedding cannot exceed 0.80 similarity with any post across the entire 30-day database.


