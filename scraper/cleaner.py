import logging
from bs4 import BeautifulSoup, Comment
from typing import Dict, Any

# Set up logging
logger = logging.getLogger(__name__)


def clean_html(html: str) -> Dict[str, Any]:
    """
    Cleans raw HTML by removing structural/non-content tags, HTML comments, 
    and stripping all attributes except class, id, href, and datetime.
    
    Args:
        html: The raw HTML content as a string.
        
    Returns:
        A dictionary containing:
            - cleaned_html (str): The cleaned HTML string.
            - original_size_bytes (int): Original HTML size in bytes.
            - cleaned_size_bytes (int): Cleaned HTML size in bytes.
            - reduction_percent (float): Percentage of size reduction.
            - tag_counts_removed (dict): Counts of specific tags removed.
    """
    if not html:
        logger.warning("Empty HTML string provided to clean_html.")
        return {
            "cleaned_html": "",
            "original_size_bytes": 0,
            "cleaned_size_bytes": 0,
            "reduction_percent": 0.0,
            "tag_counts_removed": {}
        }

    original_size = len(html.encode("utf-8"))
    
    # Parse HTML using lxml parser
    soup = BeautifulSoup(html, "lxml")
    
    # List of tags to completely remove (decompose)
    tags_to_remove = [
        "script", "style", "nav", "footer", "header", 
        "aside", "iframe", "noscript", "svg", "form", "button"
    ]
    
    tag_counts_removed = {}
    
    # Count tags first before modifying the DOM tree (handles nested tags like button inside form)
    for tag_name in tags_to_remove:
        tags = soup.find_all(tag_name)
        tag_counts_removed[tag_name] = len(tags)

    # Decompose targeted tags
    for tag_name in tags_to_remove:
        tags = soup.find_all(tag_name)
        for t in tags:
            t.decompose()
        
        count = tag_counts_removed[tag_name]
        if count > 0:
            logger.info(f"Removed {count} <{tag_name}> tag(s)")

    # 2. Remove HTML comments
    comments = soup.find_all(string=lambda text: isinstance(text, Comment))
    comment_count = len(comments)
    tag_counts_removed["html_comments"] = comment_count
    for comment in comments:
        comment.extract()
        
    if comment_count > 0:
        logger.info(f"Removed {comment_count} HTML comment(s)")

    # 3. Keep only: class, id, href, datetime attributes
    allowed_attrs = {"class", "id", "href", "datetime"}
    attrs_removed_count = 0
    
    for element in soup.find_all(True):
        # Create a copy of attributes keys to safely modify dict during iteration
        element_attrs = list(element.attrs.keys())
        for attr in element_attrs:
            if attr not in allowed_attrs:
                del element.attrs[attr]
                attrs_removed_count += 1
                
    if attrs_removed_count > 0:
        logger.debug(f"Removed {attrs_removed_count} disallowed attributes from tags.")

    cleaned_html = str(soup)
    cleaned_size = len(cleaned_html.encode("utf-8"))
    
    reduction_percent = 0.0
    if original_size > 0:
        reduction_percent = round(((original_size - cleaned_size) / original_size * 100), 1)
        
    logger.info(
        f"Stage 1 -> Stage 2: HTML cleaning completed. "
        f"Size reduced from {original_size} bytes to {cleaned_size} bytes ({reduction_percent}% reduction)."
    )
    
    return {
        "cleaned_html": cleaned_html,
        "original_size_bytes": original_size,
        "cleaned_size_bytes": cleaned_size,
        "reduction_percent": reduction_percent,
        "tag_counts_removed": tag_counts_removed
    }


