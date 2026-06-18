import time
import random
import logging
import urllib.parse
from typing import Dict, Any

import requests
from requests.exceptions import ConnectionError, Timeout, HTTPError

# Set up logging
logger = logging.getLogger(__name__)

# Predefined realistic fallback User-Agent strings (in case fake_useragent fails or is offline)
FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
]

# Initialize fake_useragent and get 5 realistic user-agents
USER_AGENTS = []
try:
    # pyrefly: ignore [missing-import]
    from fake_useragent import UserAgent
    ua = UserAgent()
    # Populate with 5 different realistic browsers/platforms
    USER_AGENTS = [
        ua.chrome,
        ua.firefox,
        ua.safari,
        ua.edge,
        ua.opera
    ]
    # Filter out empty or None values, ensuring we have valid strings
    USER_AGENTS = [str(agent) for agent in USER_AGENTS if agent]
    
    # If we couldn't get exactly 5, pad or replace with fallbacks
    if len(USER_AGENTS) < 5:
        logger.warning("fake_useragent returned fewer than 5 user agents. Using fallbacks.")
        USER_AGENTS = FALLBACK_USER_AGENTS
    else:
        logger.info("Successfully loaded 5 realistic user agents from fake_useragent.")
except Exception as e:
    logger.warning(f"Failed to initialize fake_useragent ({e}). Using hardcoded fallback user agents.")
    USER_AGENTS = FALLBACK_USER_AGENTS


def get_random_user_agent() -> str:
    """
    Selects and returns a user agent from the pool of 5 realistic user-agent strings.
    
    Returns:
        A user-agent string.
    """
    ua_string = random.choice(USER_AGENTS)
    logger.debug(f"Selected user-agent: {ua_string}")
    return ua_string


def fetch_html(url: str) -> Dict[str, Any]:
    """
    Fetches the HTML content of the given URL with user-agent rotation,
    random delays, and robust error handling.
    
    Args:
        url: The URL to fetch.
        
    Returns:
        A dictionary containing the URL, HTML content, status code, fetch time, and error.
        Format:
        {
            "url": str,
            "html": str or None,
            "status_code": int or None,
            "fetch_time_ms": int or None,
            "error": str or None
        }
    """
    logger.info(f"Preparing to fetch HTML from URL: {url}")
    
    # 1. Add random delay between 1-3 seconds
    delay = random.uniform(1.0, 3.0)
    logger.info(f"Applying random delay of {delay:.2f} seconds before fetching...")
    time.sleep(delay)
    
    # 2. Rotate user-agent
    user_agent = get_random_user_agent()
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.google.com/"
    }
    
    result = {
        "url": url,
        "html": None,
        "status_code": None,
        "fetch_time_ms": None,
        "error": None
    }
    
    start_time = time.perf_counter()
    try:
        logger.info(f"Sending GET request to {url} (Timeout: 10s)")
        response = requests.get(url, headers=headers, timeout=10.0)
        
        # Raise HTTPError if response is 4xx or 5xx
        response.raise_for_status()
        
        # Success path
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info(f"Successfully fetched HTML from {url} in {elapsed_ms} ms. Status code: {response.status_code}")
        
        result["html"] = response.text
        result["status_code"] = response.status_code
        result["fetch_time_ms"] = elapsed_ms
        
    except ConnectionError as ce:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        err_msg = f"Connection error: {str(ce)}"
        logger.error(f"Failed to fetch {url} - {err_msg}")
        result["error"] = err_msg
        result["fetch_time_ms"] = elapsed_ms
        
    except Timeout as te:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        err_msg = f"Timeout error (10s limit exceeded): {str(te)}"
        logger.error(f"Failed to fetch {url} - {err_msg}")
        result["error"] = err_msg
        result["fetch_time_ms"] = elapsed_ms
        
    except HTTPError as he:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        status_code = he.response.status_code if he.response is not None else None
        err_msg = f"HTTP error {status_code}: {str(he)}"
        logger.error(f"Failed to fetch {url} - {err_msg}")
        result["status_code"] = status_code
        result["error"] = err_msg
        result["fetch_time_ms"] = elapsed_ms
        
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        err_msg = f"Unexpected error: {str(e)}"
        logger.error(f"Failed to fetch {url} - {err_msg}")
        result["error"] = err_msg
        result["fetch_time_ms"] = elapsed_ms
        
    return result


def is_valid_url(url: str) -> bool:
    """
    Checks if a URL is reachable and points to a valid HTML page.
    
    Args:
        url: The URL to validate.
        
    Returns:
        True if the URL is reachable and the Content-Type is text/html, False otherwise.
    """
    logger.info(f"Validating URL reachability and content type: {url}")
    
    # Basic structural check
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or parsed.scheme not in ("http", "https") or not parsed.netloc:
        logger.warning(f"URL format is invalid or has unsupported scheme: {url}")
        return False
        
    headers = {
        "User-Agent": get_random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    
    # 1. Attempt HTTP HEAD request to minimize bandwidth/time
    try:
        logger.info(f"Sending HEAD request to validate {url}")
        response = requests.head(url, headers=headers, timeout=10.0, allow_redirects=True)
        
        # If HEAD succeeds, verify content type
        if response.status_code < 400:
            content_type = response.headers.get("Content-Type", "").lower()
            logger.info(f"HEAD response received. Status: {response.status_code}, Content-Type: {content_type}")
            if "text/html" in content_type:
                logger.info(f"URL {url} is valid (HEAD request verified text/html).")
                return True
            else:
                logger.warning(f"URL {url} has invalid Content-Type: {content_type}")
                return False
        else:
            logger.warning(f"HEAD request failed with status: {response.status_code}. Retrying with GET...")
            
    except (ConnectionError, Timeout, HTTPError) as e:
        logger.warning(f"HEAD request to {url} raised exception: {e}. Retrying with GET...")
    except Exception as e:
        logger.warning(f"Unexpected error during HEAD request to {url}: {e}. Retrying with GET...")

    # 2. Fallback to GET request with stream=True (only read headers)
    try:
        logger.info(f"Sending GET request (stream=True) to validate {url}")
        # stream=True avoids downloading response body, saving resources
        with requests.get(url, headers=headers, timeout=10.0, stream=True, allow_redirects=True) as response:
            if response.status_code < 400:
                content_type = response.headers.get("Content-Type", "").lower()
                logger.info(f"GET response received. Status: {response.status_code}, Content-Type: {content_type}")
                if "text/html" in content_type:
                    logger.info(f"URL {url} is valid (GET request verified text/html).")
                    return True
                else:
                    logger.warning(f"URL {url} has invalid Content-Type: {content_type}")
                    return False
            else:
                logger.warning(f"GET request failed with status: {response.status_code}")
                return False
                
    except Exception as e:
        logger.error(f"Failed to validate URL {url}: {e}")
        return False
