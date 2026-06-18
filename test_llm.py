import sys
import os
import time

# Ensure project root is in the path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from scraper.fetcher import fetch_html
from scraper.cleaner import clean_html, extract_main_content
from extractor.rule_generator import generate_rules, apply_rules
from extractor.validator import run_validation_loop

def run_llm_test():
    url = "https://www.milliyet.com.tr/spor/besiktasta-ersin-destanoglu-yol-ayriminda-avrupa-karari-7592245"
    max_attempts = 3
    
    # 1. Fetch HTML
    fetch_result = fetch_html(url)
    if fetch_result["status_code"] != 200 or fetch_result["error"]:
        print(f"Error fetching URL {url}: {fetch_result['error']}")
        return

    # 2. Clean HTML
    cleaned = clean_html(fetch_result["html"])

    # 3. Extract main content
    main_content = extract_main_content(cleaned["cleaned_html"])

    # 4. Generate rules
    rules_res = generate_rules(fetch_result["html"], url)
    rules = rules_res.get("rules") or {}
    llm_time = rules_res.get("generation_time_ms") or 0

    # 5. Apply rules
    extracted = apply_rules(fetch_result["html"], rules)

    # 6. Run validation loop
    loop_res = run_validation_loop(fetch_result["html"], url, max_attempts=max_attempts)
    val_res = loop_res.get("validation_result") or {}

    # Format output fields safely
    extracted_title = extracted.get("title") or "None"
    extracted_content = extracted.get("content") or ""
    extracted_content_snippet = (
        f'"{extracted_content[:150]}..."'
        if extracted_content else "None"
    )
    extracted_author = extracted.get("author") or "None"
    extracted_date = extracted.get("date") or "None"
    success_rate = extracted.get("success_rate", 0.0)

    # Stages pass/fail text
    stage1_res = val_res.get("stage1") or {}
    stage2_res = val_res.get("stage2") or {}
    stage3_res = val_res.get("stage3") or {}

    stage1_status = "PASS" if stage1_res.get("passed") else "FAIL"
    stage1_score = stage1_res.get("score") or 0.0

    stage2_status = "PASS" if stage2_res.get("passed") else "FAIL"
    stage2_score = stage2_res.get("score") or 0.0

    stage3_status = "PASS" if stage3_res.get("passed") else "FAIL"
    stage3_score = stage3_res.get("score") or 0.0

    overall_score = val_res.get("overall_score") or 0.0
    attempts_needed = loop_res.get("attempts_needed") or max_attempts

    print("========================================")
    print("LLM RULE GENERATION TEST")
    print("========================================")
    print(f"URL: {url}")
    print("----------------------------------------")
    print("GENERATED RULES:")
    print(f"  title   : {rules.get('title')}")
    print(f"  content : {rules.get('content')}")
    print(f"  author  : {rules.get('author')}")
    print(f"  date    : {rules.get('date')}")
    print(f"LLM Response Time: {llm_time}ms")
    print("----------------------------------------")
    print("EXTRACTED DATA:")
    print(f"  Title   : \"{extracted_title}\"")
    print(f"  Content : {extracted_content_snippet}")
    print(f"  Author  : \"{extracted_author}\"")
    print(f"  Date    : \"{extracted_date}\"")
    print(f"  Success Rate: {success_rate:.2f}")
    print("----------------------------------------")
    print("VALIDATION RESULTS:")
    print(f"  Stage 1 (Rule Quality)   : {stage1_status} ({stage1_score:.2f})")
    print(f"  Stage 2 (Content Quality): {stage2_status} ({stage2_score:.2f})")
    print(f"  Stage 3 (Newspaper3k)    : {stage3_status} ({stage3_score:.2f})")
    print(f"  Overall Score            : {overall_score:.2f}")
    print(f"  Attempts Needed          : {attempts_needed}")
    print("========================================")

if __name__ == "__main__":
    run_llm_test()
