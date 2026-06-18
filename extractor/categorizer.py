import re
import logging
import urllib.parse
from typing import Dict, Any, List, Optional

# Set up logging
logger = logging.getLogger(__name__)

# Category definitions with Turkish and English keywords
CATEGORIES = {
    "SPOR": [
        "futbol", "basketbol", "voleybol", "galatasaray", "fenerbahçe", "beşiktaş",
        "trabzonspor", "maç", "gol", "transfer", "şampiyonlar", "lig", "milli takım",
        "süper lig", "tff", "şampiyon", "derbi", "stadyum", "antrenör", "teknik direktör",
        "sports", "football", "basketball", "match", "goal", "champion", "league"
    ],
    "TEKNOLOJİ": [
        "yapay zeka", "teknoloji", "telefon", "iphone", "android", "uygulama",
        "yazılım", "donanım", "internet", "siber", "robot", "bilişim", "dijital",
        "ai", "tech", "technology", "software", "hardware", "apple", "google",
        "microsoft", "samsung", "chatgpt", "openai", "startup"
    ],
    "EKONOMİ": [
        "dolar", "euro", "borsa", "faiz", "enflasyon", "bütçe", "ihracat", "ithalat",
        "ekonomi", "piyasa", "yatırım", "hisse", "merkez bankası", "kur", "tl",
        "economy", "inflation", "market", "dollar", "bank", "gdp", "trade"
    ],
    "SİYASET": [
        "cumhurbaşkanı", "meclis", "hükümet", "bakan", "parti", "seçim", "muhalefet",
        "erdoğan", "kılıçdaroğlu", "akp", "chp", "mhp", "tbmm", "milletvekili",
        "anayasa", "referandum", "koalisyon", "başbakan",
        "politics", "election", "government", "minister", "parliament", "vote"
    ],
    "SAĞLIK": [
        "sağlık", "hastane", "doktor", "ilaç", "hastalık", "covid", "aşı", "kanser",
        "tedavi", "ameliyat", "korona", "pandemi", "virüs", "tıp", "hemşire",
        "zehir", "uyuşturucu", "ölüm", "yaralı", "kaza", "ambulans",
        "acil", "toksin", "tehlike", "kimyasal",
        "health", "hospital", "doctor", "medicine", "disease", "vaccine", "medical"
    ],
    "EĞİTİM": [
        "okul", "üniversite", "öğrenci", "öğretmen", "eğitim", "sınav", "yks", "lgs",
        "meb", "mezuniyet", "burs", "staj", "akademik", "fakülte", "lisans",
        "education", "school", "university", "student", "exam", "teacher"
    ],
    "DÜNYA": [
        "dünya", "uluslararası", "avrupa birliği", "avrupa", "abd", "rusya", "çin",
        "ukrayna", "nato", "birleşmiş milletler", "savaş", "kriz", "dış politika",
        "ingiltere", "fransa", "almanya", "suriye", "iran", "israil",
        "world", "international", "war", "crisis", "europe", "russia", "china", "usa"
    ],
}

# Keywords that count double when matched (strong category indicators)
DOUBLE_WEIGHT_KEYWORDS = {
    "galatasaray", "fenerbahçe", "beşiktaş", "trabzonspor",
    "süper lig", "şampiyonlar", "milli takım",
}

# URL path segment hints for tiebreaking
URL_CATEGORY_HINTS = {
    "spor": "SPOR",
    "sport": "SPOR",
    "sports": "SPOR",
    "teknoloji": "TEKNOLOJİ",
    "tech": "TEKNOLOJİ",
    "technology": "TEKNOLOJİ",
    "ekonomi": "EKONOMİ",
    "economy": "EKONOMİ",
    "finans": "EKONOMİ",
    "finance": "EKONOMİ",
    "siyaset": "SİYASET",
    "politika": "SİYASET",
    "politics": "SİYASET",
    "saglik": "SAĞLIK",
    "health": "SAĞLIK",
    "egitim": "EĞİTİM",
    "education": "EĞİTİM",
    "dunya": "DÜNYA",
    "world": "DÜNYA",
    "gundem": "GÜNDEM",
}

# Category display colors for UI badges
CATEGORY_COLORS = {
    "SPOR": "#10B981",        # Green
    "TEKNOLOJİ": "#6366F1",   # Indigo
    "EKONOMİ": "#F59E0B",     # Amber
    "SİYASET": "#EF4444",     # Red
    "SAĞLIK": "#EC4899",      # Pink
    "EĞİTİM": "#3B82F6",     # Blue
    "DÜNYA": "#8B5CF6",       # Purple
    "GÜNDEM": "#6B7280",      # Gray
}


