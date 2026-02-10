# Animecix Scraper

A FastAPI service that scrapes [animecix.tv](https://animecix.tv) for anime metadata and video links. It exposes REST endpoints to search titles, fetch season and episode lists, and run background jobs to download all episodes of a series.

---

## Prerequisites

- Python 3.10+
- Playwright (uses Chromium for browser automation)

---

## Installation

1. Clone or download the project and enter the directory:

   ```bash
   cd animecix_scraper
   ```

2. Create and activate a virtual environment (recommended):

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Linux / macOS
   # or:  .venv\Scripts\activate   on Windows
   ```

3. Install Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Install Playwright browsers (required for scraping):

   ```bash
   playwright install chromium
   ```

---

## Running the API

Start the server:

```bash
python main.py
```

Or with uvicorn directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

## API Usage

### Search for an anime

**GET** `/search?query=<search term>`

Returns a list of matching titles and their URLs.

Example:

```bash
curl "http://localhost:8000/search?query=shingeki"
```

Response:

```json
[
  { "title": "Shingeki no Kyojin", "url": "https://animecix.tv/titles/25/shingeki-no-kyojin" }
]
```

---

### Get anime details (seasons and episodes)

**GET** `/details?url=<anime page url>`

Returns the anime title, URL, and a list of seasons with their episodes. Does not fetch video links.

Example:

```bash
curl "http://localhost:8000/details?url=https://animecix.tv/titles/25/shingeki-no-kyojin"
```

Response includes `title`, `url`, and `seasons` (each with `season_number` and `episodes` with `season`, `number`, `url`).

---

### Start full download (all episodes)

**POST** `/download-all`

Starts a background task that, for the given anime URL, fetches every episode’s video link and downloads the file. Episodes are saved under `data/<Anime Title>/Season N/`.

Request body:

```json
{
  "anime_url": "https://animecix.tv/titles/25/shingeki-no-kyojin"
}
```

Example:

```bash
curl -X POST "http://localhost:8000/download-all" \
  -H "Content-Type: application/json" \
  -d '{"anime_url": "https://animecix.tv/titles/25/shingeki-no-kyojin"}'
```

Response:

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Scraping started in background. Check status with /status/{task_id}"
}
```

Use the returned `task_id` to poll status.

---

### Check download task status

**GET** `/status/{task_id}`

Returns the current state of the background job: `pending`, `processing`, `completed`, or `failed`. When completed, includes `results` (per-episode info) and a summary. A JSON file `downloads_<task_id>.json` is also written to the project directory when the task completes.

Example:

```bash
curl "http://localhost:8000/status/550e8400-e29b-41d4-a716-446655440000"
```

---

## Project layout

- `main.py` — FastAPI app and route handlers
- `scraper.py` — Animecix scraping (search, details, video source)
- `services.py` — Download logic and background task runner
- `models.py` — Pydantic request/response models
- `data/` — Default directory for downloaded episode files

---

## Notes

- Task state is kept in memory; restarting the server clears it. For production, use a persistent store (e.g. Redis or a database).
- Scraping and downloads are rate-limited (one episode at a time in the current implementation) to reduce load on the target site.
- Ensure you have sufficient disk space and a stable connection when running full-series downloads.
