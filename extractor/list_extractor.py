import re
import time
import json
import logging
import urllib.parse
from typing import Dict, Any, List, Optional

import requests
from bs4 import BeautifulSoup

# Set up logging
logger = logging.getLogger(__name__)


def get_domain(url: str) -> str:
    """Extracts the cleaned domain name from the given URL."""
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def is_listing_page(url: str, html: str) -> bool:
    """
    Determines if a URL is a listing page (homepage or category page)
    rather than an individual article page.

    Hard article signals (any one → immediately return False):
    - URL path contains a number with 5+ digits (article ID)
    - URL path has 4 or more segments
    - URL contains an article-type keyword AND total URL is 50+ chars

    Hard listing signals (any one → immediately return True):
    - URL is just domain root or domain + 1 short segment AND total URL < 60 chars
    - URL contains /kategori/, /etiket/, or /tag/ AND total URL < 60 chars

    Fallback: score-based heuristic using HTML signals.

    Args:
        url: The web page URL.
        html: The raw HTML content.

    Returns:
        True if the page is detected as a listing page, False otherwise.
    """
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.strip("/")
    path_segments = [s for s in path.split("/") if s]
    total_url_len = len(url)

    # ── Hard article guards (early exits → NOT a listing page) ──────────────

    # Guard 1: 5+ digit number in path = article ID
    if re.search(r'\d{5,}', path):
        logger.info(
            f"Listing detection for {url}: 5-digit ID in path → article (False)"
        )
        return False

    # Guard 2: 4 or more path segments = deep article URL
    if len(path_segments) >= 4:
        logger.info(
            f"Listing detection for {url}: {len(path_segments)} path segments → article (False)"
        )
        return False

    # Guard 3: Article-type keyword in path + long URL = article
    ARTICLE_KEYWORDS = ["galeri", "haber", "article", "articles", "news", "detay"]
    if any(kw in path.lower() for kw in ARTICLE_KEYWORDS) and total_url_len >= 50:
        logger.info(
            f"Listing detection for {url}: article keyword in path + URL≥50 → article (False)"
        )
        return False

    # ── Hard listing guards (early exits → IS a listing page) ───────────────

    # Guard 4: Root or single-segment short URL = homepage/category
    if len(path_segments) <= 1 and total_url_len < 60:
        logger.info(
            f"Listing detection for {url}: short single-segment URL → listing (True)"
        )
        return True

    # Guard 5: Explicit category/tag path segment + short URL
    LISTING_PATH_MARKERS = ["/kategori/", "/etiket/", "/tag/"]
    if any(marker in url.lower() for marker in LISTING_PATH_MARKERS) and total_url_len < 60:
        logger.info(
            f"Listing detection for {url}: category/tag path marker + URL<60 → listing (True)"
        )
        return True

    # ── Fallback: HTML-based scoring heuristic ───────────────────────────────

    # Check: URL does NOT contain numbers (article IDs)
    has_numbers = bool(re.search(r'\d{4,}', path))

    # Check: Short path (≤1 segment)
    short_path = len(path_segments) <= 1

    # Check: Multiple h2/h3 tags with links (listing indicator)
    soup = BeautifulSoup(html, "lxml")
    heading_links = 0
    for tag in soup.find_all(["h2", "h3"]):
        if tag.find("a", href=True):
            heading_links += 1
    many_heading_links = heading_links >= 5

    # Check: Low continuous article text
    article_tags = soup.find_all(["article", "div"], class_=re.compile(
        r"(article|content|detail|haber|body|text)", re.IGNORECASE
    ))
    max_continuous_words = 0
    for tag in article_tags:
        tag_words = len(tag.get_text(separator=" ", strip=True).split())
        max_continuous_words = max(max_continuous_words, tag_words)
    low_continuous_text = max_continuous_words < 500

    score = 0
    if short_path:
        score += 1
    if not has_numbers:
        score += 1
    if many_heading_links:
        score += 1
    if low_continuous_text:
        score += 1

    is_listing = score >= 2

    logger.info(
        f"Listing page detection for {url}: "
        f"short_path={short_path}, has_numbers={has_numbers}, "
        f"heading_links={heading_links}, max_continuous_words={max_continuous_words}, "
        f"score={score}/4 -> is_listing={is_listing}"
    )

    return is_listing


