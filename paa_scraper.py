import time
import random
import os
import sys
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    WebDriverException
)
from selenium_stealth import stealth
from webdriver_manager.chrome import ChromeDriverManager
from collections import deque

# 🔥 Windows 控制台中文编码修复 (防止 exe 运行时乱码)
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python < 3.7 兼容
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

class PAAScraper:
    def __init__(self, headless=False, max_depth=3):
        self.headless = headless
        self.max_depth = max_depth
        self.results_dir = "results"
        self.data_scraped = []
        self.seen_questions = set()
        self.driver = None
        self.retry_count = 0
        self.max_retries = 3
        
        # Create results directory if it doesn't exist
        if not os.path.exists(self.results_dir):
            os.makedirs(self.results_dir)
            print(f"Created directory: {self.results_dir}/")
        
        # 初始化浏览器驱动
        self.driver = self._init_driver_with_retry()

    def setup_driver(self):
        """Configures the Chrome driver with stealth settings."""
        options = Options()
        if self.headless:
            options.add_argument("--headless")
        
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-gpu")  # 防止GPU相关崩溃
        options.add_argument("--no-sandbox")  # 增加兼容性
        options.add_argument("--disable-dev-shm-usage")  # 防止内存问题
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Experimental options to remove automation flags
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # 设置页面加载超时
        driver.set_page_load_timeout(60)
        driver.implicitly_wait(10)

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
    
    def _init_driver_with_retry(self):
        """
        初始化浏览器驱动，带重试机制。
        处理ChromeDriver下载失败、Chrome未安装等问题。
        """
        last_error = None
        for attempt in range(self.max_retries):
            try:
                print(f"🚀 正在初始化浏览器... (尝试 {attempt + 1}/{self.max_retries})")
                driver = self.setup_driver()
                print("✅ 浏览器初始化成功！")
                return driver
            except WebDriverException as e:
                last_error = e
                print(f"⚠️  浏览器初始化失败 (尝试 {attempt + 1}): {str(e)[:100]}")
                if attempt < self.max_retries - 1:
                    print("   等待5秒后重试...")
                    time.sleep(5)
            except Exception as e:
                last_error = e
                print(f"⚠️  未知错误: {str(e)[:100]}")
                break
        
        # 所有重试都失败
        print("\n" + "="*70)
        print("❌ 浏览器初始化失败！")
        print("="*70)
        print("💡 可能的原因:")
        print("   1. Chrome浏览器未安装或版本过旧")
        print("   2. ChromeDriver下载失败（检查网络/代理）")
        print("   3. 杀毒软件阻止了ChromeDriver")
        print(f"\n错误详情: {last_error}")
        raise RuntimeError("无法初始化浏览器驱动")

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
    
    def _scroll_to_find_paa(self, max_scrolls=5):
        """
        滚动页面以触发懒加载，寻找PAA元素。
        Google搜索结果是懒加载的，PAA可能在页面中下部。
        
        Args:
            max_scrolls: 最大滚动次数
        Returns:
            bool: 是否找到PAA元素
        """
        # 首先检查PAA是否已经存在
        paa_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.related-question-pair")
        if paa_elements:
            return True
        
        # 分段滚动页面，触发懒加载
        scroll_pause_time = 1.5
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        
        for i in range(max_scrolls):
            # 滚动一屏的高度（约500像素）
            scroll_amount = 500 * (i + 1)
            self.driver.execute_script(f"window.scrollTo(0, {scroll_amount});")
            time.sleep(scroll_pause_time)
            
            # 每次滚动后检查PAA是否出现
            paa_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.related-question-pair")
            if paa_elements:
                print(f"   ✓ 在第 {i + 1} 次滚动后找到 PAA")
                # 滚动回PAA位置
                self.scroll_into_view(paa_elements[0])
                return True
            
            # 检查是否已经到底部
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if scroll_amount >= new_height:
                break
        
        # 滚动回顶部再做最后一次检查
        self.driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        paa_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.related-question-pair")
        return len(paa_elements) > 0
    
    def _safe_click(self, element, max_attempts=3):
        """
        安全点击元素，处理各种点击失败的情况。
        
        Args:
            element: 要点击的元素
            max_attempts: 最大尝试次数
        Returns:
            bool: 是否成功点击
        """
        for attempt in range(max_attempts):
            try:
                # 先滚动到元素位置
                self.scroll_into_view(element)
                time.sleep(0.3)
                
                # 尝试普通点击
                element.click()
                return True
                
            except ElementClickInterceptedException:
                # 点击被其他元素遮挡，尝试用JavaScript点击
                try:
                    self.driver.execute_script("arguments[0].click();", element)
                    return True
                except:
                    pass
                    
            except StaleElementReferenceException:
                # 元素已过期，无法重试
                return False
                
            except Exception as e:
                if attempt < max_attempts - 1:
                    time.sleep(0.5)
                    continue
                else:
                    return False
        
        return False
    
    def _check_for_captcha(self):
        """
        检查页面是否出现CAPTCHA或人机验证。
        支持多种Google验证类型。
        
        Returns:
            bool: 是否检测到验证
        """
        page_source = self.driver.page_source.lower()
        current_url = self.driver.current_url.lower()
        
        captcha_indicators = [
            "captcha",
            "recaptcha",
            "unusual traffic",
            "automated queries",
            "sorry/index",
            "ipv4.google.com/sorry"
        ]
        
        for indicator in captcha_indicators:
            if indicator in page_source or indicator in current_url:
                return True
        
        return False

    def process_keyword(self, keyword):
        """
        处理单个关键词，支持 PAA 触发失败后的重试机制。
        """
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
        
        # Store current keyword for saving (始终使用原始关键词作为文件名)
        self.current_keyword = keyword
        
        # 🔥 PAA 触发重试前缀列表
        retry_prefixes = [
            "",                    # 原始关键词
            "What is ",            # 定义类
            "Best ",               # 测评类 / 电商类
            "How to use ",         # 教程类
            "How to choose ",      # 选购类
            " guide",              # 指南类 (后缀)
        ]
        
        # 尝试不同的关键词变体触发 PAA
        for i, prefix in enumerate(retry_prefixes):
            # 构造搜索词
            if prefix.endswith(" "):
                search_term = prefix + keyword
            elif prefix.startswith(" "):
                search_term = keyword + prefix  # 后缀模式
            else:
                search_term = keyword
            
            is_retry = (i > 0)
            
            if is_retry:
                print(f"\n{'~'*50}")
                print(f"🔄 原始词未触发 PAA，尝试变体 #{i}: '{search_term}'")
                print(f"{'~'*50}")
            
            # 执行搜索和抓取
            success = self._search_and_scrape_paa(
                search_term=search_term,
                original_keyword=keyword,
                is_retry=is_retry
            )
            
            if success:
                if is_retry:
                    print(f"✅ 变体关键词 '{search_term}' 成功触发 PAA！")
                return  # 成功，结束处理
        
        # 所有尝试都失败
        print(f"\n{'!'*50}")
        print(f"❌ 关键词 '{keyword}' 彻底未找到 PAA")
        print(f"{'!'*50}")
        print("💡 建议：")
        print("   1. 该关键词可能确实没有 PAA 结果")
        print("   2. 尝试使用更具体或更通用的关键词")
        print("   3. 检查网络连接和代理设置")
    
    def _search_and_scrape_paa(self, search_term, original_keyword, is_retry=False):
        """
        执行搜索并抓取 PAA 的核心逻辑。
        
        Args:
            search_term: 实际搜索的关键词（可能带前缀）
            original_keyword: 原始关键词（用于数据记录）
            is_retry: 是否为重试模式
        
        Returns:
            bool: 是否成功抓取到 PAA
        """
        # 导航到 Google
        self.driver.get("https://www.google.com")
        self.random_sleep(1, 2)

        # Search
        try:
            search_box = self.driver.find_element(By.NAME, "q")
            search_box.clear()
            search_box.send_keys(search_term)
            self.random_sleep(0.5, 1)
            search_box.submit()
        except Exception as e:
            print(f"Error during search: {e}")
            return False

        self.random_sleep(2, 4)

        # Basic Check for CAPTCHA (支持多种验证类型)
        if self._check_for_captcha():
            print("\n" + "!"*50)
            print("🔒 检测到人机验证！")
            print("!"*50)
            input("请在浏览器中完成验证，然后按回车继续...")
            print("⏳ 等待页面刷新中，请稍候...")
            time.sleep(5)
            self.random_sleep(2, 3)
            
            if self._check_for_captcha():
                print("⚠️  验证似乎未完成，请重新验证后再试")
                return False

        # 🔥 滚动页面以触发懒加载，确保PAA元素被加载
        print("📜 滚动页面以加载全部内容...")
        paa_found = self._scroll_to_find_paa()
        
        if not paa_found:
            if not is_retry:
                print(f"⚠️ 原始词 '{search_term}' 未找到 PAA，准备尝试变体...")
            return False
        
        print("✅ PAA section found! Starting extraction...")
        
        # 记录数据来源标记
        source_tag = f"[重试: {search_term}]" if is_retry else ""
        
        # Recursive Expansion
        iteration_count = 0
        total_extracted = 0
        
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
                    
                    self.seen_questions.add(question_text)

                    # Scroll and Click to expand
                    self.scroll_into_view(question_div)
                    
                    # Check if already expanded
                    is_expanded = question_div.get_attribute("aria-expanded")
                    if is_expanded == "false":
                        if self._safe_click(question_div):
                            clicks_made_this_round += 1
                            self.random_sleep(2, 4)
                        else:
                            print(f"   ⚠️  点击失败，跳过: {question_text[:30]}...")
                            continue
                    
                    # Try to find snippet and link
                    snippet = ""
                    source_link = ""
                    
                    try:
                        snippet_el = pair.find_element(By.CSS_SELECTOR, ".wDYxhc")
                        snippet = snippet_el.text
                        link_el = snippet_el.find_element(By.CSS_SELECTOR, "a")
                        source_link = link_el.get_attribute("href")
                    except Exception:
                        try:
                            blocks = pair.find_elements(By.CSS_SELECTOR, "div")
                            for b in blocks:
                                if len(b.text) > 20 and b.text != question_text:
                                    snippet = b.text
                                    break
                        except:
                            pass

                    # Create data record - 添加来源标记
                    data_record = {
                        "Original Keyword": original_keyword,
                        "Search Term": search_term if is_retry else original_keyword,
                        "Type": "PAA",
                        "Question/Term": question_text,
                        "Snippet": snippet,
                        "Source Link": source_link,
                        "Discovery Level": iteration_count + 1,
                        "Data Source": "Retry" if is_retry else "Original"
                    }
                    
                    self.data_scraped.append(data_record)
                    self.save_to_excel(new_data_only=data_record)
                    total_extracted += 1
                    
                except StaleElementReferenceException:
                    print("⚠️  Stale Element encountered. Skipping...")
                    continue
                except Exception as e:
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
            related_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.s75CSd, div.k8XOCe, a.k8XOCe")
            if not related_elements:
                 related_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.AJLUJb")

            count = 0 
            for el in related_elements:
                try:
                    text = el.text
                    href = el.get_attribute("href")
                    if not href:
                        try:
                            href = el.find_element(By.TAG_NAME, "a").get_attribute("href")
                        except:
                            pass
                    
                    if text and text not in self.seen_questions:
                         data_record = {
                            "Original Keyword": original_keyword,
                            "Search Term": search_term if is_retry else original_keyword,
                            "Type": "Related Search",
                            "Question/Term": text,
                            "Snippet": "",
                            "Source Link": href if href else "",
                            "Discovery Level": 0,
                            "Data Source": "Retry" if is_retry else "Original"
                        }
                         self.data_scraped.append(data_record)
                         self.save_to_excel(new_data_only=data_record)
                         count += 1
                         total_extracted += 1
                except:
                    continue
            print(f"Captured {count} related search terms.")

        except Exception as e:
            print(f"Error extracting related searches: {e}")
        
        # 返回是否成功抓取到数据
        return total_extracted > 0

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
    
    print("="*70)
    print("🔧 PAA Scraper - Google People Also Ask 抓取工具")
    print("="*70)
    
    config_path = "config.json"
    if not os.path.exists(config_path):
        print(f"⚠️  配置文件 {config_path} 未找到，正在创建默认配置...")
        default_config = {
            "keywords": ["python automation"],
            "max_depth": 3,
            "headless": False,
            "output_file": "paa_results.xlsx"
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        print("✅ 已创建默认配置文件，请编辑 config.json 后重新运行。")
        input("按回车键退出...")
        sys.exit()

    # 读取配置文件，带异常处理
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ 配置文件格式错误！")
        print(f"   错误位置: 第 {e.lineno} 行，第 {e.colno} 列")
        print(f"   错误详情: {e.msg}")
        print("\n💡 请检查 config.json 的 JSON 格式是否正确")
        input("按回车键退出...")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 读取配置文件失败: {e}")
        input("按回车键退出...")
        sys.exit(1)

    keywords = config.get("keywords", ["python automation"])
    max_depth = config.get("max_depth", 3)
    headless = config.get("headless", False)

    print(f"Loaded {len(keywords)} keywords from config.")
    print(f"Max Depth: {max_depth}, Headless: {headless}")

    scraper = PAAScraper(headless=headless, max_depth=max_depth)
    
    try:
        for kw in keywords:
            scraper.process_keyword(kw)
        
        # 成功完成
        print("\n" + "="*70)
        print("🎉 All keywords processed! Results saved in 'results/' folder.")
        print("="*70)
        
    except Exception as e:
        # 全局异常捕获，防止闪退
        print("\n" + "="*70)
        print("❌ 程序运行出错！")
        print("="*70)
        print(f"错误类型: {type(e).__name__}")
        print(f"错误详情: {str(e)}")
        print("\n💡 常见解决方案:")
        print("   1. 如果是网络问题，请检查VPN/代理是否正常")
        print("   2. 如果是元素找不到，可能Google页面结构有变化")
        print("   3. 如果频繁出现CAPTCHA，请降低抓取频率")
        import traceback
        print("\n--- 完整错误堆栈 ---")
        traceback.print_exc()
        
    finally:
        try:
            scraper.quit()
        except:
            pass
        
        # 🔥 防闪退：程序结束前暂停
        print("\n" + "-"*70)
        input("📌 程序已结束。按回车键关闭窗口...")
