import time
import logging
import difflib
from datetime import datetime
from typing import Dict, Any, List, Optional

from newspaper import Article

# Import project modules
from scraper.fetcher import fetch_html
from scraper.cleaner import clean_html
from extractor.rule_generator import load_cached_rules, apply_rules
from extractor.validator import run_validation_loop

# Set up logging
logger = logging.getLogger(__name__)


def explain_similarity_method() -> Dict[str, str]:
    """
    Returns a human-readable explanation of the similarity calculation method
    used in cross-checking (difflib.SequenceMatcher / Ratcliff-Obershelp).

    This is intentionally exposed so that UI layers and report generators can
    surface the methodology to end-users, helping them understand why a title
    similarity can be 1.00 while content similarity is as low as 0.06.
    """
    return {
        "method": "difflib.SequenceMatcher (Ratcliff-Obershelp algoritması)",
        "description": (
            "İki metin arasındaki ortak karakter dizilerinin oranını ölçer, "
            "0.0 (hiç benzemiyor) ile 1.0 (birebir aynı) arasında skor üretir. "
            "Anlamsal benzerlik değil, karakter dizisi benzerliği ölçülür."
        ),
        "formula": (
            "benzerlik = (2 * M) / T  "
            "(M: eşleşen karakter sayısı, T: iki metnin toplam karakter sayısı)"
        ),
        "why_title_high_content_low": (
            "Başlıklar kısa ve net olduğundan iki sistem de aynı metni çekince skor 1.0 olur. "
            "İçerikte ise bir sistem yanlışlıkla başlığı veya navigasyon metnini içerik sandıysa, "
            "metinler farklı karakter dizilerine sahip olur ve skor düşer (örn: 0.06). "
            "Bu düşük skor aslında bir hata sinyalidir — extraction'da bir sorun olduğunu gösterir."
        ),
    }


def calculate_similarity_detailed(text1: Optional[str], text2: Optional[str]) -> Dict[str, Any]:
    """
    Calculates similarity using difflib.SequenceMatcher and returns the raw
    numbers behind the formula so the calculation can be displayed
    transparently to the user.

    Returns a dict with:
      - score         : final 0.0–1.0 ratio (or -1 if not comparable)
      - matched_chars : sum of matching-block sizes (M in the formula)
      - total_chars   : len(t1) + len(t2)  (T in the formula)
      - len_text1     : character count of the first text after stripping
      - len_text2     : character count of the second text after stripping
      - formula_string: human-readable calculation string
      - comparable    : False when one/both sides are empty
    """
    t1 = (text1 or "").strip().lower()
    t2 = (text2 or "").strip().lower()

    if not t1 and not t2:
        return {
            "score": -1,
            "matched_chars": 0,
            "total_chars": 0,
            "len_text1": 0,
            "len_text2": 0,
            "formula_string": "Her iki metin de boş, karşılaştırma yapılamadı",
            "comparable": False,
        }
    if not t1 or not t2:
        non_empty_len = len(t1) or len(t2)
        return {
            "score": -1,
            "matched_chars": 0,
            "total_chars": non_empty_len,
            "len_text1": len(t1),
            "len_text2": len(t2),
            "formula_string": "Metinlerden biri boş, hesaplama yapılamadı",
            "comparable": False,
        }

    matcher = difflib.SequenceMatcher(None, t1, t2)
    matched_chars = sum(triple.size for triple in matcher.get_matching_blocks())
    total_chars = len(t1) + len(t2)
    score = round(matcher.ratio(), 4)

    formula_string = (
        f"(2 × {matched_chars}) / {total_chars} = {score:.4f}"
    )

    return {
        "score": score,
        "matched_chars": matched_chars,
        "total_chars": total_chars,
        "len_text1": len(t1),
        "len_text2": len(t2),
        "formula_string": formula_string,
        "comparable": True,
    }


