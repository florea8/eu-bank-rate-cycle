import hashlib
import logging
from pathlib import Path

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from bankcycle.settings import get_settings

log = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, requests.HTTPError):
        return exc.response is not None and exc.response.status_code >= 500
    return isinstance(exc, (requests.ConnectionError, requests.Timeout))


def _raise_for_status(resp: requests.Response) -> None:
    if resp.status_code >= 400:
        raise requests.HTTPError(f"HTTP {resp.status_code} for {resp.url}", response=resp)


with_retries = retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, max=20),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)


@with_retries
def get(url: str, params: dict | None = None) -> requests.Response:
    """GET with 3 retries on 5xx and network errors. 4xx fails at once."""
    resp = requests.get(url, params=params, timeout=get_settings().http_timeout_s)
    _raise_for_status(resp)
    return resp


@with_retries
def download(url: str, dest: Path) -> str:
    """Stream url into dest and return the SHA-256 of what was written."""
    digest = hashlib.sha256()
    with requests.get(url, stream=True, timeout=get_settings().http_timeout_s) as resp:
        _raise_for_status(resp)
        with dest.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                digest.update(chunk)
    return digest.hexdigest()
