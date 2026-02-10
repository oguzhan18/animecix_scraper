import asyncio
import re
import urllib.parse

from playwright.async_api import async_playwright
from typing import List, Dict, Optional


class AnimeScraper:
    def __init__(self):
        self.base_url = "https://animecix.tv"

    def _normalize_url(self, href: str) -> str:
        if href.startswith("http"):
            return href
        return f"{self.base_url}{href}" if href.startswith("/") else f"{self.base_url}/{href}"

    async def search_anime(self, query: str) -> List[Dict]:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            encoded_query = urllib.parse.quote(query)
            search_url = f"{self.base_url}/search?q={encoded_query}"
            await page.goto(search_url)
            await page.wait_for_load_state("networkidle")

            results = []
            links = await page.locator("a[href*='/titles/']").all()
            seen_urls = set()

            for link in links:
                href = await link.get_attribute("href")
                if not href:
                    continue
                full_url = self._normalize_url(href)
                if full_url in seen_urls:
                    continue

                title = await link.inner_text()
                title = title.strip()
                if not title:
                    img = link.locator("img")
                    if await img.count() > 0:
                        title = (
                            await img.first.get_attribute("alt")
                            or await img.first.get_attribute("title")
                            or "Unknown"
                        )

                results.append({"title": title, "url": full_url})
                seen_urls.add(full_url)

            await browser.close()
            return results

    async def get_anime_details(self, anime_url: str) -> Dict:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(anime_url, wait_until="networkidle")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

            title = await page.title()
            h1 = page.locator("h1")
            if await h1.count() > 0:
                title = await h1.first.inner_text()

            all_links = await page.locator("a").all()
            season_urls = set()

            for link in all_links:
                href = await link.get_attribute("href")
                if not href or "season" not in href or "episode" in href:
                    continue
                full_url = self._normalize_url(href)
                if not full_url.startswith("http"):
                    full_url = f"{self.base_url}/{href}"
                if re.search(r'/season/\d+$', full_url):
                    season_urls.add(full_url)

            if not season_urls:
                season_urls.add(anime_url)

            seasons_data = []

            for s_url in sorted(season_urls):
                try:
                    await page.goto(s_url)
                    await page.wait_for_load_state("domcontentloaded")
                    await page.wait_for_timeout(1000)

                    s_match = re.search(r'/season/(\d+)', s_url)
                    season_num = s_match.group(1) if s_match else "1"
                    episode_links = await page.locator("a[href*='/episode/']").all()
                    current_season_episodes = []
                    seen_eps = set()

                    for link in episode_links:
                        href = await link.get_attribute("href")
                        match = re.search(r'/season/(\d+)/episode/(\d+)', href or "")
                        if not match:
                            continue
                        ep_season = match.group(1)
                        ep_num = match.group(2)
                        if ep_season != season_num and len(season_urls) != 1:
                            continue
                        if ep_num in seen_eps:
                            continue

                        full_url = self._normalize_url(href or "")
                        if not full_url.startswith("http"):
                            full_url = f"{self.base_url}/{href}"
                        current_season_episodes.append({
                            "season": ep_season,
                            "number": ep_num,
                            "url": full_url
                        })
                        seen_eps.add(ep_num)

                    if current_season_episodes:
                        seasons_data.append({
                            "season_number": season_num,
                            "episodes": sorted(
                                current_season_episodes,
                                key=lambda x: int(x["number"])
                            )
                        })
                except Exception as e:
                    print(f"Error scraping season {s_url}: {e}")

            await browser.close()
            return {
                "title": title,
                "url": anime_url,
                "seasons": seasons_data
            }

    async def get_video_source(self, episode_url: str) -> Optional[str]:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            page = await context.new_page()
            video_url_found = asyncio.Future()

            def handle_request(request):
                url = request.url
                if ".mp4" in url or ".m3u8" in url:
                    if not video_url_found.done():
                        video_url_found.set_result(url)

            page.on("request", handle_request)
            await page.goto(episode_url)
            await page.wait_for_load_state("domcontentloaded")

            try:
                await page.wait_for_timeout(2000)
                play_btn = page.locator(".play-button-animation").first
                if await play_btn.count() > 0:
                    await play_btn.click(force=True)
                else:
                    overlay = page.locator(".vjs-big-play-button")
                    if await overlay.count() > 0:
                        await overlay.click(force=True)
                    else:
                        video = page.locator("video")
                        if await video.count() > 0:
                            await video.click(force=True)
            except Exception as e:
                print(f"Error clicking play button: {e}")

            try:
                video_url = await asyncio.wait_for(video_url_found, timeout=15.0)
            except asyncio.TimeoutError:
                video_element = page.locator("video")
                if await video_element.count() > 0:
                    video_url = await video_element.first.get_attribute("src")
                else:
                    video_url = None

            await browser.close()
            return video_url
