import asyncio
import json
import os
from typing import Dict

import aiofiles
import aiohttp

from scraper import AnimeScraper


_tasks_store: Dict[str, Dict] = {}


async def download_file(url: str, filepath: str) -> bool:
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return False
                async with aiofiles.open(filepath, "wb") as f:
                    while True:
                        chunk = await response.content.read(1024 * 1024)
                        if not chunk:
                            break
                        await f.write(chunk)
                return True
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return False


def _sanitize_filename(name: str) -> str:
    for char in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
        name = name.replace(char, '')
    return name


async def scrape_all_episodes_task(task_id: str, anime_url: str, tasks: Dict[str, Dict]):
    scraper = AnimeScraper()
    tasks[task_id]["status"] = "processing"
    try:
        details = await scraper.get_anime_details(anime_url)
        anime_title = details.get("title", "Unknown").replace("/", "-").strip()
        tasks[task_id]["anime_title"] = anime_title

        all_episodes = []
        for season in details.get("seasons", []):
            for episode in season.get("episodes", []):
                all_episodes.append(episode)

        tasks[task_id]["total_episodes"] = len(all_episodes)
        tasks[task_id]["processed"] = 0
        tasks[task_id]["results"] = []

        semaphore = asyncio.Semaphore(1)
        batch_size = 5

        async def process_episode(ep):
            async with semaphore:
                try:
                    video_url = await scraper.get_video_source(ep["url"])
                    if not video_url:
                        return {
                            "season": ep["season"],
                            "episode": ep["number"],
                            "error": "Video URL not found",
                            "status": "failed"
                        }
                    season_dir = f"Season {ep['season']}"
                    raw_filename = f"{anime_title} - S{ep['season']}E{ep['number']}.mp4"
                    filename = _sanitize_filename(raw_filename)
                    file_path = os.path.join("data", anime_title, season_dir, filename)

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
                except Exception as e:
                    return {
                        "season": ep["season"],
                        "episode": ep["number"],
                        "error": str(e),
                        "status": "error"
                    }

        for i in range(0, len(all_episodes), batch_size):
            batch = all_episodes[i:i + batch_size]
            results = await asyncio.gather(*[process_episode(ep) for ep in batch])
            tasks[task_id]["results"].extend(results)
            tasks[task_id]["processed"] += len(batch)

        tasks[task_id]["status"] = "completed"
        filename_json = f"downloads_{task_id}.json"
        with open(filename_json, "w", encoding="utf-8") as f:
            json.dump(tasks[task_id], f, ensure_ascii=False, indent=2)

    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)


def get_tasks_store() -> Dict[str, Dict]:
    return _tasks_store
