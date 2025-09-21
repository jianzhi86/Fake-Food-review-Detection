"""
Selenium scraping logic for Google Maps Reviews.
"""
import logging
import re
import time
from typing import Dict, Any, List, Union

import undetected_chromedriver as uc
from selenium.common.exceptions import (TimeoutException, StaleElementReferenceException, WebDriverException,
                                        NoSuchWindowException, NoSuchElementException)
from selenium.webdriver import Chrome
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm

from modules.models import RawReview

log = logging.getLogger("scraper")

PANE_SEL = 'div[role="main"] div.m6QErb.DxyBCb.kA9KIf.dS8AEf'
CARD_SEL = "div[data-review-id]"
COOKIE_BTN = 'button[aria-label*="Accept" i], button[jsname="hZCF7e"]'
SORT_BTN = 'button[aria-label*="Sort reviews" i]'
MENU_ITEMS = 'div[role="menu"] [role="menuitem"], li[role="menuitem"]'
COMPANY_NAME_SELECTORS = [
    'h1.fontHeadlineLarge', 'h1[aria-label]', 'div.fontTitleLarge.m6QErb'
]
REVIEW_WORDS = {"reviews", "review", "ratings", "rating"}

class GoogleReviewsScraper:
    """Main scraper class for Google Maps Reviews."""

    def __init__(self, config: Dict[str, Any] = None, **kwargs):
        self.config = config or {}
        self.config.update(kwargs)
        self.driver: Union[Chrome, None] = None
        self.company_name = "Unknown Company"

    def _start_driver(self) -> bool:
        """Initializes a new Chrome driver instance."""
        try:
            log.info("Setting up Chrome driver (headless=%s)...", self.config.get("headless", True))
            opts = uc.ChromeOptions()
            opts.add_argument("--window-size=1400,900")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            if self.config.get("headless", True):
                opts.add_argument("--headless=new")
            
            self.driver = uc.Chrome(options=opts)
            self.driver.set_page_load_timeout(45)
            log.info("Chrome driver started successfully.")
            return True
        except Exception as e:
            log.error("Failed to start Chrome driver: %s", e, exc_info=True)
            self._quit_driver()
            return False

    def _quit_driver(self):
        """Safely quits the driver."""
        if self.driver:
            try:
                self.driver.quit()
                log.info("Chrome driver has been quit.")
            except Exception:
                pass
            finally:
                self.driver = None

    def scrape(self, job_info: dict = None):
        """Main scraper method."""
        for attempt in range(3):
            log.info(f"Scraping attempt {attempt + 1}/3...")
            if not self._start_driver():
                time.sleep(5)
                continue

            try:
                if job_info: job_info['progress']['percentage'] = 15
                
                self.driver.get(self.config.get("url"))
                # --- STABILITY FIX ---
                time.sleep(2) # Wait for initial page javascript to load
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )

                self.company_name = self._get_company_name(self.driver, job_info)
                self.dismiss_cookies(self.driver)
                self.click_reviews_tab(self.driver, job_info)
                self.set_sort(self.driver, self.config.get("sort_by", "relevance"))
                
                time.sleep(1.5) # Wait for reviews to load after clicking tab

                pane = WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, PANE_SEL)))
                docs, _ = self._scroll_and_extract_reviews(pane, job_info)

                log.info("Scraping successful. Total unique reviews found: %d", len(docs))
                return {"company_name": self.company_name, "reviews": list(docs.values())}

            except Exception as e:
                log.error(f"Attempt {attempt + 1} failed: {e}", exc_info=True)
                self._quit_driver()
                if attempt < 2: time.sleep(5)
        
        log.error("All scraping attempts have failed.")
        # --- GRACEFUL FAILURE ---
        return {"company_name": self.company_name or "Unknown", "reviews": []}

    def _scroll_and_extract_reviews(self, pane: WebElement, job_info: dict) -> (dict, set):
        """Handles scrolling and sets progress from 60% to 90%."""
        docs, seen = {}, set()
        idle_scrolls = 0
        
        while idle_scrolls < 5:
            cards = pane.find_elements(By.CSS_SELECTOR, CARD_SEL)
            new_reviews_in_pass = 0
            for card in cards:
                try:
                    review_id = card.get_attribute("data-review-id")
                    if not review_id or review_id in seen:
                        continue
                    
                    raw_review = RawReview.from_card(card)
                    raw_review.company_name = self.company_name
                    docs[raw_review.id] = raw_review
                    seen.add(raw_review.id)
                    new_reviews_in_pass += 1

                    if job_info:
                        progress_for_reviews = min(len(docs) / 150.0, 1.0) * 30
                        job_info['progress']['percentage'] = 60 + int(progress_for_reviews)
                        job_info['progress']['message'] = f"Scraping reviews ({len(docs)} found)..."
                except StaleElementReferenceException:
                    continue
            
            if new_reviews_in_pass == 0:
                idle_scrolls += 1
            else:
                idle_scrolls = 0

            self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", pane)
            time.sleep(1.5)
        
        return docs, seen

    def dismiss_cookies(self, driver: Chrome):
        try:
            cookie_button = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, COOKIE_BTN)))
            cookie_button.click()
            log.info("Cookie dialog dismissed.")
        except TimeoutException:
            log.debug("No cookie consent dialog detected.")

    def is_reviews_tab(self, tab: WebElement) -> bool:
        try:
            text_content = (tab.text or "").lower()
            for word in REVIEW_WORDS:
                if word in text_content:
                    return True
        except StaleElementReferenceException:
            return False
        return False

    def click_reviews_tab(self, driver: Chrome, job_info: dict):
        if job_info: 
            job_info['progress']['percentage'] = 45
            job_info['progress']['message'] = "Looking for the reviews tab..."
        
        selectors = [f'button[aria-label*="{word}" i]' for word in REVIEW_WORDS]
        selectors.append('button[jsaction*="pane.rating.moreReviews"]')
        
        for selector in selectors:
            try:
                elements = WebDriverWait(driver, 5).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector)))
                for element in elements:
                    if self.is_reviews_tab(element):
                        element.click()
                        log.info(f"Successfully clicked reviews tab using selector: {selector}")
                        if job_info:
                            job_info['progress']['percentage'] = 60
                            job_info['progress']['message'] = "✅ Navigated to reviews section!"
                        time.sleep(1) 
                        return
            except TimeoutException:
                continue
        raise TimeoutException("Could not find or click the reviews tab.")

    def set_sort(self, driver: Chrome, method: str):
        if method == "relevance":
            log.info("Using default 'relevance' sort.")
            return
        try:
            sort_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SORT_BTN)))
            sort_button.click()
            time.sleep(1)
            
            menu_items = driver.find_elements(By.CSS_SELECTOR, MENU_ITEMS)
            for item in menu_items:
                if method.lower() in item.text.lower():
                    item.click()
                    log.info(f"Successfully set sort order to '{method}'")
                    return
        except Exception as e:
            log.warning(f"Could not set sort order to '{method}'. Using default. Error: {e}")

    def _get_company_name(self, driver: Chrome, job_info: dict) -> str:
        if job_info: 
            job_info['progress']['percentage'] = 25
            job_info['progress']['message'] = "Searching for company name..."
        try:
            for selector in COMPANY_NAME_SELECTORS:
                try:
                    name_element = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    name = name_element.text.strip()
                    if name:
                        if job_info: 
                            job_info['progress']['percentage'] = 40
                            job_info['progress']['message'] = f"✅ Found company: {name}"
                        time.sleep(1)
                        return name
                except TimeoutException:
                    continue
            
            title = driver.title
            if " - Google Maps" in title:
                return title.split(" - Google Maps")[0].strip()
            return "Unknown Company"
        except Exception as e:
            log.error(f"Error finding company name: {e}")
            return "Unknown Company"

