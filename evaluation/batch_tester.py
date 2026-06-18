import os
import json
import time
import logging
from typing import List, Dict, Any, Callable, Optional

# Project imports
from scraper.fetcher import fetch_html
from scraper.cleaner import clean_html
from extractor.validator import run_validation_loop
from evaluation.cross_checker import cross_check
from extractor.categorizer import categorize_article
from extractor.rule_generator import get_domain
from scraper.detector import detect_site_type

# Set up logging
logger = logging.getLogger(__name__)

def run_batch_test(urls: List[str], progress_callback: Optional[Callable[[int, int, str, Dict[str, Any], List[Dict[str, Any]]], None]] = None) -> Dict[str, Any]:
    """
    Runs automated batch testing across multiple URLs and generates research paper statistics.
    Saves intermediate results to data/batch_results.json after each URL.
    """
    logger.info(f"Starting batch test for {len(urls)} URLs...")
    results = []
    
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    batch_results_path = "data/batch_results.json"
    
    total_urls = len(urls)
    
    for idx, url in enumerate(urls, 1):
        domain = get_domain(url)
        logger.info(f"Processing batch URL {idx}/{total_urls}: {url}")
        
        result_item = {
            "url": url,
            "domain": domain,
            "site_type": "unknown",
            "title_found": False,
            "content_found": False,
            "author_found": False,
            "date_found": False,
            "confidence_score": 0.0,
            "attempts_needed": 0,
            "stage1_score": 0.0,
            "stage2_score": 0.0,
            "stage3_score": 0.0,
            "title_similarity": 0.0,
            "content_similarity": 0.0,
            "regex_noise_reduction": 0.0,
            "regex_stats": None,
            "size_reduction_pct": 0.0,
            "category": "GÜNDEM",
            "fetch_time_ms": 0,
            "llm_time_ms": 0,
            "blacklist_triggered": False,
            "error": None
        }
        
        try:
            # 1. Fetch HTML
            fetch_res = fetch_html(url)
            result_item["fetch_time_ms"] = fetch_res.get("fetch_time_ms", 0)
            
            status_code = fetch_res.get("status_code")
            fetch_err = fetch_res.get("error")
            
            if status_code == 404 or (fetch_err and "404" in str(fetch_err)):
                result_item["error"] = "Erişilemedi"
            else:
                if fetch_err:
                    raise Exception(f"Fetch error: {fetch_err}")
                    
                raw_html = fetch_res["html"]
                if not raw_html:
                    raise Exception("Empty HTML content received")
                    
                # 2. Clean HTML
                clean_res = clean_html(raw_html)
                result_item["size_reduction_pct"] = clean_res.get("reduction_percent", 0.0)
                
                # 3. Detect Site Type
                detect_res = detect_site_type(url, raw_html)
                result_item["site_type"] = detect_res.get("site_type", "unknown")
                
                # 4. LLM Validation Loop
                llm_start = time.perf_counter()
                loop_res = run_validation_loop(raw_html, url, max_attempts=3)
                result_item["llm_time_ms"] = int((time.perf_counter() - llm_start) * 1000)
                
                final_extracted_data = loop_res["final_extracted_data"]
                final_rules = loop_res["final_rules"]
                validation_result = loop_res["validation_result"]
                attempts_needed = loop_res["attempts_needed"]
                
                result_item["attempts_needed"] = attempts_needed
                result_item["blacklist_triggered"] = attempts_needed > 1
                
                # Extract stage scores
                result_item["stage1_score"] = validation_result.get("stage1", {}).get("score", 0.0)
                result_item["stage2_score"] = validation_result.get("stage2", {}).get("score", 0.0)
                result_item["stage3_score"] = validation_result.get("stage3", {}).get("score", 0.0)
                
                # 5. Cross Check
                cc_res = cross_check(url, final_extracted_data)
                result_item["confidence_score"] = cc_res.get("confidence_score", 0.0)
                
                sim_scores = cc_res.get("similarity_scores", {})
                result_item["title_similarity"] = sim_scores.get("title", 0.0)
                result_item["content_similarity"] = sim_scores.get("content", 0.0)
                
                # 6. RegEx Noise Reduction
                regex_stats = final_extracted_data.get("regex_stats") or {}
                result_item["regex_noise_reduction"] = regex_stats.get("improvement", {}).get("noise_reduction_percent", 0.0)
                result_item["regex_stats"] = regex_stats
                
                # 7. Categorization
                cat_res = categorize_article(
                    title=final_extracted_data.get("title", ""),
                    content=final_extracted_data.get("content", ""),
                    url=url
                )
                result_item["category"] = cat_res.get("category", "GÜNDEM")
                
                # Determine field found status
                result_item["title_found"] = final_extracted_data.get("title") is not None and len(str(final_extracted_data.get("title")).strip()) > 5
                result_item["content_found"] = final_extracted_data.get("content") is not None and len(str(final_extracted_data.get("content")).strip()) > 100
                result_item["author_found"] = final_extracted_data.get("author") is not None
                result_item["date_found"] = final_extracted_data.get("date") is not None
        except Exception as e:
            logger.error(f"Error in batch testing for {url}: {e}")
            result_item["error"] = str(e)
            
        results.append(result_item)
        
        # Calculate statistics for the run so far
        stats_data = _calculate_stats(results)
        
        # Save to json file after each URL
        with open(batch_results_path, "w", encoding="utf-8") as f:
            json.dump(stats_data, f, ensure_ascii=False, indent=2)
            
        # Trigger progress callback if present
        if progress_callback is not None:
            try:
                progress_callback(idx, total_urls, domain, result_item, results)
            except Exception as cb_err:
                logger.error(f"Error in progress callback: {cb_err}")
            
    return _calculate_stats(results)

