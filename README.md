# AI Video Summarizer

Paste a YouTube link, get a structured summary, then ask questions about the video and get answers grounded in its transcript.

**Live**: [ai-video-summarizer-five.vercel.app](https://ai-video-summarizer-five.vercel.app/)

<!-- TODO: add a screenshot/GIF of the app here, e.g.:
![App screenshot](docs/screenshot.png)
-->

## Features

- Paste a YouTube URL → get a description, key takeaways, and tailored suggested questions
- Ask follow-up questions about the video, answered from its transcript with conversation memory
- Video thumbnail, title, channel, and duration pulled in automatically
- Same video is never re-summarised twice — cached in Postgres
- Markdown responses (bold, bullet points) rendered properly, not shown as raw `**`/`*`

## Architecture

```
┌──────────────┐         ┌───────────────────────┐         ┌─────────────┐
│  Frontend     │  HTTPS  │  Backend                │         │  Supabase    │
│  (Vercel)     │ ──────► │  (Render, FastAPI)       │ ──────► │  Postgres    │
│  vanilla HTML/│ ◄────── │                           │ ◄────── │              │
│  CSS/JS       │  JSON   │                           │         │              │
└──────────────┘         └───────────┬─────────────┘         └─────────────┘
                                       │
                                       ├──► YouTube (transcript + oEmbed metadata)
                                       └──► Google Gemini (summarise / answer)
```

The frontend only ever talks to the FastAPI backend — never directly to Gemini, YouTube, or the database. Both `GOOGLE_API_KEY` and `DATABASE_URL` live server-side only.

Backend is stateless between requests: chat history is rebuilt from Postgres on every `/chat` call rather than kept in memory, since the container can restart at any time (deploys, free-tier sleep/wake cycles) and any in-memory state would just vanish.

## Tech stack

| Layer | Tech |
|---|---|
| Frontend | Vanilla HTML/CSS/JS, no framework, no build step |
| Backend | Python, FastAPI |
| AI | Gemini (`gemini-flash-latest`) via `langchain-google-genai`, structured output via Pydantic |
| Database | Supabase (Postgres) via SQLAlchemy |
| Transcripts | `youtube-transcript-api` |
| Hosting | Vercel (frontend) + Render (backend) + Supabase (DB) — all free tier |

## Local development

Requires Docker.

```bash
cp .env.example .env
# fill in GOOGLE_API_KEY and DATABASE_URL in .env
docker compose up
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000 (`/health` should return `{"status":"ok"}`)

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `GOOGLE_API_KEY` | Yes | From [Google AI Studio](https://aistudio.google.com/apikey) |
| `MODEL_NAME` | No | Defaults to `gemini-flash-latest`, Google's rolling alias to the current stable Flash model |
| `DATABASE_URL` | Yes | Supabase Postgres connection string |
| `FRONTEND_ORIGIN` | Yes (prod) | Comma-separated allowed CORS origins, e.g. `http://localhost:3000,https://your-app.vercel.app` |
| `TRANSCRIPT_PROXY_URL` / `WEBSHARE_PROXY_USERNAME`+`PASSWORD` | Only on cloud hosts | See [Deploying](#deploying) — YouTube blocks transcript requests from datacenter IPs |

See `.env.example` for the full list with comments.

## Design decisions

**Adaptive stuff vs. map-reduce summarisation.** Gemini Flash's context window is large enough that almost every video transcript fits in a single call. `pipeline.py` only falls back to splitting the transcript into chunks, summarising each, and combining them when a transcript exceeds a 400,000-character threshold — avoiding the extra Gemini calls (and the risk of a summary fragmented across chunks) that unconditional map-reduce would cost on every single video.

**Structured output over markdown parsing.** The summarise endpoint asks Gemini for `{description, key_takeaways, suggested_questions}` via `llm.with_structured_output()` — a real API-level constraint on the model's response shape, not a summary the backend then tries to regex-parse. This is what lets the frontend render a clean bulleted sidebar and per-video suggested-question chips without fragile text parsing.

**Capped, rebuilt-from-DB chat memory.** `/chat` never holds a live memory object — it re-reads the last 8 turns from the `messages` table on every request. This is both what makes the backend safely stateless across container restarts, and what stops a long conversation from eventually blowing the prompt's context budget the way an unbounded full-history replay would.

**Transcript + summary caching.** The `videos` table caches the transcript and the full structured summary (as JSON) keyed by `video_id`. The same video is never fetched from YouTube or sent to Gemini twice — a repeat `/summarise` call for an already-seen video is a single indexed DB read.

## Deploying

The app is split across three free services. None of this requires a paid tier, though see the note on YouTube IP-blocking below.

### Supabase (database)

Create a project, run the schema from `CLAUDE.md`, and copy the connection string into `DATABASE_URL`.

### Backend on Render

1. [render.com](https://render.com) → sign up with GitHub
2. **New +** → **Blueprint** → select this repo (Render reads `render.yaml` at the repo root)
3. It'll prompt for `GOOGLE_API_KEY` and `DATABASE_URL` — provide both, leave `FRONTEND_ORIGIN` blank for now
4. Once live, note the service URL

**YouTube blocks transcript requests from cloud/datacenter IPs** — this affects every cloud host equally (Render, Railway, AWS, GCP, etc.), not Render specifically. If `/summarise` fails with a 503 mentioning the server's IP being blocked, add a proxy:
- Sign up at [scraperapi.com](https://www.scraperapi.com) (free tier, no card)
- Set `TRANSCRIPT_PROXY_URL=http://scraperapi:YOUR_API_KEY@proxy-server.scraperapi.com:8001` on the Render service
- This is a best-effort free workaround, not a guaranteed one — YouTube's blocking is adversarial and evolves. A paid *residential* Webshare plan (`WEBSHARE_PROXY_USERNAME`/`PASSWORD`) is the more reliable fallback if needed.

### Frontend on Vercel

1. [vercel.com](https://vercel.com) → sign up with GitHub
2. **Add New** → **Project** → import this repo
3. **Root Directory** → `frontend`, framework preset **Other** (static files, no build step)
4. Deploy

### Wire them together

- In `frontend/app.js`, set `PROD_BACKEND_URL` to your actual Render URL
- On Render, set `FRONTEND_ORIGIN` to include your Vercel URL (comma-separated with `localhost:3000` if you want both to keep working)

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/summarise` | POST | `{url}` → video metadata, description, key takeaways, suggested questions |
| `/chat` | POST | `{video_id, question}` → `{answer}` |
| `/history/{video_id}` | GET | Full chat history for a video |
| `/health` | GET | Health check |

## Known limitations

- No subscriber count in the sidebar — that requires the quota-limited YouTube Data API v3 (a separate API key), which this project deliberately avoids
- Render's free tier sleeps after 15 minutes idle; the first request after that takes 30-50s to wake up
- Transcript fetching depends on YouTube not blocking the backend's IP — see the deployment note above
