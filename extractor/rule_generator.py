import os
import time
import json
import logging
import urllib.parse
from typing import Dict, Any, Optional

import requests
from bs4 import BeautifulSoup
from extractor.regex_filter import apply_regex_filters, compare_with_without_regex

# Set up logging
logger = logging.getLogger(__name__)



def get_domain(url: str) -> str:
    """
    Extracts the cleaned domain name from the given URL.
    """
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def generate_rules(raw_html: str, url: str, feedback: Optional[str] = None) -> Dict[str, Any]:
    """
    Sends the raw body HTML segment to a local Ollama instance running llama3 to generate 
    CSS selectors for extracting article details.
    
    Args:
        raw_html: Raw HTML document.
        url: The article URL.
        feedback: Feedback from previous failed extraction attempts.
        
    Returns:
        A dictionary containing rules and Ollama response metadata.
    """
    logger.info("Initializing rule generation via local Ollama (model: llama3)...")
    
    # Extract body content
    soup = BeautifulSoup(raw_html, "lxml")
    body = soup.find("body")
    body_html = str(body) if body else raw_html
    
    # Sample the first 4000 characters of the body
    html_sample = body_html[:4000]
    
    # Keywords that indicate non-article elements (popups, ads, navigation, etc.)
    BANNED_SELECTOR_KEYWORDS = [
        "popup", "modal", "overlay", "redirect", "cookie", "banner",
        "advertisement", "reklam", "sidebar", "related", "son-dakika-list",
        "breaking-news-list", "nav", "footer", "header", "menu", "widget"
    ]
    
    system_prompt = (
        "You are an expert HTML parser. Analyze the given HTML and return ONLY a JSON \n"
        "object with CSS selectors to extract news article data. \n"
        "Return ONLY valid JSON, no explanation, no markdown, no backticks.\n\n"
        "Required JSON format:\n"
        "{\n"
        "  'title': 'CSS selector for article title',\n"
        "  'content': 'CSS selector for main article text',\n"
        "  'author': 'CSS selector for author name or null',\n"
        "  'date': 'CSS selector for publication date or null'\n"
        "}\n\n"
        "Rules:\n"
        "- Prefer specific selectors over generic ones\n"
        "- Use class or id based selectors when available\n"
        "- If a field cannot be found reliably, return null\n"
        "- Never return selectors for navigation, ads, or sidebar content\n"
        "- NEVER use selectors containing: popup, modal, overlay, redirect, "
        "cookie, banner, advertisement, reklam, sidebar, related, "
        "son-dakika-list, breaking-news-list\n"
        "- Focus on the MAIN ARTICLE BODY, not popups or modals"
    )
    
    user_prompt = (
        "You are analyzing HTML from a news website. \n"
        "Find the CSS selectors for these fields: title, content, author, date.\n\n"
        "Important rules:\n"
        "- Look for h1 tags for title\n"
        "- Look for divs with classes containing: content, article, detail, haber, body, text\n"
        "- Look for spans or divs with classes containing: author, yazar, writer\n"
        "- Look for time tags or divs with classes containing: date, tarih, time\n"
        "- Return ONLY a JSON object, no explanation\n\n"
        f"HTML to analyze:\n{html_sample}"
    )
    
    if feedback:
        user_prompt += f"\n\nFeedback from previous attempt:\n{feedback}"
    
    payload = {
        "model": "llama3",
        "prompt": user_prompt,
        "system": system_prompt,
        "stream": False,
        "options": {
            "temperature": 0.0  # Greedy decoding for deterministic JSON
        }
    }
    
    result = {
        "rules": {
            "title": None,
            "content": None,
            "author": None,
            "date": None
        },
        "raw_response": "",
        "model": "llama3",
        "generation_time_ms": 0,
        "success": False,
        "error": None
    }
    
    endpoint = "http://localhost:11434/api/generate"
    start_time = time.perf_counter()
    
    try:
        logger.info(f"Sending request to Ollama endpoint: {endpoint}")
        response = requests.post(endpoint, json=payload, timeout=120.0)
        response.raise_for_status()
        
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        result["generation_time_ms"] = elapsed_ms
        
        response_json = response.json()
        raw_text = response_json.get("response", "").strip()
        result["raw_response"] = raw_text
        
        logger.info(f"Ollama generation completed in {elapsed_ms} ms.")
        
        # Parse JSON content from raw LLM text
        # Remove markdown backticks if present
        json_str = raw_text
        if json_str.startswith("```"):
            start = json_str.find("{")
            end = json_str.rfind("}")
            if start != -1 and end != -1:
                json_str = json_str[start:end+1]
                
        # Parse logic supporting single/double quotes
        try:
            rules_dict = json.loads(json_str)
        except json.JSONDecodeError:
            # Fallback to python ast evaluation for single-quoted dict representation
            import ast
            rules_dict = ast.literal_eval(json_str)
            
        # Ensure rules keys exist and are formatted
        formatted_rules = {
            "title": rules_dict.get("title"),
            "content": rules_dict.get("content"),
            "author": rules_dict.get("author"),
            "date": rules_dict.get("date")
        }
        
        # Convert string representation of 'null' or None values to None
        for key, val in formatted_rules.items():
            if val in [None, "null", "None", "NoneVal"]:
                formatted_rules[key] = None
        
        # Filter out selectors that contain banned keywords (popup, modal, etc.)
        for key, val in formatted_rules.items():
            if val is not None:
                val_lower = val.lower()
                for banned in BANNED_SELECTOR_KEYWORDS:
                    if banned in val_lower:
                        logger.warning(f"Rejecting selector for '{key}': '{val}' contains banned keyword '{banned}'")
                        formatted_rules[key] = None
                        break
                
        result["rules"] = formatted_rules
        result["success"] = True
        logger.info(f"Rules parsed successfully: {formatted_rules}")
        
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        if result["generation_time_ms"] == 0:
            result["generation_time_ms"] = elapsed_ms
        err_msg = f"Failed to generate rules via Ollama: {e}"
        logger.error(err_msg)
        result["error"] = err_msg
        result["success"] = False
        
    return result