def extract_main_content(cleaned_html: str) -> Dict[str, Any]:
    """
    Extracts the main content elements from the cleaned HTML using a prioritized 
    list of common container selectors, falling back to <body> if none match.
    
    Args:
        cleaned_html: The minimized/cleaned HTML content.
        
    Returns:
        A dictionary containing:
            - main_html (str): The outer HTML string of the matched block.
            - main_text (str): The plain text content extracted from the block.
            - word_count (int): Word count of the plain text.
            - selector_used (str): The selector name that matched.
            - fallback_used (bool): True if fell back to body/html, False otherwise.
    """
    if not cleaned_html:
        logger.warning("Empty cleaned HTML string provided to extract_main_content.")
        return {
            "main_html": "",
            "main_text": "",
            "word_count": 0,
            "selector_used": "none",
            "fallback_used": True
        }

    soup = BeautifulSoup(cleaned_html, "lxml")
    
    # Priority selectors to locate main text body
    selectors = [
        "article", "main", ".content", ".article-body", 
        ".post-content", "#content", ".haber-detay", ".news-detail"
    ]
    
    matched_element = None
    selector_used = None
    
    for selector in selectors:
        matched_element = soup.select_one(selector)
        if matched_element:
            selector_used = selector
            logger.info(f"Located main content element using selector: '{selector}'")
            break
            
    fallback_used = False
    if not matched_element:
        logger.info("No content selector matched. Falling back to <body>.")
        matched_element = soup.find("body")
        selector_used = "body"
        fallback_used = True
        
    if not matched_element:
        logger.warning("<body> tag not found in cleaned HTML. Falling back to root document.")
        matched_element = soup
        selector_used = "html"
        fallback_used = True

    # Capture HTML structure and plain text
    main_html = str(matched_element)
    
    # Extract plain text with space separation and remove extra blank spaces
    raw_text = matched_element.get_text(separator=" ", strip=True)
    main_text = " ".join(raw_text.split())
    word_count = len(main_text.split())
    
    logger.info(
        f"Stage 2 -> Stage 3: Content extraction completed. "
        f"Selector: '{selector_used}' | Fallback: {fallback_used} | Word Count: {word_count} words."
    )
    
    return {
        "main_html": main_html,
        "main_text": main_text,
        "word_count": word_count,
        "selector_used": selector_used,
        "fallback_used": fallback_used
    }


def get_size_stats(original_html: str, cleaned_html: str, main_text: str) -> Dict[str, Any]:
    """
    Computes size statistics (in bytes and percentages) across three stages:
    Stage 1: Original HTML
    Stage 2: Cleaned HTML
    Stage 3: Main Text
    
    Args:
        original_html: The original raw HTML.
        cleaned_html: The minimized/cleaned HTML.
        main_text: The extracted plain text content.
        
    Returns:
        A dictionary containing size details and percentages for all 3 stages.
    """
    get_bytes = lambda s: len(s.encode("utf-8")) if s else 0
    
    size1 = get_bytes(original_html)
    size2 = get_bytes(cleaned_html)
    size3 = get_bytes(main_text)
    
    pct1 = 100.0
    pct2 = round((size2 / size1 * 100), 1) if size1 > 0 else 0.0
    pct3 = round((size3 / size1 * 100), 1) if size1 > 0 else 0.0
    
    reduction_pct2 = round(100.0 - pct2, 1)
    reduction_pct3 = round(100.0 - pct3, 1)
    
    logger.info("=== SIZE REDUCTION STATISTICS ===")
    logger.info(f"Stage 1 (Original HTML): {size1} bytes ({pct1}%)")
    logger.info(f"Stage 2 (Cleaned HTML) : {size2} bytes ({pct2}% of original, {reduction_pct2}% reduction)")
    logger.info(f"Stage 3 (Main Text Only): {size3} bytes ({pct3}% of original, {reduction_pct3}% reduction)")
    logger.info("=================================")
    
    return {
        "stage1_original": {
            "size_bytes": size1,
            "percent_of_original": pct1,
            "reduction_percent": 0.0
        },
        "stage2_cleaned": {
            "size_bytes": size2,
            "percent_of_original": pct2,
            "reduction_percent": reduction_pct2
        },
        "stage3_main_text": {
            "size_bytes": size3,
            "percent_of_original": pct3,
            "reduction_percent": reduction_pct3
        }
    }
