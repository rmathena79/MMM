from __future__ import annotations

import logging
import time
from pathlib import Path

import requests

from .common import DATA_RAW, STANDARD_USER_AGENT, slugify, timestamp_slug

LOGGER = logging.getLogger(__name__)


class CachedSession:
    def __init__(self, metadata: dict, sleep_seconds: float = 0.5):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': STANDARD_USER_AGENT})
        self.sleep_seconds = sleep_seconds
        self.metadata = metadata

    def get_text(self, url: str, cache_group: str, force_refresh: bool = False) -> tuple[str, Path]:
        cache_dir = DATA_RAW / cache_group
        cache_dir.mkdir(parents=True, exist_ok=True)
        slug = slugify(url)
        existing = sorted(cache_dir.glob(f'{slug}_*.html'))
        if existing and not force_refresh:
            LOGGER.info('Cache hit for %s', url)
            self.metadata.setdefault('fetches', []).append(
                {'url': url, 'cache_group': cache_group, 'cache_hit': True, 'path': str(existing[-1])}
            )
            return existing[-1].read_text(encoding='utf-8'), existing[-1]

        LOGGER.info('Fetching %s', url)
        response = self.session.get(url, timeout=60)
        response.raise_for_status()
        path = cache_dir / f'{slug}_{timestamp_slug()}.html'
        path.write_text(response.text, encoding='utf-8')
        self.metadata.setdefault('fetches', []).append(
            {
                'url': url,
                'cache_group': cache_group,
                'cache_hit': False,
                'path': str(path),
                'status_code': response.status_code,
            }
        )
        time.sleep(self.sleep_seconds)
        return response.text, path
