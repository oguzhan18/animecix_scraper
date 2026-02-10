import uuid

from fastapi import FastAPI, HTTPException, BackgroundTasks

from typing import List

from models import SearchResult, DownloadRequest
from scraper import AnimeScraper
from services import get_tasks_store, scrape_all_episodes_task

app = FastAPI(title="Animecix Scraper API", description="API to scrape animecix.tv")

scraper = AnimeScraper()
tasks = get_tasks_store()


@app.get("/search", response_model=List[SearchResult])
async def search(query: str):
    try:
        return await scraper.search_anime(query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/details")
async def get_details(url: str):
    try:
        return await scraper.get_anime_details(url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/download-all")
async def start_download_all(request: DownloadRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "status": "pending",
        "anime_url": request.anime_url
    }
    background_tasks.add_task(scrape_all_episodes_task, task_id, request.anime_url, tasks)
    return {
        "task_id": task_id,
        "message": "Scraping started in background. Check status with /status/{task_id}"
    }


@app.get("/status/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
