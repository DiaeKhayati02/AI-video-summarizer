# YT Summariser — Claude Code Project Spec

## What we're building
A full-stack AI-powered YouTube video summariser and Q&A chatbot.
- Paste a YouTube URL → get a structured summary
- Ask questions about the video → get answers with memory

---

## Stack

### Frontend
- Vanilla HTML + CSS + JavaScript (no frameworks)
- Communicates with backend via `fetch()` calls
- Deployed on Vercel

### Backend
- Python + FastAPI
- Two endpoints: `POST /summarise` and `POST /chat`
- Deployed on Render (free Web Service, deployed via `render.yaml` blueprint) using the existing Dockerfile

### AI Layer (LangChain — current LCEL-style API, not the legacy `langchain.chains`/`langchain.memory` API)
- `youtube-transcript-api` — fetches video transcripts (no YouTube API key needed); video duration is derived from the last transcript snippet's `start + duration`, not a separate API call
- Video title/channel name come from YouTube's public oEmbed endpoint (`youtube.com/oembed`) — no API key needed, but also no subscriber count (that requires the quota-limited YouTube Data API v3, which this project deliberately doesn't use)
- `langchain_text_splitters.RecursiveCharacterTextSplitter` — chunks transcripts, only invoked when a transcript exceeds the model's context budget
- Summarisation via `PromptTemplate | llm.with_structured_output(VideoSummary)` (LCEL): single call by default, returning `{description, key_takeaways, suggested_questions}`; falls back to a hand-rolled map-reduce (map each chunk to plain text, then one structured combine call) only for transcripts too long to fit in context
- Q&A via `PromptTemplate | llm`; chat history is capped to the last N turns, read straight from the `messages` table (no live memory object — see `memory.py`)
- All prompt templates live in `prompts.py` (built on `langchain_core.prompts.PromptTemplate`)
- Note: `langchain` 1.x removed `load_summarize_chain`, `LLMChain`, and `langchain.memory` from the top-level package — don't reintroduce them. Depend directly on `langchain-core`, `langchain-text-splitters`, and `langchain-google-genai`.

### LLM
- `gemini-flash-latest` (primary) via `langchain-google-genai` — Google's rolling alias to the current stable Flash model, so it doesn't rot when specific model versions get retired (`gemini-1.5-flash` was removed from the API entirely mid-project)
- Model is configurable via `.env` (`MODEL_NAME`) so it can be swapped (e.g. to an OpenAI model) without code changes

### Database
- Supabase (hosted PostgreSQL)
- ORM: SQLAlchemy + psycopg2
- Two tables: `videos` and `messages` (see schema below)
- Connection via `DATABASE_URL` in `.env`

### Local Dev
- Docker Compose with 2 services: `backend` + `frontend` (nginx:alpine)
- Supabase is external — no local DB container needed

### Env Management
- `python-dotenv` locally
- Render environment variables in production
- Vercel environment variables for frontend (if needed)

---

## Folder Structure

```
yt-summariser/
├── backend/
│   ├── main.py            # FastAPI app, CORS, route registration
│   ├── transcript.py      # youtube-transcript-api logic + error handling
│   ├── pipeline.py        # LangChain summarise chain + Q&A chain
│   ├── memory.py          # windowed/summary memory setup per session
│   ├── prompts.py         # All prompt templates (summarise + Q&A)
│   ├── database.py        # SQLAlchemy engine, session, models
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .dockerignore      # must live here, not at repo root — this is the Docker build context
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js             # fetch() calls, DOM updates, chat rendering
├── docker-compose.yml
├── .env                   # Never committed
├── .env.example           # Committed — shows required keys
└── README.md
```

---

## Database Schema

### `videos` table
```sql
CREATE TABLE videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    youtube_url TEXT NOT NULL,
    video_id TEXT NOT NULL UNIQUE,   -- extracted from URL
    transcript TEXT,                  -- raw transcript text
    summary TEXT,                     -- generated summary
    created_at TIMESTAMP DEFAULT now()
);
```

### `messages` table
```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT now()
);
```

---

## API Endpoints

### `POST /summarise`
**Request:**
```json
{ "url": "https://www.youtube.com/watch?v=..." }
```
**Behaviour:**
1. Extract video_id from URL
2. Check `videos` table — if a structured summary is already cached (JSON-encoded in `videos.summary`), return it
3. If not: fetch transcript + duration, look up title/channel via YouTube's oEmbed endpoint (no API key needed), run the structured-output summarise call, cache the JSON blob in `videos.summary`, return
**Response:**
```json
{
  "video_id": "abc123",
  "title": "...",
  "channel_name": "...",
  "duration_seconds": 754,
  "description": "...",
  "key_takeaways": ["...", "..."],
  "suggested_questions": ["...", "..."],
  "cached": false
}
```
Note: `summarise_transcript()` in `pipeline.py` returns this shape via `llm.with_structured_output(VideoSummary)` (a Pydantic model), not free-form markdown — this is deliberately more reliable than asking the model for markdown and parsing it, since the sidebar UI needs the description and key takeaways as distinct fields, not prose.

### `POST /chat`
**Request:**
```json
{
  "video_id": "abc123",
  "question": "What did they say about X?"
}
```
**Behaviour:**
1. Load transcript from DB by video_id
2. Load message history from `messages` table for this video_id
3. Rebuild memory from history, capped to the last N turns (or summarised if older)
4. Run Q&A chain with transcript as context + memory
5. Save user message + assistant response to `messages` table
6. Return answer
**Response:**
```json
{ "answer": "..." }
```