def apply_rules(html: str, rules: Dict[str, Optional[str]]) -> Dict[str, Any]:
    """
    Applies CSS selectors from the rules dictionary to extract article details.
    Uses automatic fallback selectors if the target selector fails.
    
    Args:
        html: The HTML document to extract from.
        rules: Dictionary of CSS selectors.
        
    Returns:
        A dictionary containing extracted values, success flags, fallback flags,
        and success rate.
    """
    logger.info("Applying extraction rules to HTML...")
    soup = BeautifulSoup(html, "lxml")

    # --- Raw page text for regex analytics (BEFORE any CSS selector filtering) ---
    # soup.get_text() gives the full page plain text including nav, footer, ads,
    # social buttons, etc. This is the dirtiest representation — ideal for
    # measuring how much regex filters actually clean up.
    raw_page_text_for_stats = soup.get_text(separator="\n", strip=True)

    extracted_data = {
        "title": None,
        "content": None,
        "author": None,
        "date": None
    }
    
    extraction_success = {
        "title": False,
        "content": False,
        "author": False,
        "date": False
    }
    
    used_fallback = {
        "title": False,
        "content": False,
        "author": False,
        "date": False
    }
    
    # Minimum content length to accept (below this, try next fallback)
    MIN_CONTENT_LENGTH = 200
    
    fallbacks = {
        "title": ['h1', 'h1.title', '.title h1', '.news-title', '.haber-baslik'],
        "content": [
            'article',
            '.news-detail-content',
            '.haber-detay-icerik',
            '.detail-body',
            '.article-body',
            '[class*="article"]',
            '[class*="detail"]',
            '[class*="content"]',
            '.news-detail',
            '.haber-detay',
            '.content',
            'main p',
        ],
        "author": [
            '.author', '.yazar', '.writer', 'span.author-name', 
            'a.author', '.news-author', '.article-author',
            'span[itemprop="author"]', 'div[itemprop="author"]',
            'meta[name="articleAuthor"]', 'meta[name="author"]',
            'meta[property="article:author"]', 'meta[property="creators"]',
            'meta[property="mrf:authors"]'
        ],
        "date": ['time', '.date', '.tarih', 'span.time']
    }
    
    fields = ["title", "content", "author", "date"]
    
    for field in fields:
        selector = rules.get(field)
        
        def extract_by_selector(sel: Optional[str]) -> Optional[str]:
            if not sel:
                return None
            try:
                if field == "content":
                    matched_elements = soup.select(sel)
                    if matched_elements:
                        texts = [el.get_text(separator=" ", strip=True) for el in matched_elements]
                        texts = [t for t in texts if t]
                        if texts:
                            return "\n\n".join(texts)
                elif field == "date":
                    el = soup.select_one(sel)
                    if el:
                        if el.has_attr("datetime") and el["datetime"]:
                            return el["datetime"].strip()
                        else:
                            return el.get_text(separator=" ", strip=True)
                else:
                    el = soup.select_one(sel)
                    if el:
                        if el.name == "meta" and el.has_attr("content"):
                            return el["content"].strip()
                        return el.get_text(separator=" ", strip=True)
            except Exception as e:
                logger.error(f"Error applying selector '{sel}' for field '{field}': {e}")
            return None

        # 1. Try LLM selector
        val = extract_by_selector(selector)
        # For content field, enforce minimum length
        if val and field == "content" and len(val.strip()) < MIN_CONTENT_LENGTH:
            logger.warning(f"Selector '{selector}' yielded content too short ({len(val.strip())} chars < {MIN_CONTENT_LENGTH}). Trying fallbacks...")
            val = None
        if val:
            extracted_data[field] = val
            extraction_success[field] = True
            logger.info(f"Successfully extracted '{field}' using selector: '{selector}'")
        else:
            # 2. Try Fallbacks
            if selector:
                logger.warning(f"Selector '{selector}' did not yield text for field '{field}'. Trying fallbacks...")
            else:
                logger.debug(f"No selector defined for field '{field}'. Trying fallbacks...")
                
            for fb_sel in fallbacks[field]:
                fb_val = extract_by_selector(fb_sel)
                if fb_val:
                    # For content field, enforce minimum length before accepting fallback
                    if field == "content" and len(fb_val.strip()) < MIN_CONTENT_LENGTH:
                        logger.warning(f"Fallback '{fb_sel}' yielded content too short ({len(fb_val.strip())} chars). Skipping...")
                        continue
                    extracted_data[field] = fb_val
                    extraction_success[field] = True
                    used_fallback[field] = True
                    logger.info(f"Successfully extracted '{field}' using fallback selector: '{fb_sel}'")
                    break
                    
            if not extraction_success[field]:
                logger.warning(f"All selectors and fallbacks failed to extract field '{field}'")
    
    # --- Step A: Capture the truly raw content BEFORE any post-processing ---
    # This is what we'll compare against in the regex stats (before vs after).
    pre_processing_raw = extracted_data["content"] or ""

    # Post-processing: Clean content noise
    if extracted_data["content"]:
        raw_content = extracted_data["content"]
        
        # Noise phrases to remove
        noise_phrases = [
            "Paylaş", "Kopyala", "Son Güncellenme", "Linki Kopya",
            "Haberler", "#Süper Lig", "#Beşiktaş", "#Galatasaray",
            "#Fenerbahçe", "#Trabzonspor"
        ]
        
        # Split into lines and clean
        lines = raw_content.split("\n")
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Skip lines shorter than 20 characters
            if len(stripped) < 20:
                continue
            # Skip lines containing noise phrases
            if any(noise in stripped for noise in noise_phrases):
                continue
            cleaned_lines.append(stripped)
        
        # Deduplicate sentences within the cleaned content
        full_text = " ".join(cleaned_lines)
        sentences = [s.strip() for s in full_text.split(".") if s.strip()]
        seen = set()
        unique_sentences = []
        for sentence in sentences:
            normalized = sentence.lower().strip()
            if normalized not in seen:
                seen.add(normalized)
                unique_sentences.append(sentence)
        
        # Rejoin with proper punctuation and strip extra whitespace
        cleaned_content = ". ".join(unique_sentences)
        if cleaned_content and not cleaned_content.endswith("."):
            cleaned_content += "."
        
        # Normalize whitespace
        import re
        cleaned_content = re.sub(r'\s+', ' ', cleaned_content).strip()
        
        if cleaned_content:
            logger.info(f"Content cleaned: {len(raw_content)} -> {len(cleaned_content)} chars")
            extracted_data["content"] = cleaned_content
        else:
            logger.warning("Content cleaning removed all text, keeping original")


    # --- RegEx analytics: compare full raw page text vs. after regex filtering ---
    # Using raw_page_text_for_stats (full page get_text before any CSS filtering)
    # means "before" has real URLs written as text in onclick/data attributes
    # rendered as text, social share button labels, hashtags, date noise, etc.
    raw_content = pre_processing_raw
    filtered_content = ""
    regex_stats = {
        "without_regex": {"text_length": 0, "noise_count": 0, "noise_ratio": 0.0, "word_count": 0},
        "with_regex": {"text_length": 0, "noise_count": 0, "noise_ratio": 0.0, "word_count": 0},
        "improvement": {"noise_reduction_percent": 0.0, "length_reduction_percent": 0.0, "clarity_improvement": "Yok"},
        "filters_applied": {
            "html_entities_removed": 0,
            "urls_removed": 0,
            "social_noise_removed": 0,
            "datetime_noise_removed": 0,
            "hashtags_removed": 0,
            "short_lines_removed": 0
        },
        "total_items_removed": 0
    }

    if raw_page_text_for_stats:
        # apply_regex_filters counts what was removed from the raw page text
        regex_res = apply_regex_filters(raw_page_text_for_stats)
        filtered_content = regex_res["filtered_text"]
        # compare_with_without_regex builds before/after stats using raw page text
        regex_stats = compare_with_without_regex(raw_page_text_for_stats)
        logger.info(
            f"Regex stats computed on raw page text ({len(raw_page_text_for_stats)} chars). "
            f"Noise before: {regex_stats['without_regex']['noise_count']}, "
            f"after: {regex_stats['with_regex']['noise_count']}"
        )

    # Ensure final content is set (prefer post-processed result, fall back to filtered)
    if not extracted_data["content"] and filtered_content:
        extracted_data["content"] = filtered_content


    # Calculate success rate as ratio of successfully extracted fields
    success_count = sum(extraction_success.values())
    success_rate = round(success_count / len(fields), 2)
    
    logger.info(f"Extraction completed. Success count: {success_count}/{len(fields)} (Rate: {success_rate})")
    
    return {
        "title": extracted_data["title"],
        "content": extracted_data["content"],
        "raw_content": raw_content,
        "filtered_content": filtered_content,
        "regex_stats": regex_stats,
        "author": extracted_data["author"],
        "date": extracted_data["date"],
        "extraction_success": extraction_success,
        "used_fallback": used_fallback,
        "success_rate": success_rate
    }



