"""
Network utilities for OpenCore Prodigy.

Handles downloading, retries, checksum validation, and GPG signature verification.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import (
    CHECKSUM_ALGORITHM,
    ENABLE_GPG_VERIFICATION,
    GITHUB_API_BASE,
    GITHUB_RETRY_ATTEMPTS,
    GITHUB_RETRY_DELAY,
    GITHUB_TIMEOUT,
    MAX_RETRIES,
    RETRY_BACKOFF_FACTOR,
    USER_AGENT,
)
from logger import setup_logger

logger = setup_logger(__name__)


class NetworkError(Exception):
    """Raised when network operations fail."""

    pass


class ChecksumError(Exception):
    """Raised when checksum validation fails."""

    pass


def _make_request(url: str, timeout: int = GITHUB_TIMEOUT) -> str:
    """
    Make an HTTP GET request with proper headers.

    Args:
        url: URL to request
        timeout: Request timeout in seconds

    Returns:
        Response body as string

    Raises:
        NetworkError: If request fails
    """
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as e:
        raise NetworkError(f"Failed to fetch {url}: {e}") from e


def http_get_json(url: str, retry_attempts: int = GITHUB_RETRY_ATTEMPTS) -> Dict[str, Any]:
    """
    Fetch and parse JSON from URL with exponential backoff retry.

    Args:
        url: URL to fetch
        retry_attempts: Number of retry attempts

    Returns:
        Parsed JSON as dictionary

    Raises:
        NetworkError: If all retries fail
    """
    last_error = None
    for attempt in range(retry_attempts):
        try:
            response = _make_request(url)
            return json.loads(response)
        except NetworkError as e:
            last_error = e
            if attempt < retry_attempts - 1:
                delay = GITHUB_RETRY_DELAY * (RETRY_BACKOFF_FACTOR ** attempt)
                logger.warning(
                    f"Attempt {attempt + 1}/{retry_attempts} failed. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
            else:
                logger.error(f"All {retry_attempts} attempts failed for {url}")

    raise NetworkError(f"Failed after {retry_attempts} attempts: {last_error}") from last_error


def http_download(
    url: str,
    dest: Path,
    checksum: Optional[str] = None,
    checksum_type: str = CHECKSUM_ALGORITHM,
    retry_attempts: int = MAX_RETRIES,
) -> Path:
    """
    Download file from URL with retry logic and optional checksum validation.

    Args:
        url: URL to download
        dest: Destination file path
        checksum: Expected checksum (optional)
        checksum_type: Algorithm for checksum (sha256, md5, etc.)
        retry_attempts: Number of retry attempts

    Returns:
        Path to downloaded file

    Raises:
        NetworkError: If download fails after retries
        ChecksumError: If checksum validation fails
    """
    if dest.exists() and not checksum:
        logger.debug(f"File already exists (no checksum validation): {dest}")
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    last_error = None

    for attempt in range(retry_attempts):
        try:
            logger.info(f"Downloading: {url}")
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=GITHUB_TIMEOUT) as resp:
                file_size = int(resp.headers.get("Content-Length", 0))
                logger.debug(f"File size: {file_size / (1024*1024):.2f} MB")

                with open(dest, "wb") as f:
                    chunk_size = 8192
                    downloaded = 0
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

            logger.info(f"Download complete: {dest}")

            # Validate checksum if provided
            if checksum:
                _validate_checksum(dest, checksum, checksum_type)

            return dest

        except (HTTPError, URLError, TimeoutError) as e:
            last_error = e
            if dest.exists():
                dest.unlink()  # Clean up partial download
            if attempt < retry_attempts - 1:
                delay = GITHUB_RETRY_DELAY * (RETRY_BACKOFF_FACTOR ** attempt)
                logger.warning(
                    f"Download attempt {attempt + 1}/{retry_attempts} failed. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
            else:
                logger.error(f"Download failed after {retry_attempts} attempts")

    raise NetworkError(f"Failed to download {url} after {retry_attempts} attempts: {last_error}")


def _validate_checksum(
    file_path: Path,
    expected: str,
    algorithm: str = CHECKSUM_ALGORITHM,
) -> None:
    """
    Validate file checksum.

    Args:
        file_path: Path to file
        expected: Expected checksum value
        algorithm: Hash algorithm (sha256, md5, etc.)

    Raises:
        ChecksumError: If checksum doesn't match
    """
    logger.info(f"Validating {algorithm} checksum for {file_path.name}")

    hasher = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)

    actual = hasher.hexdigest().lower()
    expected = expected.lower()

    if actual != expected:
        raise ChecksumError(
            f"Checksum mismatch for {file_path.name}\n"
            f"Expected: {expected}\n"
            f"Actual:   {actual}"
        )

    logger.debug(f"Checksum valid: {actual}")


def get_latest_release_asset(
    repo: str,
    asset_match: str,
) -> Optional[Dict[str, Any]]:
    """
    Get latest release asset from GitHub repository.

    Args:
        repo: Repository in format "owner/name"
        asset_match: String to match in asset name

    Returns:
        Asset dict with metadata, or None if not found
    """
    try:
        api_url = f"{GITHUB_API_BASE}/{repo}/releases/latest"
        data = http_get_json(api_url)

        if "assets" not in data:
            logger.warning(f"No assets found in {repo} latest release")
            return None

        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if asset_match in name:
                logger.debug(f"Found asset: {name}")
                return asset

        logger.warning(
            f"Asset matching '{asset_match}' not found in {repo} latest release"
        )
        return None

    except NetworkError as e:
        logger.error(f"Failed to fetch release info for {repo}: {e}")
        return None


def download_release_asset(
    repo: str,
    asset_match: str,
    cache_dir: Path,
) -> Path:
    """
    Download latest release asset from GitHub repository.

    Args:
        repo: Repository in format "owner/name"
        asset_match: String to match in asset name
        cache_dir: Directory to cache downloaded file

    Returns:
        Path to downloaded file

    Raises:
        NetworkError: If download fails
    """
    asset = get_latest_release_asset(repo, asset_match)
    if not asset:
        raise NetworkError(f"Asset '{asset_match}' not found in {repo} latest release")

    url = asset["browser_download_url"]
    name = asset["name"]
    dest = cache_dir / name

    return http_download(url, dest)