def extract_news_list(url: str, html: str) -> Dict[str, Any]:
    """
    Extracts all news headline links from a listing page (homepage or category page)
    using LLM-generated CSS selectors.
    
    Args:
        url: The listing page URL.
        html: The raw HTML content.
        
    Returns:
        A dictionary containing the extracted headlines, metadata, and stats.
    """
    logger.info(f"Starting news list extraction for: {url}")
    
    domain = get_domain(url)
    soup = BeautifulSoup(html, "lxml")
    body = soup.find("body")
    body_html = str(body) if body else html
    
    # Sample the first 5000 characters for the LLM
    html_sample = body_html[:5000]
    
    system_prompt = (
        "You are analyzing a news website listing page (homepage or category page).\n"
        "Find the CSS selector that targets news article headline links.\n"
        "These are <a> tags that link to individual news articles.\n"
        "Return ONLY a JSON object:\n"
        "{\n"
        "  'headline_selector': 'CSS selector for headline links',\n"
        "  'container_selector': 'CSS selector for the news list container'\n"
        "}\n"
        "Rules:\n"
        "- Selector must target <a> tags with href attributes\n"
        "- Links should point to article pages, not categories or external sites\n"
        "- NEVER return selectors for: navigation, footer, sidebar, ads\n"
        "- Prefer selectors with h2, h3, or headline-related classes\n"
        "- Return ONLY valid JSON, no explanation, no markdown, no backticks"
    )
    
    user_prompt = (
        "You are analyzing a Turkish news website listing page.\n"
        "Find the CSS selector for news headline links.\n\n"
        "Important rules:\n"
        "- Look for <a> tags inside h2, h3, or heading containers\n"
        "- Look for classes containing: title, baslik, haber, news, headline\n"
        "- The selector should match MULTIPLE headline links on the page\n"
        "- Return ONLY a JSON object, no explanation\n\n"
        f"HTML to analyze:\n{html_sample}"
    )
    
    payload = {
        "model": "llama3",
        "prompt": user_prompt,
        "system": system_prompt,
        "stream": False,
        "options": {
            "temperature": 0.0
        }
    }
    
    result = {
        "url": url,
        "page_type": "listing",
        "total_found": 0,
        "headlines": [],
        "selector_used": None,
        "llm_generation_time_ms": 0,
        "success": False,
        "error": None
    }
    
    endpoint = "http://localhost:11434/api/generate"
    llm_selector = None
    
    start_time = time.perf_counter()
    
    try:
        logger.info(f"Sending list extraction request to Ollama endpoint: {endpoint}")
        response = requests.post(endpoint, json=payload, timeout=120.0)
        response.raise_for_status()
        
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        result["llm_generation_time_ms"] = elapsed_ms
        
        response_json = response.json()
        raw_text = response_json.get("response", "").strip()
        
        logger.info(f"Ollama list selector generation completed in {elapsed_ms} ms.")
        
        # Parse JSON from LLM response
        json_str = raw_text
        if json_str.startswith("```"):
            start_idx = json_str.find("{")
            end_idx = json_str.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = json_str[start_idx:end_idx + 1]
        
        try:
            selector_dict = json.loads(json_str)
        except json.JSONDecodeError:
            import ast
            selector_dict = ast.literal_eval(json_str)
        
        llm_selector = selector_dict.get("headline_selector")
        logger.info(f"LLM headline selector: {llm_selector}")
        
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        result["llm_generation_time_ms"] = elapsed_ms
        logger.error(f"LLM list selector generation failed: {e}")
        result["error"] = str(e)
    
    # Fallback selectors for Turkish news sites
    fallback_selectors = [
        'h3 a[href]',
        'h2 a[href]',
        '.news-title a[href]',
        '.haber-baslik a[href]',
        '[class*="title"] a[href]',
        '[class*="baslik"] a[href]',
        '[class*="headline"] a[href]',
        'a h3',
        'a h2',
        '.card-title a[href]',
        'li a[href]',
    ]
    
    # Navigation menu keyword exclusions (exact title match)
    NAV_KEYWORDS = {
        "Dünya", "Ekonomi", "Teknoloji", "Spor", "Magazin", "Gündem",
        "Türkiye", "Sağlık", "Eğitim", "Siyaset", "Frekanslar",
        "Otomobil", "Resmi İlanlar", "Son Dakika", "Galeri",
        "World", "Business", "Sports", "Technology", "Politics",
    }

    # URL pattern exclusions (Filter 3 + original patterns)
    exclude_patterns = [
        '/kategori/', '/etiket/', '/yazar/', '/tag/', '/author/',
        '/page/', '/sayfa/', '/login', '/register', '/arama/',
        '/search', '/rss', '/feed', '/video/', '/galeri/',
        # Filter 3 additions
        '/galeriler/', 'dunya-haberleri', 'ekonomi-haberleri',
        'magazin-haberleri', 'resmi-ilanlar', 'son-dakika-depremler',
        '/frekanslar/', '/programlar/',
    ]
    
    def extract_headlines_with_selector(sel: str) -> List[Dict[str, Any]]:
        """Apply a CSS selector and extract filtered headline links."""
        headlines = []
        seen_urls = set()
        
        try:
            elements = soup.select(sel)
        except Exception as e:
            logger.error(f"Invalid selector '{sel}': {e}")
            return []
        
        for el in elements:
            # Get the <a> tag — either the element itself or the first <a> descendant
            if el.name == "a":
                link_el = el
            else:
                link_el = el.find("a", href=True)
                if not link_el:
                    # If the selector matched something inside an <a>, find the parent <a>
                    link_el = el.find_parent("a", href=True)
            
            if not link_el:
                continue
            
            href = link_el.get("href", "").strip()
            if not href:
                continue
            
            # Resolve relative URLs
            if href.startswith("/"):
                parsed = urllib.parse.urlparse(url)
                href = f"{parsed.scheme}://{parsed.netloc}{href}"
            elif not href.startswith("http"):
                continue  # Skip javascript:, mailto:, etc.
            
            # Filter: same domain only
            link_domain = get_domain(href)
            if link_domain != domain:
                continue
            
            # Filter: exclude non-article URL patterns (Filter 3)
            if any(pat in href.lower() for pat in exclude_patterns):
                continue

            # Filter 4 - Minimum URL length for article pages (50 chars)
            if len(href) < 50:
                continue

            # Deduplicate
            if href in seen_urls:
                continue
            seen_urls.add(href)

            # Get title text
            title = link_el.get_text(separator=" ", strip=True)
            if not title:
                continue

            # Filter 1 - Minimum title length: 2+ words AND 15+ characters
            if len(title.split()) < 2 or len(title) < 15:
                continue

            # Filter 2 - Exclude navigation menu keywords (exact match)
            if title.strip() in NAV_KEYWORDS:
                continue
            
            headlines.append({
                "rank": len(headlines) + 1,
                "title": title,
                "url": href,
                "selector_used": sel
            })
        
        return headlines
    
    # Try LLM selector first, then fallbacks
    best_headlines = []
    best_selector = None
    
    selectors_to_try = []
    if llm_selector:
        selectors_to_try.append(llm_selector)
    selectors_to_try.extend(fallback_selectors)
    
    for sel in selectors_to_try:
        headlines = extract_headlines_with_selector(sel)
        if len(headlines) > len(best_headlines):
            best_headlines = headlines
            best_selector = sel
            logger.info(f"Selector '{sel}' found {len(headlines)} headlines (best so far)")
    
    # Re-rank headlines sequentially
    for i, h in enumerate(best_headlines, 1):
        h["rank"] = i
        h["selector_used"] = best_selector
    
    result["headlines"] = best_headlines
    result["total_found"] = len(best_headlines)
    result["selector_used"] = best_selector
    result["success"] = len(best_headlines) > 0
    
    logger.info(
        f"List extraction completed for {url}. "
        f"Total headlines: {len(best_headlines)} | Selector: {best_selector}"
    )
    
    return result
