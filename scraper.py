import asyncio
import re
from playwright.async_api import async_playwright, Page, BrowserContext
from typing import List, Dict, Optional
import urllib.parse

class AnimeScraper:
    def __init__(self):
        self.base_url = "https://animecix.tv"

    async def search_anime(self, query: str) -> List[Dict]:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Navigate to search page
            # Assuming search works via query param or we type in a box
            # Trying direct search url pattern first if known, otherwise using the search bar
            # Common pattern: https://animecix.tv/search?q=...
            encoded_query = urllib.parse.quote(query)
            search_url = f"{self.base_url}/search?q={encoded_query}"
            
            print(f"Searching for: {search_url}")
            await page.goto(search_url)
            await page.wait_for_load_state("networkidle")
            
            results = []
            # Inspecting likely selectors based on standard layouts
            # We need to be flexible here since we haven't seen the HTML
            # I will try to find elements that look like anime cards
            
            # Placeholder selector - will need adjustment based on actual site
            # Usually strictors are like .poster-card or .anime-item
            # Let's try to get all links that contain '/titles/'
            
            links = await page.locator("a[href*='/titles/']").all()
            
            seen_urls = set()
            for link in links:
                href = await link.get_attribute("href")
                if not href:
                    continue
                
                # normalize url
                if not href.startswith("http"):
                    full_url = f"{self.base_url}{href}" if href.startswith("/") else f"{self.base_url}/{href}"
                else:
                    full_url = href
                
                if full_url in seen_urls:
                    continue
                
                # Extract title
                title = await link.inner_text()
                title = title.strip()
                if not title:
                    # try getting title from image alt or title attribute
                    img = link.locator("img")
                    if await img.count() > 0:
                        title = await img.first.get_attribute("alt") or await img.first.get_attribute("title") or "Unknown"
                
                results.append({
                    "title": title,
                    "url": full_url
                })
                seen_urls.add(full_url)
            
            await browser.close()
            return results

    async def get_anime_details(self, anime_url: str) -> Dict:
        """
        Scrapes available seasons and episodes for a given anime URL.
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            print(f"Getting details for: {anime_url}")
            await page.goto(anime_url, wait_until="networkidle")
            
            # Scroll to bottom to trigger any lazy loading
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

            # Extract title
            title = await page.title()
            h1 = page.locator("h1")
            if await h1.count() > 0:
                title = await h1.first.inner_text()
            
            # Find season links
            # Pattern: /titles/{id}/{slug}/season/{num}
            # Or from the debug output: /titles/25/shingeki-no-kyojin/season/1
            
            season_links = []
            
            # We look for links that look like season tabs/cards
            # Debug output showed links with text "Season 1", "Season 2" etc.
            # And href containing "/season/"
            
            # Collect all unique season URLs
            # Use broader selector and filter in python
            all_links = await page.locator("a").all()
            season_urls = set()
            
            print(f"Found {len(all_links)} links total")
            
            for link in all_links:
                href = await link.get_attribute("href")
                if not href:
                    continue
                
                # Check if it is a season overview link (not an episode link)
                # Episode links have "/episode/" in them. Season links usually don't (or end with season/X)
                if "season" in href and "episode" not in href:
                     # normalize
                    full_url = f"{self.base_url}{href}" if href.startswith("/") else href
                    if not full_url.startswith("http"):
                         full_url = f"{self.base_url}/{href}"
                    
                    # Simple heuristic: if it matches .../season/\d+$
                    if re.search(r'/season/\d+$', full_url):
                        print(f"Added season: {full_url}")
                        season_urls.add(full_url)

            # If no season links found (maybe only 1 season?), use current page if it has episodes
            if not season_urls:
                season_urls.add(anime_url)

            seasons_data = []
            
            for s_url in sorted(season_urls):
                print(f"Scraping season: {s_url}")
                try:
                    await page.goto(s_url)
                    await page.wait_for_load_state("domcontentloaded")
                    # Wait a bit for dynamic content
                    await page.wait_for_timeout(1000)
                    
                    # Extract season number from URL
                    s_match = re.search(r'/season/(\d+)', s_url)
                    season_num = s_match.group(1) if s_match else "1"
                    
                    # Find episode links on this page
                    # Debug output: /titles/25/season/4/episode/1
                    episode_links = await page.locator("a[href*='/episode/']").all()
                    
                    current_season_episodes = []
                    seen_eps = set()
                    
                    for link in episode_links:
                        href = await link.get_attribute("href")
                        # Parse episode number
                        # format: .../season/4/episode/1
                        match = re.search(r'/season/(\d+)/episode/(\d+)', href)
                        if match:
                            ep_season = match.group(1)
                            ep_num = match.group(2)
                            
                            # Only add if it matches the season we are currently scraping (if explicit)
                            # or just add everything if we are unsure
                            if ep_season == season_num or len(season_urls) == 1:
                                if ep_num in seen_eps:
                                    continue
                                
                                full_url = f"{self.base_url}{href}" if href.startswith("/") else href
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
                            "episodes": sorted(current_season_episodes, key=lambda x: int(x['number']))
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
        """
        Navigates to the episode page, clicks the play button, and intercepts the video URL.
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            # Use specific User Agent as in debug script
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            page = await context.new_page()
            
            video_url_found = asyncio.Future()
            
            def handle_request(request):
                # Check for video file extensions or m3u8
                url = request.url
                if ".mp4" in url or ".m3u8" in url:
                    if not video_url_found.done():
                        print(f"Video candidate found: {url}")
                        video_url_found.set_result(url)
            
            page.on("request", handle_request)
            
            print(f"Navigating to episode: {episode_url}")
            await page.goto(episode_url)
            await page.wait_for_load_state("domcontentloaded") # networkidle might hang on ads
            
            # User said: "play-button-animation tıklayıp"
            # Try to find and click the play button
            try:
                print("Looking for play button...")
                # Wait for a bit for the player to initialize
                await page.wait_for_timeout(2000)
                
                # Check for various play button selectors
                play_btn = page.locator(".play-button-animation").first
                if await play_btn.count() > 0:
                    print("Clicking .play-button-animation")
                    # Force click might help if overlayed
                    await play_btn.click(force=True)
                else:
                    # Try generic video play buttons or overlay
                    print("Play button not found by class, trying generic search...")
                    # Sometimes it's an overlay
                    overlay = page.locator(".vjs-big-play-button")
                    if await overlay.count() > 0:
                         await overlay.click(force=True)
                    else:
                         # Last resort: click the video element itself
                         video = page.locator("video")
                         if await video.count() > 0:
                             await video.click(force=True)
            except Exception as e:
                print(f"Error clicking play button: {e}")
            
            # Wait for video url to be captured
            try:
                # Increased timeout to 15s to be safe
                video_url = await asyncio.wait_for(video_url_found, timeout=15.0)
            except asyncio.TimeoutError:
                print("Timeout waiting for video URL request. Checking DOM...")
                # Fallback: check <video> tag src
                video_element = page.locator("video")
                if await video_element.count() > 0:
                    video_url = await video_element.first.get_attribute("src")
                    # Sometimes src is blob:..., which is not useful, but better than nothing
                else:
                    video_url = None
            
            await browser.close()
            return video_url

# Helper for main execution (testing)
if __name__ == "__main__":
    scraper = AnimeScraper()
    # Test code would go here
