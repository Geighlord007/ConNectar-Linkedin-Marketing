#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LinkedIn 搜索管理器（v2 — CDP DOM 提取）

核心变化：
- 用 driver.execute_script(JS) 直接从 DOM 提取联系人，替代 HTML 解析
- 去掉所有滚动预热/补抓/NLP 模型依赖
- 内置页面健康检查和指数退避重试
"""

import os
import time
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus, urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from .extractors.cdp_dom_extractor import CDPDomExtractor
from .llm_refiner import LLMRefiner

logger = logging.getLogger(__name__)


class FinalSearchManager:
    """LinkedIn 搜索管理器 — CDP DOM 提取版"""

    def __init__(self):
        self.driver: Optional[webdriver.Chrome] = None
        self.extractor = CDPDomExtractor()
        self.llm_refiner = LLMRefiner()
        self._html_save_dir: Optional[str] = None

        # 页面加载等待时间（秒）
        self.page_load_wait = float(os.getenv("SCRAPER_PAGE_LOAD_WAIT", "6"))
        self.page_load_wait_first = float(os.getenv("SCRAPER_FIRST_PAGE_WAIT", "8"))

        # 翻页间随机延迟范围（秒）
        self.page_delay_min = float(os.getenv("SCRAPER_PAGE_DELAY_MIN", "2"))
        self.page_delay_max = float(os.getenv("SCRAPER_PAGE_DELAY_MAX", "4"))

        # 安全挑战重试
        self.max_health_retries = 3
        self.health_retry_base_delay = 5  # 指数退避基数（秒）

    # ------------------------------------------------------------------
    # 连接
    # ------------------------------------------------------------------
    def connect_to_chrome(self, debug_port: int = 9222) -> bool:
        try:
            opts = Options()
            opts.add_experimental_option("debuggerAddress", f"localhost:{debug_port}")
            self.driver = webdriver.Chrome(options=opts)
            logger.info(f"已连接到 Chrome (端口 {debug_port})")
            return True
        except Exception as e:
            logger.error(f"连接 Chrome 失败: {e}")
            return False

    # ------------------------------------------------------------------
    # 普通搜索
    # ------------------------------------------------------------------
    def search_people(
        self,
        keyword: str,
        max_results: int = 50,
        max_pages: int = 1,
        enrich_profiles: bool = True,
    ) -> List[Dict[str, Any]]:
        """搜索人员并提取联系人信息。

        Args:
            enrich_profiles: 是否打开缺少公司信息的人的个人主页补全数据
        """
        if not self.driver:
            logger.error("未连接到浏览器")
            return []

        try:
            self._init_html_save_dir(keyword)

            search_url = (
                f"https://www.linkedin.com/search/results/people/"
                f"?keywords={quote_plus(keyword)}"
                f"&origin=SWITCH_SEARCH_VERTICAL"
            )
            logger.warning(f"开始搜索: {keyword}, 最大页数: {max_pages}")

            self.driver.get(search_url)
            time.sleep(self.page_load_wait_first)

            all_contacts = self._extract_multi_page(
                keyword, max_results, max_pages
            )

            # 第一步：LLM 精炼 headline → title + company（快，无需打开页面）
            if all_contacts and self.llm_refiner.enabled:
                self.llm_refiner.refine_contacts(all_contacts)

            # 第二步：对 LLM 也无法提取公司的，访问个人主页补全
            if enrich_profiles and all_contacts:
                missing = sum(1 for c in all_contacts if not c.get("company"))
                if missing > 0:
                    logger.warning(
                        f"LLM 精炼后仍有 {missing}/{len(all_contacts)} 人缺少公司信息，"
                        f"开始访问个人主页补全..."
                    )
                    self.extractor.enrich_contacts_from_profiles(
                        self.driver, all_contacts,
                        delay_between=float(os.getenv(
                            "SCRAPER_PROFILE_DELAY", "3"
                        )),
                    )

            self._save_raw_results(keyword, all_contacts)
            return all_contacts

        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return []

    def search_people_multi_page(self, keyword, max_results=50, max_pages=1):
        return self.search_people(keyword, max_results, max_pages)

    # ------------------------------------------------------------------
    # Sales Navigator 搜索
    # ------------------------------------------------------------------
    def search_people_sales_navigator(
        self, max_results: int = 50, max_pages: int = 1
    ) -> List[Dict[str, Any]]:
        if not self.driver:
            logger.error("未连接到浏览器")
            return []

        try:
            current_url = self.driver.current_url
            if "linkedin.com/sales" not in current_url:
                logger.error("请先在 Sales Navigator 中设置好搜索条件")
                return []

            logger.info(f"Sales Navigator 爬取, 最大页数: {max_pages}")
            all_contacts = self._extract_multi_page(
                "sales_nav", max_results, max_pages
            )
            self._save_raw_results("sales_nav", all_contacts)
            return all_contacts

        except Exception as e:
            logger.error(f"Sales Navigator 搜索失败: {e}")
            return []

    # ------------------------------------------------------------------
    # 多页提取核心
    # ------------------------------------------------------------------
    def _extract_multi_page(
        self,
        keyword: str,
        max_results: int,
        max_pages: int,
    ) -> List[Dict[str, Any]]:
        all_contacts: List[Dict[str, Any]] = []

        for page_num in range(1, max_pages + 1):
            logger.warning(f"正在爬取第 {page_num}/{max_pages} 页...")

            # 页面健康检查（含指数退避重试）
            if not self._ensure_page_healthy():
                logger.error("页面健康检查失败，停止爬取")
                break

            # 等待搜索结果渲染
            wait_sec = self.page_load_wait_first if page_num == 1 else self.page_load_wait
            self._wait_for_results(wait_sec)

            # 保存 HTML 存档
            self._save_page_html(keyword, page_num)

            # CDP DOM 提取
            page_contacts = self.extractor.extract_contacts(self.driver)

            # 添加元数据
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            for c in page_contacts:
                c["search_keyword"] = keyword
                c["extracted_at"] = now

            if not page_contacts:
                logger.warning(f"第 {page_num} 页未提取到联系人，停止")
                break

            all_contacts.extend(page_contacts)
            logger.warning(
                f"第 {page_num} 页: {len(page_contacts)} 个联系人, "
                f"累计: {len(all_contacts)}"
            )

            if len(all_contacts) >= max_results:
                break

            # 翻页
            if page_num < max_pages:
                if not self._go_to_next_page():
                    logger.warning("无法翻到下一页，可能已到最后")
                    break
                # 随机延迟，模拟人类行为
                delay = self.page_delay_min + (
                    self.page_delay_max - self.page_delay_min
                ) * (hash(str(time.time())) % 100 / 100)
                time.sleep(delay)

        logger.warning(f"搜索完成，共 {len(all_contacts)} 个联系人")
        return all_contacts[:max_results]

    # ------------------------------------------------------------------
    # 页面健康检查 + 指数退避
    # ------------------------------------------------------------------
    def _ensure_page_healthy(self) -> bool:
        for attempt in range(self.max_health_retries):
            health = self.extractor.check_page_health(self.driver)

            if health.get("ok"):
                return True

            issue = health.get("issue", "unknown")
            logger.warning(f"页面异常: {issue} (第 {attempt+1} 次检测)")

            if issue == "login_required":
                logger.error("需要重新登录 LinkedIn，请在浏览器中登录后重试")
                input("登录完成后按回车继续...")
                self.driver.refresh()
                time.sleep(5)

            elif issue == "security_challenge":
                logger.error("触发安全验证，请在浏览器中手动完成验证")
                input("验证完成后按回车继续...")
                self.driver.refresh()
                time.sleep(5)

            elif issue == "rate_limited":
                wait = self.health_retry_base_delay * (2 ** attempt)
                logger.warning(f"请求频率受限，等待 {wait} 秒后重试...")
                time.sleep(wait)
                self.driver.refresh()
                time.sleep(3)

            else:
                time.sleep(self.health_retry_base_delay)
                self.driver.refresh()
                time.sleep(3)

        return False

    # ------------------------------------------------------------------
    # 等待搜索结果
    # ------------------------------------------------------------------
    def _wait_for_results(self, max_wait: float = 6):
        """等待搜索结果卡片出现"""
        try:
            WebDriverWait(self.driver, max_wait).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, '[data-view-name="people-search-result"]')
                )
            )
        except TimeoutException:
            # 回退：尝试旧版选择器
            try:
                WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR,
                         "li.reusable-search__result-container, "
                         "div.search-results-container")
                    )
                )
            except TimeoutException:
                logger.warning("搜索结果加载超时，将尝试提取当前页面内容")

    # ------------------------------------------------------------------
    # 翻页
    # ------------------------------------------------------------------
    def _go_to_next_page(self) -> bool:
        """点击下一页按钮"""
        try:
            next_btn = self.driver.find_element(
                By.CSS_SELECTOR,
                'button[aria-label="Next"], '
                'button.artdeco-pagination__button--next'
            )
            if not next_btn.is_enabled():
                return False
            next_btn.click()
            time.sleep(2)
            return True
        except Exception:
            # 回退：尝试从 URL 构造下一页
            try:
                current_url = self.driver.current_url
                parsed = urlparse(current_url)
                params = parse_qs(parsed.query)
                current_page = int(params.get("page", ["1"])[0])
                next_page = current_page + 1
                # 重建 URL
                new_params = {k: v[0] for k, v in params.items()}
                new_params["page"] = str(next_page)
                query = "&".join(f"{k}={v}" for k, v in new_params.items())
                next_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query}"
                self.driver.get(next_url)
                time.sleep(3)
                return True
            except Exception as e:
                logger.warning(f"翻页失败: {e}")
                return False

    def go_to_next_page(self) -> bool:
        """公开接口，兼容旧调用"""
        return self._go_to_next_page()

    def go_to_next_page_sales_nav(self) -> bool:
        """Sales Navigator 翻页"""
        try:
            next_btn = self.driver.find_element(
                By.CSS_SELECTOR,
                'button[aria-label="Next"], '
                'button.artdeco-pagination__button--next, '
                'button[class*="pagination__button--next"]'
            )
            if not next_btn.is_enabled():
                return False
            next_btn.click()
            time.sleep(3)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # HTML 存档（保留用于调试，可选）
    # ------------------------------------------------------------------
    def _init_html_save_dir(self, keyword: str):
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            base = os.path.join(os.getcwd(), "data", "html_data")
            self._html_save_dir = os.path.join(
                base, f"{keyword.replace(' ', '_')}_{ts}"
            )
            os.makedirs(self._html_save_dir, exist_ok=True)
        except Exception:
            self._html_save_dir = None

    def _save_page_html(self, keyword: str, page_num: int):
        if not self._html_save_dir:
            return
        try:
            path = os.path.join(
                self._html_save_dir, f"page{page_num:03d}.html"
            )
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
        except Exception:
            pass

    def save_page_html(self, keyword: str, page_num: int):
        """公开接口，兼容旧调用"""
        self._save_page_html(keyword, page_num)

    # ------------------------------------------------------------------
    # 保存原始结果
    # ------------------------------------------------------------------
    def _save_raw_results(self, keyword: str, contacts: List[Dict]):
        if not contacts:
            return
        try:
            base = os.path.join(os.getcwd(), "data", "raw", "_sessions")
            os.makedirs(base, exist_ok=True)
            safe_kw = keyword.replace(" ", "_")
            path = os.path.join(base, f"search_results_{safe_kw}_final.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(contacts, f, ensure_ascii=False, indent=2)
            logger.warning(f"结果已保存: {path}")
        except Exception as e:
            logger.warning(f"保存结果失败: {e}")

    # ------------------------------------------------------------------
    # 兼容旧接口（供 main_controller 等调用）
    # ------------------------------------------------------------------
    def set_extraction_mode(self, mode: str):
        """保留接口但不再区分模式，统一使用 CDP DOM 提取"""
        pass

    def extract_contacts(self, keyword: str, max_results: int, suppress_log: bool = False):
        """兼容旧调用：从当前页面提取联系人"""
        contacts = self.extractor.extract_contacts(self.driver)
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        for c in contacts:
            c["search_keyword"] = keyword
            c["extracted_at"] = now
        return contacts[:max_results]