def cache_rules(url: str, rules: Dict[str, Optional[str]], success_rate: float = 0.0) -> None:
    """
    Caches generated extraction rules to data/rules_cache/{domain}.json.
    
    Args:
        url: The target page URL.
        rules: The generated CSS selectors rules dict.
        success_rate: The extraction success rate of the rules.
    """
    domain = get_domain(url)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_dir = os.path.join(project_root, "data", "rules_cache")
    
    # Ensure cache directory exists
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{domain}.json")
    
    cache_data = {
        "rules": rules,
        "success_rate": success_rate,
        "timestamp": time.time()
    }
    
    logger.info(f"Caching generated rules to {cache_path}...")
    try:
        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=4)
        logger.info(f"Rules for {domain} successfully cached.")
    except Exception as e:
        logger.error(f"Failed to cache rules for {domain}: {e}")


def load_cached_rules(url: str) -> Optional[Dict[str, Optional[str]]]:
    """
    Loads cached rules for the domain if they are less than 7 days old.
    
    Args:
        url: The target page URL.
        
    Returns:
        The cached rules dictionary, or None if no valid cache exists.
    """
    domain = get_domain(url)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_dir = os.path.join(project_root, "data", "rules_cache")
    cache_path = os.path.join(cache_dir, f"{domain}.json")
    
    logger.info(f"Checking cache for domain: {domain}")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                cache_data = json.load(f)
            
            timestamp = cache_data.get("timestamp", 0)
            # 7 days in seconds: 7 * 24 * 60 * 60 = 604800
            if time.time() - timestamp < 604800:
                logger.info(f"Found valid cached rules for {domain} (age < 7 days)")
                return cache_data.get("rules")
            else:
                logger.info(f"Cached rules for {domain} have expired (> 7 days old)")
        except Exception as e:
            logger.error(f"Failed to load cached rules for {domain}: {e}")
            
    return None
