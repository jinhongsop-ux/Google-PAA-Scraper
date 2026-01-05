import time
import random
import os
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException
from selenium_stealth import stealth
from webdriver_manager.chrome import ChromeDriverManager
from collections import deque

class PAAScraper:
    def __init__(self, headless=False, max_depth=3):
        self.headless = headless
        self.max_depth = max_depth
        self.results_dir = "results"
        self.data_scraped = []
        self.seen_questions = set()
        self.driver = self.setup_driver()
        
        # Create results directory if it doesn't exist
        if not os.path.exists(self.results_dir):
            os.makedirs(self.results_dir)
            print(f"Created directory: {self.results_dir}/")

    def setup_driver(self):
        """Configures the Chrome driver with stealth settings."""
        options = Options()
        if self.headless:
            options.add_argument("--headless")
        
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Experimental options to remove automation flags
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        # Apply selenium-stealth
        stealth(driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
        return driver

    def random_sleep(self, min_time=2.0, max_time=5.0):
        """Sleep for a random interval to mimic human behavior."""
        time.sleep(random.uniform(min_time, max_time))

    def scroll_into_view(self, element):
        """Scrolls the element into view."""
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            time.sleep(random.uniform(0.5, 1.5))
        except Exception:
            pass
    
    def sanitize_filename(self, keyword):
        """Convert keyword to valid filename by removing illegal characters."""
        # Remove or replace illegal filename characters
        illegal_chars = '<>:"/\\|?*'
        filename = keyword
        for char in illegal_chars:
            filename = filename.replace(char, '_')
        # Replace spaces with underscores
        filename = filename.replace(' ', '_')
        # Remove leading/trailing underscores and dots
        filename = filename.strip('_.')
        # Limit length to avoid filesystem issues
        if len(filename) > 200:
            filename = filename[:200]
        return filename
    
    def get_output_filename(self, keyword):
        """Get the output Excel filename for a given keyword."""
        safe_name = self.sanitize_filename(keyword)
        return os.path.join(self.results_dir, f"{safe_name}.xlsx")
    
    def load_historical_data(self, keyword):
        """
        Load historical data for a keyword if it exists.
        Returns the count of loaded questions.
        """
        filename = self.get_output_filename(keyword)
        if os.path.exists(filename):
            try:
                df = pd.read_excel(filename)
                if 'Question/Term' in df.columns:
                    # Load all existing questions into seen_questions set
                    existing_questions = df['Question/Term'].dropna().unique().tolist()
                    self.seen_questions.update(existing_questions)
                    return len(existing_questions)
            except Exception as e:
                print(f"⚠️  Error loading historical data: {e}")
        return 0

    def get_paa_questions_elements(self):
        """Locates all PAA question elements currently visible on the page."""
        # Common PAA classes / attributes. 
        # Often div with jsname='Cpkphb' is the question header or div[aria-expanded]
        try:
            # This selector targets the question text container which is usually clickeable
            # We look for elements that look like PAA headers
            elements = self.driver.find_elements(By.CSS_SELECTOR, "div.related-question-pair")
            return elements
        except Exception as e:
            print(f"Error finding PAA elements: {e}")
            return []

    def extract_text(self, element, selector):
        try:
            return element.find_element(By.CSS_SELECTOR, selector).text
        except:
            return ""

    def process_keyword(self, keyword):
        print(f"\n{'='*70}")
        print(f"🔍 Processing Keyword: {keyword}")
        print(f"{'='*70}")
        
        # Reset seen_questions and load historical data
        self.seen_questions = set()
        historical_count = self.load_historical_data(keyword)
        
        if historical_count > 0:
            print(f"📚 已加载关键词 [{keyword}] 的历史数据 {historical_count} 条，将自动跳过重复...")
        else:
            print(f"📝 关键词 [{keyword}] 无历史数据，开始全新抓取...")
        
        # Store current keyword for saving
        self.current_keyword = keyword
        self.driver.get("https://www.google.com")
        self.random_sleep(1, 2)

        # Search
        try:
            search_box = self.driver.find_element(By.NAME, "q")
            search_box.clear()
            search_box.send_keys(keyword)
            self.random_sleep(0.5, 1)
            search_box.submit()
        except Exception as e:
            print(f"Error during search: {e}")
            return

        self.random_sleep(2, 4)

        # Basic Check for CAPTCHA
        if "captcha" in self.driver.page_source.lower():
            input("CAPTCHA detected! Please solve it in the browser and press Enter here to continue...")

        # Find initial PAA section
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.related-question-pair"))
            )
        except:
            print(f"No PAA section found for '{keyword}'.")
            return

        # Recursive Expansion
        # We perform a sort of interactive BFS/DFS by clicking through available questions
        # Since clicking generates new ones, we need to refresh our list of elements reasonably
        
        iteration_count = 0
        
        while iteration_count < self.max_depth:
            print(f"Expansion Level {iteration_count + 1}...")
            
            # Find all current PAA elements
            paa_pairs = self.driver.find_elements(By.CSS_SELECTOR, "div.related-question-pair")
            
            clicks_made_this_round = 0
            
            for pair in paa_pairs:
                try:
                    # Extract Question Text
                    question_div = pair.find_element(By.CSS_SELECTOR, "div[role='button']")
                    question_text = question_div.text
                    
                    if not question_text or question_text in self.seen_questions:
                        continue
                    
                    # Mark as seen so we don't re-process duplicate text (though Google might show same Q twice)
                    self.seen_questions.add(question_text)

                    # Scroll and Click to expand
                    self.scroll_into_view(question_div)
                    
                    # Check if already expanded
                    is_expanded = question_div.get_attribute("aria-expanded")
                    if is_expanded == "false":
                        question_div.click()
                        clicks_made_this_round += 1
                        self.random_sleep(2, 4) # Critical wait for content load and new questions generation
                    
                    # Extract Data from the expanded panel
                    # The answer usually sits in a container sibling or child. 
                    # Often inside the pair, there is a container for the answer that becomes visible.
                    
                    # Try to find snippet and link
                    snippet = ""
                    source_link = ""
                    
                    try:
                        # Wait briefly for the answer to be visible
                        # Answer is usually in 'div.g' or specific PAA answer container class
                        # We use a broad search within the pair element
                        snippet_el = pair.find_element(By.CSS_SELECTOR, ".wDYxhc") # Common class for PAA info part
                        snippet = snippet_el.text
                        
                        link_el = snippet_el.find_element(By.CSS_SELECTOR, "a")
                        source_link = link_el.get_attribute("href")
                    except Exception:
                        # Fallback parsing attempts if classes differ
                        try:
                            # Try generic block search
                            blocks = pair.find_elements(By.CSS_SELECTOR, "div")
                            # Heuristic: Find the block with substantial text that isn't the question
                            for b in blocks:
                                if len(b.text) > 20 and b.text != question_text:
                                    snippet = b.text
                                    break
                        except:
                            pass

                    # Create data record
                    data_record = {
                        "Original Keyword": keyword,
                        "Type": "PAA",
                        "Question/Term": question_text,
                        "Snippet": snippet,
                        "Source Link": source_link,
                        "Discovery Level": iteration_count + 1
                    }
                    
                    # Add to in-memory list
                    self.data_scraped.append(data_record)
                    
                    # 🔥 CHECKPOINT SAVE: Save immediately after each question
                    self.save_to_excel(new_data_only=data_record)
                    
                except StaleElementReferenceException:
                    print("⚠️  Stale Element encountered. Skipping this element and continuing...")
                    continue
                except Exception as e:
                    # Log other errors but continue processing
                    print(f"⚠️  Error processing element: {str(e)[:100]}. Continuing...")
                    continue
            
            if clicks_made_this_round == 0:
                print("No new unique questions clicked this round. Stopping expansion.")
                break
                
            iteration_count += 1
            self.random_sleep(1, 3)

        # Extraction of 'People also search for'
        print("Extracting 'People also search for'...")
        try:
            # Common footer area related searches
            # Classes like .y6Uy8d or div[data-attrid='related_search']
            # We can also look for the heading "People also search for"
            
            # General approach: Look for the block at the bottom
            related_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.s75CSd, div.k8XOCe, a.k8XOCe") # Common classes for related search pills/links
            if not related_elements:
                 related_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.AJLUJb") # Bottom related searches container

            count = 0 
            for el in related_elements:
                try:
                    text = el.text
                    href = el.get_attribute("href")
                    if not href:
                        # Sometimes the link is on parent or processing differs
                        try:
                            href = el.find_element(By.TAG_NAME, "a").get_attribute("href")
                        except:
                            pass
                    
                    if text and text not in self.seen_questions:
                         data_record = {
                            "Original Keyword": keyword,
                            "Type": "Related Search",
                            "Question/Term": text,
                            "Snippet": "",
                            "Source Link": href if href else "",
                            "Discovery Level": 0
                        }
                         self.data_scraped.append(data_record)
                         
                         # 🔥 CHECKPOINT SAVE: Save related search term immediately
                         self.save_to_excel(new_data_only=data_record)
                         count += 1
                except:
                    continue
            print(f"Captured {count} related search terms.")

        except Exception as e:
            print(f"Error extracting related searches: {e}")

    def save_to_excel(self, new_data_only=None):
        """
        Save data to Excel with incremental append and deduplication.
        Uses per-keyword filenames based on self.current_keyword.
        
        Args:
            new_data_only: If provided, save only this single record (for checkpoint saving)
        """
        # Get filename for current keyword
        if not hasattr(self, 'current_keyword'):
            print("⚠️  No current keyword set. Cannot save.")
            return
        
        filename = self.get_output_filename(self.current_keyword)
        
        # Determine what data to save
        if new_data_only:
            new_df = pd.DataFrame([new_data_only])
        elif self.data_scraped:
            new_df = pd.DataFrame(self.data_scraped)
        else:
            print("No data to save.")
            return

        try:
            # Check if file exists and read existing data
            if os.path.exists(filename):
                existing_df = pd.read_excel(filename)
                # Combine existing and new data
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            else:
                combined_df = new_df
            
            # Remove duplicates based on Question/Term (keep first occurrence)
            combined_df = combined_df.drop_duplicates(subset=["Question/Term"], keep="first")
            
            # Save to Excel
            combined_df.to_excel(filename, index=False)
            
            if new_data_only:
                # Checkpoint save - show progress
                total_count = len(combined_df)
                print(f"✓ 已保存：{new_data_only['Question/Term'][:60]}... | 当前总数：{total_count}条")
            else:
                print(f"Data saved to {filename} (Total: {len(combined_df)} records)")
                
        except Exception as e:
            print(f"Error saving to Excel: {e}. Attempting backup save...")
            try:
                backup_filename = f"paa_results_backup_{int(time.time())}.xlsx"
                new_df.to_excel(backup_filename, index=False)
                print(f"Backup saved to {backup_filename}")
            except Exception as backup_error:
                print(f"Backup save also failed: {backup_error}")

    def quit(self):
        self.driver.quit()

if __name__ == "__main__":
    import json
    
    config_path = "config.json"
    if not os.path.exists(config_path):
        print(f"Config file {config_path} not found. Creating default...")
        default_config = {
            "keywords": ["python automation"],
            "max_depth": 3,
            "headless": False,
            "output_file": "paa_results.xlsx"
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4)
        print("Please edit config.json and run again.")
        exit()

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    keywords = config.get("keywords", ["python automation"])
    max_depth = config.get("max_depth", 3)
    headless = config.get("headless", False)

    print(f"Loaded {len(keywords)} keywords from config.")
    print(f"Max Depth: {max_depth}, Headless: {headless}")

    scraper = PAAScraper(headless=headless, max_depth=max_depth)
    
    try:
        for kw in keywords:
            scraper.process_keyword(kw)
    finally:
        # Final message
        print("\n" + "="*70)
        print("🎉 All keywords processed! Results saved in 'results/' folder.")
        print("="*70)
        scraper.quit()