def _calculate_stats(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Helper to calculate per-domain and overall stats from results list."""
    total_urls = len(results)
    successful_list = [r for r in results if r["error"] is None]
    failed_list = [r for r in results if r["error"] is not None]
    
    successful_count = len(successful_list)
    failed_count = len(failed_list)
    
    # Per Domain Stats
    per_domain = {}
    for r in results:
        dom = r["domain"]
        if dom not in per_domain:
            per_domain[dom] = {
                "total": 0,
                "successful": 0,
                "confidence_sum": 0.0,
                "attempts_sum": 0
            }
        
        per_domain[dom]["total"] += 1
        if r["error"] is None:
            per_domain[dom]["successful"] += 1
            per_domain[dom]["confidence_sum"] += r["confidence_score"]
            per_domain[dom]["attempts_sum"] += r["attempts_needed"]
            
    per_domain_stats = {}
    for dom, stats in per_domain.items():
        succ = stats["successful"]
        per_domain_stats[dom] = {
            "total": stats["total"],
            "successful": succ,
            "avg_confidence": round(stats["confidence_sum"] / max(succ, 1), 2) if succ > 0 else 0.0,
            "avg_attempts": round(stats["attempts_sum"] / max(succ, 1), 2) if succ > 0 else 0.0
        }
        
    # Overall Stats
    overall_stats = {
        "avg_confidence": 0.0,
        "avg_attempts": 0.0,
        "title_found_rate": 0.0,
        "content_found_rate": 0.0,
        "author_found_rate": 0.0,
        "date_found_rate": 0.0,
        "solved_attempt_1": 0,
        "solved_attempt_2": 0,
        "solved_attempt_3": 0,
        "failed_all": 0,
        "avg_size_reduction": 0.0,
        "avg_regex_noise_reduction": 0.0,
        "avg_fetch_time_ms": 0,
        "avg_llm_time_ms": 0
    }
    
    if total_urls > 0:
        overall_stats["title_found_rate"] = round(sum(1 for r in results if r["title_found"]) / total_urls, 2)
        overall_stats["content_found_rate"] = round(sum(1 for r in results if r["content_found"]) / total_urls, 2)
        overall_stats["author_found_rate"] = round(sum(1 for r in results if r["author_found"]) / total_urls, 2)
        overall_stats["date_found_rate"] = round(sum(1 for r in results if r["date_found"]) / total_urls, 2)
        
    if successful_count > 0:
        overall_stats["avg_confidence"] = round(sum(r["confidence_score"] for r in successful_list) / successful_count, 2)
        overall_stats["avg_attempts"] = round(sum(r["attempts_needed"] for r in successful_list) / successful_count, 2)
        overall_stats["solved_attempt_1"] = sum(1 for r in successful_list if r["attempts_needed"] == 1)
        overall_stats["solved_attempt_2"] = sum(1 for r in successful_list if r["attempts_needed"] == 2)
        overall_stats["solved_attempt_3"] = sum(1 for r in successful_list if r["attempts_needed"] == 3)
        overall_stats["avg_size_reduction"] = round(sum(r["size_reduction_pct"] for r in successful_list) / successful_count, 1)
        overall_stats["avg_regex_noise_reduction"] = round(sum(r["regex_noise_reduction"] for r in successful_list) / successful_count, 1)
        overall_stats["avg_fetch_time_ms"] = int(sum(r["fetch_time_ms"] for r in successful_list) / successful_count)
        overall_stats["avg_llm_time_ms"] = int(sum(r["llm_time_ms"] for r in successful_list) / successful_count)
        
    overall_stats["failed_all"] = failed_count
    
    return {
        "total_urls": total_urls,
        "successful": successful_count,
        "failed": failed_count,
        "results": results,
        "per_domain_stats": per_domain_stats,
        "overall_stats": overall_stats
    }
