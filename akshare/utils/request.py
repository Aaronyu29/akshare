# !/usr/bin/env python
"""
Date: 2025/12/31
Desc: HTTP request utilities.
"""

import random
import re
import time
from typing import Dict, Tuple
from urllib.parse import urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://quote.eastmoney.com/",
}


def _eastmoney_push2_fallback_url(url: str) -> str | None:
    parsed_url = urlparse(url)
    if re.fullmatch(r"\d+\.push2\.eastmoney\.com", parsed_url.netloc):
        return urlunparse(parsed_url._replace(netloc="push2.eastmoney.com"))
    return None


def request_with_retry(
    url: str,
    params: Dict = None,
    timeout: int = 15,
    max_retries: int = 3,
    base_delay: float = 1.0,
    random_delay_range: Tuple[float, float] = (0.5, 1.5),
) -> requests.Response:
    """
    HTTP GET with retries.
    :param url: request URL
    :type url: str
    :param params: request parameters
    :type params: dict
    :param timeout: timeout in seconds
    :type timeout: int
    :param max_retries: max retries
    :type max_retries: int
    :param base_delay: base exponential backoff delay in seconds
    :type base_delay: float
    :param random_delay_range: random jitter range in seconds
    :type random_delay_range: tuple
    :return: Response object
    :rtype: requests.Response
    :raises: last request exception
    """
    last_exception = None
    fallback_url = _eastmoney_push2_fallback_url(url)
    if fallback_url is not None:
        urls = [fallback_url, url]
    else:
        urls = [url]

    for current_url in urls:
        for attempt in range(max_retries):
            try:
                with requests.Session() as session:
                    adapter = HTTPAdapter(pool_connections=1, pool_maxsize=1)
                    session.mount("http://", adapter)
                    session.mount("https://", adapter)

                    response = session.get(
                        current_url,
                        params=params,
                        headers=DEFAULT_HEADERS,
                        timeout=timeout,
                    )
                    response.raise_for_status()
                    return response

            except (requests.RequestException, ValueError) as exc:
                last_exception = exc

                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt) + random.uniform(
                        *random_delay_range
                    )
                    time.sleep(delay)

    raise last_exception
