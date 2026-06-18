import re
from typing import Dict, Any

def apply_regex_filters(text: str) -> Dict[str, Any]:
    """
    Applies a series of RegEx filters to clean the extracted news content.
    Returns the cleaned text along with statistics about what was removed.
    """
    if not text:
        text = ""
        
    original_text = text
    original_length = len(text)
    
    # Track metrics
    filters_applied = {
        "html_entities_removed": 0,
        "urls_removed": 0,
        "social_noise_removed": 0,
        "datetime_noise_removed": 0,
        "hashtags_removed": 0,
        "short_lines_removed": 0
    }
    
    current_text = text
    
    # FILTER 1 - Remove HTML entities:
    # pattern: r'&[a-zA-Z]+;|&#[0-9]+;'
    pattern_html = r'&[a-zA-Z]+;|&#[0-9]+;'
    current_text, count_html = re.subn(pattern_html, "", current_text)
    filters_applied["html_entities_removed"] = count_html
    
    # FILTER 2 - Remove URLs:
    # pattern: r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    pattern_url = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    current_text, count_url = re.subn(pattern_url, "", current_text)
    filters_applied["urls_removed"] = count_url
    
    # FILTER 3 - Remove social media noise:
    # pattern: r'(Paylaş|Tweete|Facebook|Twitter|Instagram|WhatsApp|Telegram|LinkedIn|Pinterest|Copy|Kopyala|Share)[^\n]*'
    pattern_social = r'(Paylaş|Tweete|Facebook|Twitter|Instagram|WhatsApp|Telegram|LinkedIn|Pinterest|Copy|Kopyala|Share)[^\n]*'
    current_text, count_social = re.subn(pattern_social, "", current_text)
    filters_applied["social_noise_removed"] = count_social
    
    # FILTER 4 - Remove date/time noise:
    # pattern: r'\d{2}\.\d{2}\.\d{4}\s*[-|]\s*\d{2}:\d{2}'
    pattern_datetime = r'\d{2}\.\d{2}\.\d{4}\s*[-|]\s*\d{2}:\d{2}'
    current_text, count_datetime = re.subn(pattern_datetime, "", current_text)
    filters_applied["datetime_noise_removed"] = count_datetime
    
    # FILTER 5 - Remove hashtags:
    # pattern: r'#\w+'
    pattern_hashtag = r'#\w+'
    current_text, count_hashtag = re.subn(pattern_hashtag, "", current_text)
    filters_applied["hashtags_removed"] = count_hashtag
    
    # FILTER 6 - Remove excessive whitespace:
    # pattern: r'\n{3,}' → replace with '\n\n'
    # pattern: r' {2,}' → replace with ' '
    current_text = re.sub(r'\n{3,}', '\n\n', current_text)
    current_text = re.sub(r' {2,}', ' ', current_text)
    
    # FILTER 7 - Remove short noise lines:
    # Split by newline, remove lines < 20 chars, rejoin
    lines = current_text.split('\n')
    filtered_lines = []
    removed_lines_count = 0
    for line in lines:
        if len(line.strip()) >= 20:
            filtered_lines.append(line)
        else:
            if line.strip():  # Only count as removed if it wasn't already empty space
                removed_lines_count += 1
                
    current_text = '\n'.join(filtered_lines)
    filters_applied["short_lines_removed"] = removed_lines_count
    
    filtered_length = len(current_text)
    
    # Reduction percentage
    reduction_percent = 0.0
    if original_length > 0:
        reduction_percent = round(((original_length - filtered_length) / original_length) * 100, 1)
        
    total_items_removed = sum(filters_applied.values())
    
    return {
        "original_text": original_text,
        "filtered_text": current_text,
        "original_length": original_length,
        "filtered_length": filtered_length,
        "reduction_percent": reduction_percent,
        "filters_applied": filters_applied,
        "total_items_removed": total_items_removed
    }

def compare_with_without_regex(raw_text: str) -> Dict[str, Any]:
    """
    Compares the noise level in the text before and after applying regex filters.
    """
    if not raw_text:
        raw_text = ""
        
    # Get filtered text
    filtered_res = apply_regex_filters(raw_text)
    filtered_text = filtered_res["filtered_text"]
    
    # Noise indicators - covers social share buttons, ad labels, nav/footer noise
    # typically found in a full-page get_text() dump
    noise_indicators = [
        "Paylaş", "Kopyala", "Facebook", "Twitter", "Instagram", "WhatsApp",
        "Telegram", "LinkedIn", "Pinterest", "Share", "Tweet",
        "Son Güncelleme", "Son güncelleme", "Güncelleme Tarihi",
        "İlgili Haberler", "İlgili Haber", "Önerilen Haberler",
        "Reklam", "Advertisement", "Sponsored", "Sponsorlu",
        "Abone Ol", "Takip Et", "Bizi Takip", "Newsletter",
        "Çerez", "Cookie", "Gizlilik", "Kullanım Koşulları",
        "#", "http",
    ]

    def get_stats(text: str) -> Dict[str, Any]:
        txt_len = len(text)
        words = text.split()
        word_count = len(words)
        
        # Count occurrences of noise indicators (case-insensitive for robust matching)
        noise_count = 0
        text_lower = text.lower()
        for ind in noise_indicators:
            noise_count += text_lower.count(ind.lower())
            
        noise_ratio = 0.0
        if word_count > 0:
            noise_ratio = round(noise_count / word_count, 3)
            
        return {
            "text_length": txt_len,
            "noise_count": noise_count,
            "noise_ratio": noise_ratio,
            "word_count": word_count
        }
        
    without_regex = get_stats(raw_text)
    with_regex = get_stats(filtered_text)
    
    # Calculate improvements
    noise_red_pct = 0.0
    if without_regex["noise_count"] > 0:
        noise_red_pct = round(((without_regex["noise_count"] - with_regex["noise_count"]) / without_regex["noise_count"]) * 100, 1)
        
    len_red_pct = filtered_res["reduction_percent"]
    
    # Clarity improvement label
    if noise_red_pct >= 80:
        clarity = "Yüksek"
    elif noise_red_pct >= 40:
        clarity = "Orta"
    elif noise_red_pct > 0:
        clarity = "Düşük"
    else:
        clarity = "Yok"
        
    return {
        "without_regex": without_regex,
        "with_regex": with_regex,
        "improvement": {
            "noise_reduction_percent": noise_red_pct,
            "length_reduction_percent": len_red_pct,
            "clarity_improvement": clarity
        },
        "filters_applied": filtered_res["filters_applied"],
        "total_items_removed": filtered_res["total_items_removed"]
    }