### `GET /history/{video_id}`
Returns all messages for a given video so the frontend can restore chat on page reload.

### `GET /health`
Returns `{ "status": "ok" }` — used by Render for health checks.

---

## Environment Variables

```env
# .env.example

# LLM
GOOGLE_API_KEY=your_key_here
MODEL_NAME=gemini-flash-latest   # Google's rolling alias to the current stable Flash model

# Supabase
DATABASE_URL=postgresql://postgres:[password]@db.[project].supabase.co:5432/postgres

# App
BACKEND_URL=http://localhost:8000   # overridden in production
```

---

## Docker Setup

### backend/Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml
```yaml
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./backend:/app

  frontend:
    image: nginx:alpine
    ports:
      - "3000:80"
    volumes:
      - ./frontend:/usr/share/nginx/html
```

---

## Frontend Behaviour

### `index.html` layout
- Top section: URL input + "Summarise" button
- Middle section: Summary panel (rendered after summarise call)
- Bottom section: Chat panel — message input + conversation history

### `app.js` structure
Organise into clear functions:
```
fetchSummary(url)         → POST /summarise → calls renderSummary()
fetchAnswer(videoId, q)   → POST /chat → calls renderMessage()
loadHistory(videoId)      → GET /history/:videoId → restores chat
renderSummary(data)       → updates summary panel DOM
renderMessage(msg, role)  → appends chat bubble to chat panel
showLoading(bool)         → toggles loading state on buttons
showError(msg)            → displays error banner
```

### UX requirements
- Loading state on the Summarise button while waiting (LLM takes a few seconds)
- Loading state on the Send button while waiting for chat response
- If the video has no transcript, show a clear error: "This video has no available transcript."
- If the video was already summarised (cached: true), show a small "Cached" badge
- Chat bubbles: user messages right-aligned, assistant messages left-aligned
- Textarea for question input that submits on Enter (Shift+Enter for newline)

---

## Key Design Decisions to Implement Correctly

1. **Transcript caching** — always check `videos` table before fetching + running LLM. Same video should never cost two API calls.

2. **Adaptive summarisation** — check transcript token length first. If it fits in the model's context window (Gemini Flash's is very large, so most 1-2hr videos will), use `chain_type="stuff"` — one LLM call, cheaper, and keeps narrative coherence. Only fall back to `chain_type="map_reduce"` (or `refine`) for the rare transcript that actually exceeds the context budget. Unconditional `map_reduce` wastes calls and can fragment the summary across chunks.

3. **Memory reconstruction, capped** — don't store a live memory object. Rebuild the chat history from DB messages on every `/chat` request (stateless, works with Render's ephemeral containers) — but don't load the *full* history unbounded, since long chat threads would eventually blow the context window too. `memory.py` queries only the last N turns from Postgres and formats them into the prompt directly.

4. **CORS** — add `CORSMiddleware` to FastAPI allowing the Vercel frontend origin. In dev, allow `http://localhost:3000`.

5. **Video ID extraction** — handle multiple YouTube URL formats:
   - `https://www.youtube.com/watch?v=VIDEO_ID`
   - `https://youtu.be/VIDEO_ID`
   - `https://www.youtube.com/embed/VIDEO_ID`

6. **Error handling** — wrap transcript fetch in try/except. `youtube-transcript-api` raises `TranscriptsDisabled` and `NoTranscriptFound` for videos that genuinely lack captions — catch both, return a 400. Separately, it raises `RequestBlocked`/`IpBlocked` when YouTube blocks the *server's* IP (near-universal on cloud hosts — Render, Railway, AWS, GCP, etc. all get blocked, since YouTube blocklists datacenter IP ranges broadly, not any specific provider) — catch this separately and return a 503, since it's an infra issue, not a bad video. The most reliable fix is routing through a *residential* rotating proxy — datacenter proxies, including Webshare's own free tier, get blocked the same way an unproxied cloud host does. `transcript.py`'s `_build_transcript_api()` supports either `TRANSCRIPT_PROXY_URL` (a generic proxy URL, e.g. a scraping API's proxy-mode endpoint — note these typically intercept TLS, so the session disables cert verification, an inherent tradeoff of that approach) or `WEBSHARE_PROXY_USERNAME`/`PASSWORD` for a residential Webshare plan specifically. Community reports suggest even paid residential proxies aren't a guaranteed fix against YouTube's blocking — verify whichever option is configured actually works before relying on it.

---

## requirements.txt

```
fastapi
uvicorn
python-dotenv
langchain-core
langchain-text-splitters
langchain-google-genai
youtube-transcript-api
requests
sqlalchemy
psycopg2-binary
pydantic
```

---

## Build Order

Build in this exact order to avoid blocked dependencies:

1. `database.py` — models + engine + session first
2. `transcript.py` — pure function, no dependencies
3. `prompts.py` — pure strings, no dependencies
4. `pipeline.py` — depends on prompts
5. `memory.py` — depends on database
6. `main.py` — wires everything together
7. Frontend — build after backend endpoints are working and testable via curl/Postman

---

## README must include

- Project description + demo screenshot
- Local setup instructions (`docker compose up`)
- Environment variables guide
- Architecture diagram description
- Design decisions section explaining: why adaptive stuff/map_reduce, why capped memory reconstruction, why transcript caching
- Deployment guide (Render + Vercel + Supabase)
```
