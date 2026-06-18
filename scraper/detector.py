import logging
import urllib.parse
from bs4 import BeautifulSoup
from typing import Dict, Any

# Set up logging
logger = logging.getLogger(__name__)


def detect_language(text: str) -> str:
    """
    Detects the language of the given text using the langdetect library.
    
    Args:
        text: The text to analyze.
        
    Returns:
        The detected lowercase language code (e.g., "tr", "en", "de"), 
        or "unknown" if detection fails.
    """
    if not text or not text.strip():
        logger.debug("Empty or whitespace text provided. Returning 'unknown'.")
        return "unknown"
        
    try:
        from langdetect import detect
        # We pass a cleaned sample of the text to avoid overhead on extremely long texts
        sample_text = text.strip()[:1000]
        lang = detect(sample_text)
        logger.info(f"Language detected successfully: '{lang}'")
        return lang.lower()
    except Exception as e:
        logger.warning(f"Failed to detect language: {e}. Returning 'unknown'.")
        return "unknown"


def detect_site_type(url: str, html: str) -> Dict[str, Any]:
    """
    Classifies a site category from its URL and HTML content.
    
    Categories: "news", "sports", "technology", "official", "international", "unknown"
    
    Args:
        url: The web page URL.
        html: The raw/cleaned HTML content.
        
    Returns:
        A dictionary containing site classification metadata:
        {
            "site_type": str,
            "language": str,
            "domain": str,
            "confidence": float,
            "detection_method": str
        }
    """
    logger.info(f"Starting site type detection for URL: {url}")
    
    parsed_url = urllib.parse.urlparse(url)
    path = parsed_url.path.lower()
    query = parsed_url.query.lower()
    domain = parsed_url.netloc.lower()
    
    # Clean domain string (strip www.)
    if domain.startswith("www."):
        domain = domain[4:]

    # 1. Scoring maps for categories
    categories = ["news", "sports", "technology", "official", "international"]
    url_scores = {cat: 0.0 for cat in categories}
    meta_scores = {cat: 0.0 for cat in categories}
    content_scores = {cat: 0.0 for cat in categories}

    # URL path & query keyword checks
    if any(kw in path or kw in query for kw in ["spor", "sport", "futbol", "soccer", "basketbol"]):
        url_scores["sports"] += 0.6
    if any(kw in path or kw in query for kw in ["tekno", "tech", "bilim", "science"]):
        url_scores["technology"] += 0.6
    if any(kw in path or kw in query for kw in ["news", "haber", "gundem", "makale", "article", "breaking", "son-dakika"]):
        url_scores["news"] += 0.5
    if domain.endswith((".gov", ".gov.tr", ".gov.uk", ".org")):
        url_scores["official"] += 0.7
    if any(kw in path for kw in ["official", "resmi", "kamu"]):
        url_scores["official"] += 0.4
    if any(kw in path for kw in ["/en/", "/global/", "international", "global"]):
        url_scores["international"] += 0.5

    # Parse HTML
    soup = BeautifulSoup(html, "lxml")

    # 2. Meta tags check
    # Check og:type meta tag
    og_type_tag = soup.find("meta", property="og:type") or soup.find("meta", attrs={"name": "og:type"})
    if og_type_tag and og_type_tag.get("content"):
        og_type = og_type_tag.get("content").lower()
        if og_type in ["article", "news", "blog"]:
            meta_scores["news"] += 0.4

    # Check article:section, category, section, or topic tags
    section_tags = [
        soup.find("meta", property="article:section"),
        soup.find("meta", attrs={"name": "article:section"}),
        soup.find("meta", attrs={"name": "category"}),
        soup.find("meta", attrs={"name": "section"}),
        soup.find("meta", attrs={"name": "topic"})
    ]
    for tag in section_tags:
        if tag and tag.get("content"):
            val = tag.get("content").lower()
            if any(kw in val for kw in ["sport", "spor", "futbol", "football", "soccer"]):
                meta_scores["sports"] += 0.7
            if any(kw in val for kw in ["tech", "technology", "tekno", "bilim", "science", "software"]):
                meta_scores["technology"] += 0.7
            if any(kw in val for kw in ["news", "politics", "world", "gundem", "haber"]):
                meta_scores["news"] += 0.6
            if any(kw in val for kw in ["gov", "official", "resmi"]):
                meta_scores["official"] += 0.5
            if any(kw in val for kw in ["en", "global", "international"]):
                meta_scores["international"] += 0.5

    # 3. HTML Content check (Title and H1 texts)
    title_text = ""
    if soup.title and soup.title.string:
        title_text = soup.title.string.lower()
        
    h1_texts = [h1.get_text().lower() for h1 in soup.find_all("h1")]
    content_pool = title_text + " " + " ".join(h1_texts)

    if content_pool.strip():
        if any(kw in content_pool for kw in ["spor", "sport", "futbol", "football", "soccer", "basketbol"]):
            content_scores["sports"] += 0.5
        if any(kw in content_pool for kw in ["tech", "technology", "teknoloji", "science", "bilim", "yazilim", "software"]):
            content_scores["technology"] += 0.5
        if any(kw in content_pool for kw in ["haber", "news", "gundem", "son dakika", "breaking"]):
            content_scores["news"] += 0.4
        if any(kw in content_pool for kw in ["bakanligi", "resmi", "t.c.", "official", "government"]):
            content_scores["official"] += 0.5
        if any(kw in content_pool for kw in ["global", "international", "world"]):
            content_scores["international"] += 0.4

    # Determine winning category and classification method
    detected_cat = "unknown"
    max_score = 0.0
    detection_method = "default"

    for cat in categories:
        total = url_scores[cat] + meta_scores[cat] + content_scores[cat]
        if total > max_score:
            max_score = total
            detected_cat = cat
            
            # Map sub-scores to determine the most influential detection method
            contribs = {
                "meta_tags": meta_scores[cat],
                "url_keywords": url_scores[cat],
                "html_content": content_scores[cat]
            }
            # Pick the method that contributed the highest points
            detection_method = max(contribs, key=contribs.get)

    # Compute language
    body_tag = soup.find("body")
    body_text = body_tag.get_text(separator=" ", strip=True) if body_tag else ""
    lang_detect_text = content_pool + " " + body_text
    lang = detect_language(lang_detect_text)

    # Calculate confidence based on maximum cumulative score
    confidence = 0.0
    if detected_cat != "unknown" and max_score > 0.0:
        confidence = round(min(max_score / 1.5, 1.0), 2)
    else:
        detected_cat = "unknown"
        detection_method = "default"

    logger.info(
        f"Site type classification completed: Domain='{domain}' -> Category='{detected_cat}' "
        f"(Confidence={confidence}, Method='{detection_method}', Language='{lang}')"
    )

    return {
        "site_type": detected_cat,
        "language": lang,
        "domain": domain,
        "confidence": confidence,
        "detection_method": detection_method
    }


