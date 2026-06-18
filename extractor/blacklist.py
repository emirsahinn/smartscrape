import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

# Set up logging
logger = logging.getLogger(__name__)

DEFAULT_BLACKLIST = {
    "global": [
        ".advertisement", ".ads", ".reklam", ".banner",
        ".sidebar", ".related-news", ".son-dakika-list",
        ".navigation", ".menu", ".footer-content",
        "#comments", ".comment-section", ".social-share",
        ".cookie-notice", ".newsletter-signup"
    ],
    "by_domain": {}
}


def _get_blacklist_path() -> str:
    """
    Returns the absolute path to the data/blacklist.json file.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "data", "blacklist.json")


def load_blacklist() -> Dict[str, Any]:
    """
    Loads the blacklist dictionary from data/blacklist.json.
    If the file doesn't exist, creates it with default blacklisted selectors.
    
    Returns:
        The blacklist dictionary containing "global" and "by_domain" keys.
    """
    file_path = _get_blacklist_path()
    
    # Ensure parent directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    if not os.path.exists(file_path):
        logger.info(f"Blacklist file not found at {file_path}. Creating with defaults...")
        try:
            with open(file_path, "w") as f:
                json.dump(DEFAULT_BLACKLIST, f, indent=4)
            return DEFAULT_BLACKLIST
        except Exception as e:
            logger.error(f"Failed to create default blacklist file: {e}")
            return DEFAULT_BLACKLIST
            
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
            # Schema integrity check
            if "global" not in data:
                data["global"] = DEFAULT_BLACKLIST["global"]
            if "by_domain" not in data:
                data["by_domain"] = {}
            return data
    except Exception as e:
        logger.error(f"Failed to load blacklist from {file_path}: {e}. Returning defaults.")
        return DEFAULT_BLACKLIST


def add_to_blacklist(selector: str, domain: str, reason: str) -> None:
    """
    Adds a selector to the blacklist for a specific domain.
    Promotes the selector to the global blacklist if it is blacklisted on 3 or more distinct domains.
    
    Args:
        selector: The CSS selector to blacklist.
        domain: The domain where the selector failed.
        reason: The reason for blacklisting.
    """
    if not selector:
        return

    blacklist_data = load_blacklist()
    
    by_domain = blacklist_data["by_domain"]
    if domain not in by_domain:
        by_domain[domain] = []
        
    domain_list = by_domain[domain]
    
    # Check if selector is already listed for this domain
    existing_item = None
    for item in domain_list:
        if item.get("selector") == selector:
            existing_item = item
            break
            
    if existing_item:
        existing_item["times_failed"] = existing_item.get("times_failed", 1) + 1
        existing_item["reason"] = reason
        existing_item["added_at"] = datetime.now().isoformat()
        logger.info(f"Updated selector '{selector}' count for domain '{domain}'. Failures: {existing_item['times_failed']}")
    else:
        domain_list.append({
            "selector": selector,
            "reason": reason,
            "added_at": datetime.now().isoformat(),
            "times_failed": 1
        })
        logger.info(f"Blacklisted selector '{selector}' for domain '{domain}'. Reason: {reason}")
        
    # Promotion Check: Promote to global if seen on 3+ different domains
    all_domains_with_selector = set()
    for dom, items in by_domain.items():
        for item in items:
            if item.get("selector") == selector:
                all_domains_with_selector.add(dom)
                
    if len(all_domains_with_selector) >= 3:
        if selector not in blacklist_data["global"]:
            blacklist_data["global"].append(selector)
            logger.info(f"Selector '{selector}' has failed on {len(all_domains_with_selector)} domains. Promoting to global blacklist.")
            
    # Save back to file
    file_path = _get_blacklist_path()
    try:
        with open(file_path, "w") as f:
            json.dump(blacklist_data, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save blacklist to {file_path}: {e}")


def is_blacklisted(selector: str, domain: str) -> bool:
    """
    Checks if a selector is in the global blacklist or the domain-specific blacklist.
    
    Args:
        selector: The CSS selector to check.
        domain: The domain scope.
        
    Returns:
        True if the selector is blacklisted, False otherwise.
    """
    if not selector:
        return False
        
    blacklist_data = load_blacklist()
    
    # 1. Check global list
    if selector in blacklist_data.get("global", []):
        return True
        
    # 2. Check domain-specific list
    domain_list = blacklist_data.get("by_domain", {}).get(domain, [])
    if any(item.get("selector") == selector for item in domain_list):
        return True
        
    return False


def filter_rules(rules: Dict[str, Optional[str]], domain: str) -> Dict[str, Optional[str]]:
    """
    Filters out any blacklisted selectors from the generated rules dict, replacing them with None.
    
    Args:
        rules: Dict of generated CSS selectors.
        domain: The domain scope.
        
    Returns:
        A cleaned rules dictionary.
    """
    logger.info(f"Filtering rule selectors against blacklist for domain: {domain}")
    cleaned_rules = {}
    
    for field, selector in rules.items():
        if selector and is_blacklisted(selector, domain):
            logger.warning(f"Filtered blacklisted selector '{selector}' from field '{field}' on domain '{domain}'.")
            cleaned_rules[field] = None
        else:
            cleaned_rules[field] = selector
            
    return cleaned_rules


def get_blacklist_stats() -> Dict[str, Any]:
    """
    Returns statistics about the blacklist for research reporting purposes.
    
    Returns:
        A dictionary containing global count, unique domains count,
        total domain-specific selector count, and top most failed selectors.
    """
    blacklist_data = load_blacklist()
    
    global_list = blacklist_data.get("global", [])
    by_domain = blacklist_data.get("by_domain", {})
    
    # Total unique domain-specific items count
    total_domain_specific = sum(len(items) for items in by_domain.values())
    
    # Find top problematic selectors based on times_failed
    selector_failures = {}
    for dom, items in by_domain.items():
        for item in items:
            sel = item.get("selector")
            if sel:
                selector_failures[sel] = selector_failures.get(sel, 0) + item.get("times_failed", 1)
                
    # Sort descending
    sorted_selectors = sorted(selector_failures.items(), key=lambda x: x[1], reverse=True)
    most_problematic = [sel for sel, count in sorted_selectors[:5]]
    
    return {
        "total_global_blacklisted": len(global_list),
        "domains_with_blacklist": len(by_domain),
        "most_problematic_selectors": most_problematic,
        "total_domain_specific": total_domain_specific
    }


# Backwards compatibility class wrapper
class BlacklistManager:
    """
    Backwards-compatible class wrapper around module-level blacklist functions.
    """
    def __init__(self, file_path: str):
        self.file_path = file_path
        
    @property
    def blacklist(self) -> List[str]:
        # For compatibility with legacy code calling manager.blacklist (e.g. flat list append)
        # Returns the global list of strings
        data = load_blacklist()
        return data.get("global", [])
        
    def save_blacklist(self):
        # Saved automatically by functions, but defined to prevent errors
        logger.info("BlacklistManager.save_blacklist called (compatibility proxy).")
        pass
