from fastapi import FastAPI, HTTPException, BackgroundTasks
from typing import List, Dict
import asyncio
import uvicorn
import uuid
import json
import os
import aiohttp
import aiofiles
from scraper import AnimeScraper
from models import SearchResult, AnimeDetails, DownloadRequest, Episode

app = FastAPI(title="Animecix Scraper API", description="API to scrape animecix.tv")

scraper = AnimeScraper()

# In-memory storage for background tasks (in production use a DB/Redis)
tasks: Dict[str, Dict] = {}

@app.get("/search", response_model=List[SearchResult])
async def search(query: str):
    """
    Search for an anime by name.
    """
    try:
        results = await scraper.search_anime(query)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/details")
async def get_details(url: str):
    """
    Get seasons and episodes list for a given anime URL.
    Does NOT scrape video links yet.
    """
    try:
        details = await scraper.get_anime_details(url)
        return details
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def download_file(url: str, filepath: str):
    """
    Downloads a file from a URL to a local path using aiohttp.
    """
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    async with aiofiles.open(filepath, 'wb') as f:
                        while True:
                            chunk = await response.content.read(1024 * 1024) # 1MB chunks
                            if not chunk:
                                break
                            await f.write(chunk)
                    return True
                else:
                    return False
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return False

async def scrape_all_episodes_task(task_id: str, anime_url: str):
    tasks[task_id]["status"] = "processing"
    try:
        # 1. Get details
        details = await scraper.get_anime_details(anime_url)
        anime_title = details.get("title", "Unknown").replace("/", "-").strip() # sanitize
        tasks[task_id]["anime_title"] = anime_title
        
        all_episodes = []
        for season in details.get("seasons", []):
            for episode in season.get("episodes", []):
                all_episodes.append(episode)
        
        tasks[task_id]["total_episodes"] = len(all_episodes)
        tasks[task_id]["processed"] = 0
        tasks[task_id]["results"] = []

        # 2. Scrape video links one by one and download immediately
        # Using a semaphore to limit concurrent downloads/browser instances
        # Since browser is heavy, we keep batch size small (1 or 2)
        
        semaphore = asyncio.Semaphore(1) # Process 1 by 1 to be safe and avoid rate limits/resource issues

        async def process_episode(ep):
            async with semaphore:
                try:
                    video_url = await scraper.get_video_source(ep["url"])
                    
                    if video_url:
                        # Prepare download path
                        # data/Anime Name/Season X/Episode Y.mp4
                        season_dir = f"Season {ep['season']}"
                        filename = f"{anime_title} - S{ep['season']}E{ep['number']}.mp4"
                        
                        # Sanitize path components
                        # Simple replacement for common illegal chars
                        for char in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
                             filename = filename.replace(char, '')
                        
                        file_path = os.path.join("data", anime_title, season_dir, filename)
                        
                        # Download immediately
                        print(f"Downloading {filename}...")
                        success = await download_file(video_url, file_path)
                        
                        status = "downloaded" if success else "download_failed"
                        
                        return {
                            "series": anime_title,
                            "season": ep["season"],
                            "episode": ep["number"],
                            "page_url": ep["url"],
                            "video_url": video_url,
                            "filename": filename,
                            "local_path": file_path,
                            "status": status
                        }
                    else:
                         return {
                            "season": ep["season"],
                            "episode": ep["number"],
                            "error": "Video URL not found",
                            "status": "failed"
                        }
                        
                except Exception as e:
                    return {
                        "season": ep["season"],
                        "episode": ep["number"],
                        "error": str(e),
                        "status": "error"
                    }
        
        # We can still gather, but the semaphore will limit concurrency
        # Or we can just loop since we want "sequential" feel or controlled parallelism
        # Gather is better so we can just wait for all
        
        # To avoid creating too many futures at once for long series, we can chunk it
        batch_size = 5
        for i in range(0, len(all_episodes), batch_size):
            batch = all_episodes[i:i+batch_size]
            results = await asyncio.gather(*[process_episode(ep) for ep in batch])
            
            tasks[task_id]["results"].extend(results)
            tasks[task_id]["processed"] += len(batch)
            
        tasks[task_id]["status"] = "completed"
        
        # Save results JSON
        filename_json = f"downloads_{task_id}.json"
        with open(filename_json, "w", encoding="utf-8") as f:
            json.dump(tasks[task_id], f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)

@app.post("/download-all")
async def start_download_all(request: DownloadRequest, background_tasks: BackgroundTasks):
    """
    Starts a background task to scrape video links for ALL episodes of the given anime.
    Returns a Task ID to check status.
    """
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "status": "pending",
        "anime_url": request.anime_url
    }
    background_tasks.add_task(scrape_all_episodes_task, task_id, request.anime_url)
    return {"task_id": task_id, "message": "Scraping started in background. Check status with /status/{task_id}"}

@app.get("/status/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