def categorize_article(title: str, content: str = "", url: str = "") -> Dict[str, Any]:
    """
    Automatically categorizes a news article based on keyword matching
    in the title, content preview, and URL path.
    
    Args:
        title: The article headline.
        content: The article body text (only first 200 chars are used).
        url: The article URL (used for tiebreaking).
        
    Returns:
        A dictionary with category, confidence, matched keywords, and all scores.
    """
    # Build the text to analyze: title + first 200 chars of content
    title_lower = (title or "").lower().strip()
    content_preview = (content or "")[:200].lower().strip()
    analysis_text = f"{title_lower} {content_preview}"
    
    # Count keyword matches for each category
    all_scores = {}
    all_matched = {}
    
    for category, keywords in CATEGORIES.items():
        matched_keywords = []
        score = 0
        for kw in keywords:
            # Use word boundary matching for short keywords to avoid false positives
            matched = False
            if len(kw) <= 3:
                pattern = r'\b' + re.escape(kw) + r'\b'
                if re.search(pattern, analysis_text, re.IGNORECASE):
                    matched = True
            else:
                if kw in analysis_text:
                    matched = True
            
            if matched:
                matched_keywords.append(kw)
                # Double weight for strong category indicators
                if kw in DOUBLE_WEIGHT_KEYWORDS:
                    score += 2
                else:
                    score += 1
        
        all_scores[category] = score
        all_matched[category] = matched_keywords
    
    # Find the category with the highest score
    max_score = max(all_scores.values()) if all_scores else 0
    
    if max_score == 0:
        # No keywords matched — try URL path as last resort
        url_category = _get_category_from_url(url)
        if url_category and url_category != "GÜNDEM":
            logger.info(f"No keyword matches. Using URL hint: {url_category}")
            return {
                "category": url_category,
                "confidence": 0.4,
                "matched_keywords": [],
                "all_scores": all_scores
            }
        # Default to GÜNDEM
        return {
            "category": "GÜNDEM",
            "confidence": 0.3,
            "matched_keywords": [],
            "all_scores": all_scores
        }
    
    # Get all categories with the max score (for tiebreaking)
    top_categories = [cat for cat, score in all_scores.items() if score == max_score]
    
    if len(top_categories) == 1:
        winner = top_categories[0]
    else:
        # Tiebreaker: use URL path keywords
        url_category = _get_category_from_url(url)
        if url_category in top_categories:
            winner = url_category
        else:
            # Pick the first in our defined order
            category_order = list(CATEGORIES.keys())
            winner = min(top_categories, key=lambda c: category_order.index(c))
    
    # Calculate confidence based on match density
    total_keywords_in_category = len(CATEGORIES[winner])
    matched_count = all_scores[winner]
    confidence = min(round(matched_count / max(total_keywords_in_category * 0.3, 1), 2), 1.0)
    
    logger.info(
        f"Article categorized as {winner} (confidence: {confidence}, "
        f"matched: {all_matched[winner]})"
    )
    
    return {
        "category": winner,
        "confidence": confidence,
        "matched_keywords": all_matched[winner],
        "all_scores": all_scores
    }


def categorize_news_list(headlines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Categorizes a list of news headlines by their title and URL.
    
    Args:
        headlines: List of dicts with at least 'title' and 'url' keys.
        
    Returns:
        The same list with 'category' and 'category_confidence' added to each item.
    """
    logger.info(f"Categorizing {len(headlines)} headlines...")
    
    for item in headlines:
        title = item.get("title", "")
        url = item.get("url", "")
        
        cat_res = categorize_article(title=title, content="", url=url)
        item["category"] = cat_res["category"]
        item["category_confidence"] = cat_res["confidence"]
    
    # Log category distribution
    distribution = {}
    for item in headlines:
        cat = item.get("category", "GÜNDEM")
        distribution[cat] = distribution.get(cat, 0) + 1
    logger.info(f"Category distribution: {distribution}")
    
    return headlines


def get_category_color(category: str) -> str:
    """Returns the hex color code for a given category."""
    return CATEGORY_COLORS.get(category, CATEGORY_COLORS["GÜNDEM"])


def get_all_categories() -> List[str]:
    """Returns all available category names including GÜNDEM."""
    return list(CATEGORIES.keys()) + ["GÜNDEM"]


def _get_category_from_url(url: str) -> Optional[str]:
    """Extracts a category hint from the URL path segments."""
    if not url:
        return None
    
    try:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.lower().strip("/")
        segments = path.split("/")
        
        for segment in segments:
            if segment in URL_CATEGORY_HINTS:
                return URL_CATEGORY_HINTS[segment]
    except Exception:
        pass
    
    return None
