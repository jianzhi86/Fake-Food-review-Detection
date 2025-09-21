"""
Utility functions for Google Maps Reviews Scraper.
"""
import datetime
import logging
import re
import time
from datetime import timezone
from functools import lru_cache
from typing import List

from selenium.common.exceptions import (NoSuchElementException,
                                        StaleElementReferenceException,
                                        TimeoutException)
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Logger
log = logging.getLogger("scraper")

# Constants for language detection
HEB_CHARS = re.compile(r"[\u0590-\u05FF]")
THAI_CHARS = re.compile(r"[\u0E00-\u0E7F]")


@lru_cache(maxsize=1024)
def detect_lang(txt: str) -> str:
    """Detect language based on character sets"""
    if HEB_CHARS.search(txt):  return "he"
    if THAI_CHARS.search(txt): return "th"
    return "en"


@lru_cache(maxsize=128)
def safe_int(s: str | None) -> int:
    """Safely convert string to integer, returning 0 if not possible"""
    m = re.search(r"\d+", s or "")
    return int(m.group()) if m else 0


def try_find(el: WebElement, css: str, *, all=False) -> List[WebElement]:
    """Safely find elements by CSS selector without raising exceptions"""
    try:
        if all:
            return el.find_elements(By.CSS_SELECTOR, css)
        obj = el.find_element(By.CSS_SELECTOR, css)
        return [obj] if obj else []
    except (NoSuchElementException, StaleElementReferenceException):
        return []


def first_text(el: WebElement, css: str) -> str:
    """Get text from the first matching element that has non-empty text"""
    for e in try_find(el, css, all=True):
        try:
            if (t := e.text.strip()):
                return t
        except StaleElementReferenceException:
            continue
    return ""

def first_attr(el: WebElement, css: str, attr: str) -> str:
    """Get attribute value from the first matching element that has a non-empty value"""
    for e in try_find(el, css, all=True):
        try:
            if (v := (e.get_attribute(attr) or "").strip()):
                return v
        except StaleElementReferenceException:
            continue
    return ""


def parse_date_to_iso(date_str: str) -> str:
    """
    Parse date strings like "2 weeks ago", "January 2023", etc. into ISO format.
    Returns a best-effort ISO string, or empty string if parsing fails.
    """
    if not date_str:
        return ""

    try:
        now = datetime.datetime.now(timezone.utc)
        date_str = date_str.lower()
        dt = now # Default to now

        if "ago" in date_str:
            num = int(re.search(r'\d+', date_str).group()) if re.search(r'\d+', date_str) else 1
            if "minute" in date_str: dt = now - datetime.timedelta(minutes=num)
            elif "hour" in date_str: dt = now - datetime.timedelta(hours=num)
            elif "day" in date_str: dt = now - datetime.timedelta(days=num)
            elif "week" in date_str: dt = now - datetime.timedelta(weeks=num)
            elif "month" in date_str: dt = now - datetime.timedelta(days=30 * num) # Approximation
            elif "year" in date_str: dt = now - datetime.timedelta(days=365 * num) # Approximation
        
        return dt.replace(microsecond=0).isoformat()
    except Exception:
        return ""


def click_if(driver: Chrome, css: str, delay: float = .25, timeout: float = 5.0) -> bool:
    """Click element if it exists and is clickable, with timeout and better error handling."""
    try:
        elements = driver.find_elements(By.CSS_SELECTOR, css)
        if not elements:
            return False

        for element in elements:
            try:
                if element.is_displayed() and element.is_enabled():
                    element.click()
                    time.sleep(delay)
                    return True
            except Exception:
                continue

        try:
            WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, css))
            ).click()
            time.sleep(delay)
            return True
        except TimeoutException:
            return False

    except Exception as e:
        log.debug(f"Error in click_if: {str(e)}")
        return False


def get_current_iso_date() -> str:
    """Return current UTC time in ISO format."""
    return datetime.datetime.now(timezone.utc).isoformat()