def cross_check(url: str, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates extracted article data against results obtained independently using Newspaper3k.
    
    Args:
        url: The web page URL.
        extracted_data: Dict of data extracted by NextScrape (title, content, author, date).
        
    Returns:
        A cross-check dictionary containing similarity scores, agreement flags, and 
        extracted values from both sources.
    """
    logger.info(f"Starting Newspaper3k cross-check validation for: {url}")
    
    newspaper_data = {
        "title": None,
        "content": None,
        "author": None,
        "date": None
    }
    
    # 1. Fetch page using Newspaper3k independently (handles network errors gracefully)
    try:
        article = Article(url)
        logger.info(f"Downloading page via Newspaper3k from: {url}")
        article.download()
        article.parse()
        
        newspaper_data["title"] = article.title.strip() if article.title else None
        newspaper_data["content"] = article.text.strip() if article.text else None
        newspaper_data["author"] = ", ".join(article.authors).strip() if article.authors else None
        
        if article.publish_date:
            if isinstance(article.publish_date, datetime):
                newspaper_data["date"] = article.publish_date.isoformat()
            else:
                newspaper_data["date"] = str(article.publish_date).strip()
        else:
            newspaper_data["date"] = None
            
        logger.info("Newspaper3k article parsing completed successfully.")
    except Exception as e:
        logger.error(f"Newspaper3k cross-check download/parse failed for {url}: {e}")
        # Keep values as None and proceed with comparison (similarity will be 0.0 for non-empty fields)

    # 2. Detailed similarity calculation for each field
    our_title = extracted_data.get("title")
    our_content = extracted_data.get("content")
    our_author = extracted_data.get("author")
    our_date = extracted_data.get("date")

    similarity_details = {
        "title":   calculate_similarity_detailed(our_title,   newspaper_data["title"]),
        "content": calculate_similarity_detailed(our_content, newspaper_data["content"]),
        "author":  calculate_similarity_detailed(our_author,  newspaper_data["author"]),
        "date":    calculate_similarity_detailed(our_date,    newspaper_data["date"]),
    }

    # Flat float scores (kept for backwards-compatibility with all callers)
    similarity_scores = {
        field: detail["score"]
        for field, detail in similarity_details.items()
    }

    # Agreement threshold >= 0.7 similarity (unavailable fields are not in agreement)
    agreement = {
        field: (similarity_scores[field] >= 0.7) if similarity_scores[field] != -1 else False
        for field in ["title", "content", "author", "date"]
    }

    # Weighted confidence score from AVAILABLE fields only
    # Weights: title=0.4, content=0.3, author=0.2, date=0.1
    field_weights = {
        "title": 0.4,
        "content": 0.3,
        "author": 0.2,
        "date": 0.1
    }
    
    available_weight_sum = 0.0
    weighted_score_sum = 0.0
    for field, weight in field_weights.items():
        score = similarity_scores[field]
        if score != -1:  # Only include available fields
            available_weight_sum += weight
            weighted_score_sum += weight * score
    
    if available_weight_sum > 0:
        confidence_score = round(weighted_score_sum / available_weight_sum, 2)
    else:
        confidence_score = 0.0  # No fields available for comparison
    
    # If title and content similarity are both high (>= 0.9), ensure confidence_score is >= 0.85
    title_sim = similarity_scores["title"]
    content_sim = similarity_scores["content"]
    if title_sim != -1 and content_sim != -1 and title_sim >= 0.9 and content_sim >= 0.9:
        confidence_score = max(confidence_score, 0.85)
    
    logger.info(
        f"Cross-check comparison completed. Confidence Score: {confidence_score} | "
        f"Title Sim: {similarity_scores['title']} | Content Sim: {similarity_scores['content']}"
    )

    return {
        "url": url,
        "our_extraction": {
            "title": our_title,
            "content": our_content,
            "author": our_author,
            "date": our_date
        },
        "newspaper_extraction": newspaper_data,
        "similarity_scores": similarity_scores,
        "similarity_details": similarity_details,
        "confidence_score": confidence_score,
        "agreement": agreement
    }


def batch_cross_check(urls: List[str]) -> Dict[str, Any]:
    """
    Executes cross-validation on multiple URLs using the full NextScrape pipeline.
    
    Args:
        urls: List of web page URLs.
        
    Returns:
        A dictionary containing aggregated pipeline statistics and results details.
    """
    logger.info(f"Starting batch cross-check for {len(urls)} URLs...")
    results = []
    successful_count = 0
    
    for url in urls:
        logger.info(f"Processing URL in batch: {url}")
        
        # 1. Fetch Page
        fetch_res = fetch_html(url)
        if fetch_res["status_code"] != 200 or fetch_res["error"] or not fetch_res["html"]:
            logger.error(f"Batch fetch failed for {url}. Status: {fetch_res['status_code']}, Error: {fetch_res['error']}")
            continue
            
        html = fetch_res["html"]
        
        try:
            # 2. Clean HTML content
            clean_res = clean_html(html)
            cleaned_html = clean_res["cleaned_html"]
            
            # 3. Check Cache or Run Validation Loop to obtain selectors
            rules = load_cached_rules(url)
            if rules:
                logger.info(f"Applying cached rule selectors for: {url}")
                extracted_data = apply_rules(html, rules)
            else:
                logger.info(f"No cached selectors found. Executing self-correcting validation loop for: {url}")
                loop_res = run_validation_loop(html, url)
                extracted_data = loop_res["final_extracted_data"]
                
            # 4. Execute Cross Check
            cc_res = cross_check(url, extracted_data)
            results.append(cc_res)
            successful_count += 1
            
        except Exception as e:
            logger.error(f"Failed to process {url} in batch cross-check: {e}")
            continue

    # Compute aggregate statistics
    avg_confidence = 0.0
    field_accuracy = {
        "title": 0.0,
        "content": 0.0,
        "author": 0.0,
        "date": 0.0
    }
    
    if successful_count > 0:
        total_conf = sum(res["confidence_score"] for res in results)
        avg_confidence = round(total_conf / successful_count, 2)
        
        # Average similarity per field, skipping -1 (unavailable) scores
        for field in ["title", "content", "author", "date"]:
            available_scores = [res["similarity_scores"][field] for res in results if res["similarity_scores"][field] != -1]
            if available_scores:
                field_accuracy[field] = round(sum(available_scores) / len(available_scores), 2)
            else:
                field_accuracy[field] = -1  # No data available for this field
        
    logger.info(
        f"Batch cross-check completed. Total URLs: {len(urls)} | Successful: {successful_count}/{len(urls)} | "
        f"Average Confidence: {avg_confidence}"
    )

    return {
        "total_urls": len(urls),
        "successful": successful_count,
        "average_confidence": avg_confidence,
        "field_accuracy": field_accuracy,
        "results": results
    }