def is_article_page(url: str, html: str) -> bool:
    """
    Evaluates heuristic indicators to determine if the page is a single 
    article page (True) or a homepage/category listing (False).
    
    Indicators:
        - URL path segments depth >= 2
        - Keywords ("article", "haber", "news", "post") in URL path
        - Exactly one <h1> tag in the DOM
        - Text word count > 200 words
        
    Args:
        url: The web page URL.
        html: The raw/cleaned HTML content.
        
    Returns:
        True if categorized as an article page, False otherwise.
    """
    logger.info(f"Running article page heuristic analysis on URL: {url}")
    
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()
    
    # Hompepage / Root check
    if not path or path in ["/", "/index.html", "/index.htm", "/index.php", "/index.asp"]:
        logger.info(f"URL points to root/homepage index. Classifying as listing/homepage: False")
        return False
        
    path_segments = [s for s in path.split("/") if s]
    score = 0.0
    indicators = {}

    # 1. URL Path depth segment count
    has_deep_path = len(path_segments) >= 2
    if has_deep_path:
        score += 1.0
    indicators["deep_path"] = has_deep_path

    # 2. URL keywords check
    has_url_kws = any(kw in path for kw in ["article", "haber", "news", "post"])
    if has_url_kws:
        score += 1.0
    indicators["url_keywords"] = has_url_kws

    # Parse DOM structure
    soup = BeautifulSoup(html, "lxml")

    # 3. Single H1 tag check
    h1_count = len(soup.find_all("h1"))
    has_single_h1 = (h1_count == 1)
    if has_single_h1:
        score += 1.0
    indicators["single_h1"] = has_single_h1

    # 4. Long text content word count
    body_tag = soup.find("body")
    body_text = body_tag.get_text(separator=" ", strip=True) if body_tag else ""
    # Clean whitespace and count words
    words = body_text.split()
    word_count = len(words)
    
    has_long_content = False
    if word_count > 500:
        score += 2.0
        has_long_content = True
    elif word_count > 200:
        score += 1.5
        has_long_content = True
    indicators["long_content"] = has_long_content
    indicators["word_count"] = word_count

    # Decision threshold: score >= 2.0
    is_article = (score >= 2.0)
    
    logger.info(
        f"Article check completed. Score={score:.1f} (Threshold=2.0) -> IsArticle={is_article}. "
        f"Indicators Checked: {indicators}"
    )
    
    return is_article
