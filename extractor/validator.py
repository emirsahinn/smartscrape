import os
import time
import logging
import difflib
from datetime import datetime
from typing import Dict, Any, List, Optional

from bs4 import BeautifulSoup
from newspaper import Article

# Import project modules
from scraper.cleaner import clean_html
from extractor.blacklist import BlacklistManager
from extractor import rule_generator

# Set up logging
logger = logging.getLogger(__name__)


def validate_extraction(html: str, rules: Dict[str, Optional[str]], extracted_data: Dict[str, Any], url: str) -> Dict[str, Any]:
    """
    Runs a 3-stage validation process on the extracted article data to assess quality.
    
    STAGE 1: Rule Quality Check (DOM element existence and uniqueness checks)
    STAGE 2: Content Quality Check (Text length, author names, and semantic noise checks)
    STAGE 3: Cross-validation (difflib comparison against Newspaper3k parsed results)
    
    Args:
        html: The original raw HTML document.
        rules: Dict of CSS selectors applied.
        extracted_data: Dict of extracted values (title, content, author, date).
        url: The web page URL.
        
    Returns:
        A dictionary containing stage-specific outcomes, overall scores, and status flags.
    """
    logger.info("Starting 3-stage validation process...")
    start_time = time.perf_counter()
    soup = BeautifulSoup(html, "lxml")
    
    title = extracted_data.get("title") or ""
    content = extracted_data.get("content") or ""
    author = extracted_data.get("author") or ""
    date = extracted_data.get("date") or ""

    # ==========================================
    # STAGE 1: Extracted Data Quality Check (weighted scoring)
    # Weights: title=0.25, content=0.50, author=0.125, date=0.125
    # Pass threshold: >= 0.5 (title + content is enough to pass)
    # ==========================================
    logger.info("Validation STAGE 1: Checking extracted data quality...")
    
    checks = {}
    stage1_score = 0.0
    
    # 1. Title check (weight: 0.25)
    title_found = title is not None and len(title.strip()) > 5
    checks["title_found"] = title_found
    if title_found:
        stage1_score += 0.25
    
    # 2. Content check (weight: 0.50)
    content_found = content is not None and len(content.strip()) > 100
    checks["content_found"] = content_found
    checks["content_substantial"] = content_found
    if content_found:
        stage1_score += 0.50
        
    # 3. Author check (weight: 0.125)
    author_found = author is not None and len(author.strip()) > 0
    checks["author_found"] = author_found
    if author_found:
        stage1_score += 0.125
    
    # 4. Date check (weight: 0.125)
    date_found = date is not None and len(date.strip()) > 0
    checks["date_found"] = date_found
    if date_found:
        stage1_score += 0.125
    
    # Title uniqueness (informational, does not affect score)
    title_selector = rules.get("title")
    if title_selector:
        try:
            title_elements = soup.select(title_selector)
            checks["title_unique"] = len(title_elements) == 1
        except Exception:
            checks["title_unique"] = False
    else:
        checks["title_unique"] = False
    
    stage1_score = round(stage1_score, 2)
    stage1_passed = stage1_score >= 0.5
    
    logger.info(f"Stage 1 Score: {stage1_score} (Passed: {stage1_passed})")
    if not stage1_passed:
        logger.warning(f"Stage 1 failed - score {stage1_score} below 0.5. Details: {checks}")

    # ==========================================
    # STAGE 2: Content Quality Check
    # ==========================================
    logger.info("Validation STAGE 2: Checking content quality...")
    
    # Title validation: not empty, not purely numbers, length between 10 and 200 chars
    title_valid = (
        bool(title.strip()) and 
        not title.strip().isdigit() and 
        10 <= len(title.strip()) <= 200
    )
    
    # Content validation: not empty, > 100 words
    words = content.split()
    word_count = len(words)
    content_valid = bool(content.strip()) and word_count > 100
    
    # Author validation: if exists, must be 2-50 chars, not a URL
    author_valid = None
    if author:
        author_valid = (
            2 <= len(author.strip()) <= 50 and 
            not author.strip().startswith(("http://", "https://", "www."))
        )
        
    # Date validation: if exists, attempt to parse
    date_valid = None
    if date:
        date_valid = False
        try:
            from dateutil.parser import parse
            parse(str(date))
            date_valid = True
        except Exception:
            pass
            
    # Noise detection checks
    noise_indicators = []
    content_lower = content.lower()
    
    # Check for keyword spam
    spam_keywords = ["cookie", "javascript", "reklam", "advertisement"]
    for kw in spam_keywords:
        if kw in content_lower:
            noise_indicators.append(f"contains_{kw}")
            
    # Check for broadcast keywords in main content
    broadcast_words = ["canlı tv", "canlı yayın"]
    for bw in broadcast_words:
        if bw in content_lower:
            noise_indicators.append(f"contains_{bw.replace(' ', '_')}")
            
    # Link density check: mostly links if > 50% of words look like URLs
    url_count = sum(1 for w in words if w.startswith(("http://", "https://", "www.")))
    if word_count > 0 and (url_count / word_count) > 0.5:
        noise_indicators.append("mostly_urls")
        
    noise_detected = len(noise_indicators) > 0

    # Score calculation for Stage 2
    # Start at 1.0, apply penalties for failures
    stage2_score = 1.0
    if not title_valid:
        stage2_score -= 0.2
    if not content_valid:
        stage2_score -= 0.3
    if author and not author_valid:
        stage2_score -= 0.1
    if date and not date_valid:
        stage2_score -= 0.1
    if noise_detected:
        # Subtract 0.1 for each unique noise indicator up to a maximum penalty of 0.3
        penalty = min(len(noise_indicators) * 0.1, 0.3)
        stage2_score -= penalty
        
    stage2_score = round(max(stage2_score, 0.0), 2)
    stage2_passed = stage2_score >= 0.7
    
    logger.info(f"Stage 2 Score: {stage2_score} (Passed: {stage2_passed})")
    if not stage2_passed:
        logger.warning(
            f"Stage 2 failed - score {stage2_score} below 0.7. "
            f"Title Valid: {title_valid}, Content Valid: {content_valid}, Noise Indicators: {noise_indicators}"
        )

    # ==========================================
    # STAGE 3: Cross-validation with Newspaper3k
    # ==========================================
    logger.info("Validation STAGE 3: Running Newspaper3k cross-validation...")
    
    newspaper_title = ""
    newspaper_content = ""
    title_similarity = 0.0
    content_similarity = 0.0
    
    try:
        # Pass the HTML directly to newspaper's Article class to prevent duplicate requests
        article = Article(url)
        article.set_html(html)
        article.parse()
        
        newspaper_title = article.title or ""
        newspaper_content = article.text or ""
        
        # Calculate difflib similarity ratios
        if title.strip() and newspaper_title.strip():
            title_similarity = round(difflib.SequenceMatcher(None, title.lower().strip(), newspaper_title.lower().strip()).ratio(), 2)
        if content.strip() and newspaper_content.strip():
            content_similarity = round(difflib.SequenceMatcher(None, content.lower().strip(), newspaper_content.lower().strip()).ratio(), 2)
            
    except Exception as e:
        logger.error(f"Failed to cross-validate with Newspaper3k: {e}")
        
    # Stage 3 score is the average similarity of title and content
    stage3_score = round((title_similarity + content_similarity) / 2.0, 2)
    
    # Boost stage3 score if both similarities are high
    if title_similarity >= 0.8 and content_similarity >= 0.8:
        stage3_score = 0.95
    
    stage3_passed = title_similarity >= 0.5  # Flag potential error if title matching ratio is low
    
    logger.info(f"Stage 3 Score: {stage3_score} (Passed: {stage3_passed}, Title Similarity: {title_similarity})")

    # ==========================================
    # Overall Score & Aggregation
    # Stage weights: stage1=0.20, stage2=0.35, stage3=0.45
    overall_score = round((0.20 * stage1_score) + (0.35 * stage2_score) + (0.45 * stage3_score), 2)
    
    # If stage3 title_similarity >= 0.9 AND content_similarity >= 0.9:
    # overall_score should be >= 0.85 regardless of stage1
    if title_similarity >= 0.9 and content_similarity >= 0.9:
        overall_score = max(overall_score, 0.85)
    
    # Needs regeneration if stage1 fails (<0.5) or total quality is poor (<0.75)
    needs_regeneration = (stage1_score < 0.5) or (overall_score < 0.75)
    
    # Calculate how many stages met their quality thresholds (S1 >= 0.5, S2 >= 0.7, S3 >= 0.5)
    stages_passed_count = sum([
        1 if stage1_score >= 0.5 else 0,
        1 if stage2_score >= 0.7 else 0,
        1 if title_similarity >= 0.5 else 0
    ])
    
    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
    
    logger.info(
        f"Validation completed in {elapsed_ms} ms. "
        f"Overall Score: {overall_score} | Passed: {not needs_regeneration} | Needs Regeneration: {needs_regeneration}"
    )

    return {
        "stage1": {
            "passed": stage1_passed,
            "score": stage1_score,
            "details": {
                "title_found": checks["title_found"],
                "content_found": checks["content_found"],
                "author_found": checks["author_found"],
                "date_found": checks["date_found"],
                "title_unique": checks["title_unique"],
                "content_substantial": checks["content_substantial"]
            }
        },
        "stage2": {
            "passed": stage2_passed,
            "score": stage2_score,
            "details": {
                "title_valid": title_valid,
                "content_valid": content_valid,
                "author_valid": author_valid,
                "date_valid": date_valid,
                "noise_detected": noise_detected,
                "noise_indicators": noise_indicators
            }
        },
        "stage3": {
            "passed": stage3_passed,
            "score": stage3_score,
            "details": {
                "title_similarity": title_similarity,
                "content_similarity": content_similarity,
                "newspaper_title": newspaper_title,
                "newspaper_content": newspaper_content
            }
        },
        "overall_score": overall_score,
        "passed": not needs_regeneration,
        "needs_regeneration": needs_regeneration,
        "stages_passed": stages_passed_count,
        "validation_time_ms": elapsed_ms
    }


