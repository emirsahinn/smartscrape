import sys
import logging
from scraper.fetcher import fetch_html
from scraper.cleaner import clean_html, extract_main_content
from scraper.detector import detect_site_type, is_article_page

# Set logging level to WARNING to keep the pipeline stdout report clean and readable
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

def run_pipeline():
    urls = [
        "https://www.milliyet.com.tr/spor/besiktasta-ersin-destanoglu-yol-ayriminda-avrupa-karari-7592245",
        "https://www.ntv.com.tr/teknoloji",
        "https://www.bbc.com/turkce"
    ]
    
    total_tested = len(urls)
    successful_fetches = 0
    size_reductions = []
    word_counts = []
    
    for url in urls:
        print("=" * 40)
        print(f"URL: {url}")
        print("=" * 40)
        
        # 1. Fetch HTML page content
        fetch_res = fetch_html(url)
        status_code = fetch_res["status_code"]
        fetch_time = fetch_res["fetch_time_ms"]
        error = fetch_res["error"]
        
        # Check if the fetch succeeded
        if error or status_code != 200 or not fetch_res["html"]:
            error_details = error if error else f"Status Code {status_code}"
            print(f"✗ Fetch Status    : Failed ({error_details})")
            print(f"✗ Fetch Time      : {fetch_time}ms" if fetch_time else "✗ Fetch Time      : N/A")
            print("✗ Original Size   : N/A")
            print("✗ Cleaned Size    : N/A")
            print("✗ Reduction       : N/A")
            print("✗ Word Count      : N/A")
            print("✗ Language        : N/A")
            print("✗ Site Type       : N/A")
            print("✗ Is Article Page : N/A")
            print("✗ Selector Used   : N/A")
            print("=" * 40)
            print()
            continue
            
        successful_fetches += 1
        html = fetch_res["html"]
        
        # 2. Clean HTML content
        clean_res = clean_html(html)
        cleaned_html = clean_res["cleaned_html"]
        orig_size = clean_res["original_size_bytes"]
        clean_size = clean_res["cleaned_size_bytes"]
        reduction = clean_res["reduction_percent"]
        
        # 3. Extract main content
        main_res = extract_main_content(cleaned_html)
        word_count = main_res["word_count"]
        selector_used = main_res["selector_used"]
        
        # 4. Classify site category & detect language
        detect_res = detect_site_type(url, html)
        site_type = detect_res["site_type"]
        confidence = detect_res["confidence"]
        lang = detect_res["language"]
        
        # 5. Run article heuristics
        is_article = is_article_page(url, html)
        
        # Record stats for successful runs
        size_reductions.append(reduction)
        word_counts.append(word_count)
        
        # Format sizes with commas for readability
        orig_size_str = f"{orig_size:,}"
        clean_size_str = f"{clean_size:,}"
        
        print(f"✓ Fetch Status    : {status_code}")
        print(f"✓ Fetch Time      : {fetch_time}ms")
        print(f"✓ Original Size   : {orig_size_str} bytes")
        print(f"✓ Cleaned Size    : {clean_size_str} bytes")
        print(f"✓ Reduction       : {reduction}%")
        print(f"✓ Word Count      : {word_count} words")
        print(f"✓ Language        : {lang}")
        print(f"✓ Site Type       : {site_type} (confidence: {confidence})")
        print(f"✓ Is Article Page : {is_article}")
        print(f"✓ Selector Used   : {selector_used}")
        print("=" * 40)
        print()
        
    # Print Summary statistics
    avg_reduction = sum(size_reductions) / len(size_reductions) if size_reductions else 0.0
    avg_words = sum(word_counts) / len(word_counts) if word_counts else 0.0
    
    print("SUMMARY")
    print(f"- Total URLs tested: {total_tested}")
    print(f"- Successful fetches: {successful_fetches}/{total_tested}")
    print(f"- Average size reduction: {avg_reduction:.1f}%")
    print(f"- Average word count: {int(avg_words)}")

if __name__ == "__main__":
    run_pipeline()
