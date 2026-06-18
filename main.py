import logging
from scraper.fetcher import fetch_html, is_valid_url

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("nextscrape")

def main():
    logger.info("Starting NextScrape...")
    test_url = "https://httpbin.org/html"
    
    logger.info(f"Validating URL: {test_url}")
    if is_valid_url(test_url):
        logger.info(f"URL is valid. Fetching HTML...")
        result = fetch_html(test_url)
        logger.info(f"Fetch completed. Status code: {result['status_code']}")
        if result['error']:
            logger.error(f"Error fetching page: {result['error']}")
        else:
            logger.info(f"Fetched {len(result['html'])} bytes of HTML.")
    else:
        logger.warning(f"URL is not a reachable HTML page: {test_url}")

if __name__ == "__main__":
    main()