def run_validation_loop(html: str, url: str, max_attempts: int = 3) -> Dict[str, Any]:
    """
    Main self-correcting logic loop. Generates, applies, and validates extraction rules.
    If validation fails, blacklists selectors and regenerates with feedback.
    
    Args:
        html: The original raw HTML document.
        url: The web page URL.
        max_attempts: Maximum retries allowed.
        
    Returns:
        A summary dictionary of the final extraction outcomes and history:
        {
            "final_extracted_data": dict,
            "final_rules": dict,
            "validation_result": dict,
            "attempts_needed": int,
            "success": bool,
            "attempt_history": list
        }
    """
    logger.info(f"Starting self-correcting validation loop (Max Attempts: {max_attempts}) for {url}")
    
    # 1. Clean HTML to feed into the selector prompt
    clean_res = clean_html(html)
    cleaned_html = clean_res["cleaned_html"]
    
    attempt = 1
    attempt_history = []
    feedback = None
    
    final_rules = {}
    final_extracted_data = {}
    validation_result = {}
    success = False
    
    while attempt <= max_attempts:
        logger.info(f"\n--- Validation Loop: Attempt {attempt} of {max_attempts} ---")
        
        # 2. Generate CSS rules (passes feedback from prior attempts if available)
        gen_res = rule_generator.generate_rules(html, url, feedback=feedback)
        if not gen_res["success"]:
            logger.error(f"Rule generation failed on attempt {attempt}: {gen_res['error']}")
            attempt_history.append({
                "attempt": attempt,
                "score": 0.0,
                "failed_reason": f"Rule generation failed: {gen_res['error']}"
            })
            # Prepare simple feedback and retry
            feedback = f"Rule generation failed with error: {gen_res['error']}. Please try again."
            attempt += 1
            continue
            
        rules = gen_res["rules"]
        final_rules = rules
        
        # 3. Apply rules to extract content
        extracted_data = rule_generator.apply_rules(html, rules)
        final_extracted_data = extracted_data
        
        # 4. Validate extraction content
        val_res = validate_extraction(html, rules, extracted_data, url)
        validation_result = val_res
        
        overall_score = val_res["overall_score"]
        needs_regen = val_res["needs_regeneration"]
        
        # Check if validation succeeded
        if overall_score >= 0.75 and not needs_regen:
            logger.info(f"Validation succeeded on attempt {attempt} (Score: {overall_score})")
            attempt_history.append({
                "attempt": attempt,
                "score": overall_score,
                "failed_reason": None
            })
            success = True
            
            # Cache the successful rules
            rule_generator.cache_rules(url, rules, success_rate=overall_score)
            break
            
        # Attempt failed, calculate details and blacklist problematic selectors
        failed_reasons = []
        if not val_res["stage1"]["passed"]:
            failed_reasons.append(f"Stage 1 Rule Quality Check failed (score: {val_res['stage1']['score']})")
        if not val_res["stage2"]["passed"]:
            failed_reasons.append(f"Stage 2 Content Quality Check failed (score: {val_res['stage2']['score']})")
        if not val_res["stage3"]["passed"]:
            failed_reasons.append(f"Stage 3 Newspaper3k Cross-validation failed (score: {val_res['stage3']['score']})")
            
        failed_reason_str = ", ".join(failed_reasons)
        logger.warning(f"Attempt {attempt} failed validation (Score: {overall_score}). Reasons: {failed_reason_str}")
        
        attempt_history.append({
            "attempt": attempt,
            "score": overall_score,
            "failed_reason": failed_reason_str
        })
        
        if attempt < max_attempts:
            # Determine failed selectors to blacklist
            failed_selectors = []
            
            # If title failed validation
            if not val_res["stage1"]["details"]["title_found"] or not val_res["stage1"]["details"]["title_unique"] or not val_res["stage2"]["details"]["title_valid"]:
                sel = rules.get("title")
                if sel: failed_selectors.append(sel)
                
            # If content failed validation
            if not val_res["stage1"]["details"]["content_found"] or not val_res["stage1"]["details"]["content_substantial"] or not val_res["stage2"]["details"]["content_valid"]:
                sel = rules.get("content")
                if sel: failed_selectors.append(sel)
                
            # If optional fields were queried but failed to find matches
            if rules.get("author") and not val_res["stage1"]["details"]["author_found"]:
                failed_selectors.append(rules["author"])
            if rules.get("date") and not val_res["stage1"]["details"]["date_found"]:
                failed_selectors.append(rules["date"])
                
            # Add unique selectors to blacklist.json via add_to_blacklist function
            from extractor.blacklist import add_to_blacklist
            from extractor.rule_generator import get_domain
            domain = get_domain(url)
            for sel in failed_selectors:
                if sel:
                    add_to_blacklist(sel, domain, reason=failed_reason_str)
                
            # Formulate self-correcting feedback for the next generation
            feedback = "The previous CSS selectors failed validation for the following reasons:\n"
            feedback += "\n".join(f"- {r}" for r in failed_reasons)
            if failed_selectors:
                feedback += f"\nDo NOT use these failed CSS selectors: {', '.join(failed_selectors)}"
            feedback += "\nPlease analyze the HTML document structure and suggest alternative selectors."
            
        attempt += 1
        
    logger.info(f"Loop completed. Success: {success} | Attempts taken: {min(attempt, max_attempts)}")
    
    return {
        "final_extracted_data": final_extracted_data,
        "final_rules": final_rules,
        "validation_result": validation_result,
        "attempts_needed": min(attempt, max_attempts) if success else max_attempts,
        "success": success,
        "attempt_history": attempt_history
    }
