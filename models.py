from typing import List, Optional

from pydantic import BaseModel


class SearchResult(BaseModel):
    title: str
    url: str


class Episode(BaseModel):
    season: str
    number: str
    url: str
    video_url: Optional[str] = None


class Season(BaseModel):
    season_number: str
    episodes: List[Episode]


class AnimeDetails(BaseModel):
    title: str
    url: str
    seasons: List[Season]


class DownloadRequest(BaseModel):
    anime_url: str


class DownloadResponse(BaseModel):
    anime_title: str
    episodes_found: int
    results: List[Episode]
