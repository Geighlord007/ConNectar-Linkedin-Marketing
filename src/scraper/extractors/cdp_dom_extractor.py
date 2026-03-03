#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CDP DOM 提取器 — 通过在页面中执行 JavaScript 直接从 DOM 提取联系人数据。

替代旧的 HTML 解析方案（Hybrid V44 / Expert V4），优势：
- 零 HTML 解析，零 NLP 模型依赖
- 利用 LinkedIn 的语义 DOM 属性（data-view-name, aria-label）
- ~50 行 JS 完成提取，数据天然干净
"""

import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 页面内执行的 JavaScript 提取逻辑
# ---------------------------------------------------------------------------
EXTRACT_CONTACTS_JS = r"""
return (() => {
    const NOISE_TEXTS = new Set([
        'Connect', 'Follow', 'Message', 'Pending', 'Send InMail',
        'View profile', 'More', 'Dismiss',
    ]);

    const NOISE_PATTERNS = [
        /^\d+K?\+?\s*followers?$/i,
        /mutual connections?$/i,
        /^Current:|^Past:|^Education:|^About:|^Skills:/,
        /people also viewed/i,
    ];

    function isNoise(text) {
        if (NOISE_TEXTS.has(text)) return true;
        return NOISE_PATTERNS.some(p => p.test(text));
    }

    /* ---------- name 清洗 ---------- */
    const NAME_SUFFIXES_TO_STRIP = [
        /\s+is hiring$/i,
        /\s+is an?\s+.{0,30}$/i,       // "is a LinkedIn Top Voice"
        /\s*\(.*Open to Work.*\)/i,
        /\s*-\s*Open to Work$/i,
        /,?\s*(?:He\/Him|She\/Her|They\/Them)$/i,
    ];

    function cleanName(raw) {
        if (!raw) return '';
        let name = raw.trim();
        for (const pat of NAME_SUFFIXES_TO_STRIP) {
            name = name.replace(pat, '');
        }
        return name.trim();
    }

    /* ---------- headline → title + company ---------- */
    function splitHeadline(headline) {
        if (!headline) return { title: '', company: '' };

        // " at " 是 LinkedIn 标准格式
        let idx = headline.lastIndexOf(' at ');
        if (idx > 0) {
            return {
                title: headline.slice(0, idx).trim(),
                company: headline.slice(idx + 4).trim(),
            };
        }
        // " @ " 偶尔出现
        idx = headline.lastIndexOf(' @ ');
        if (idx > 0) {
            return {
                title: headline.slice(0, idx).trim(),
                company: headline.slice(idx + 3).trim(),
            };
        }
        // 法语格式 " chez " / " la " (出现在法/罗语 headline)
        for (const sep of [' chez ', ' che ']) {
            idx = headline.lastIndexOf(sep);
            if (idx > 0) {
                return {
                    title: headline.slice(0, idx).trim(),
                    company: headline.slice(idx + sep.length).trim(),
                };
            }
        }
        // 没有明确分隔符，整段都是 headline
        return { title: headline, company: '' };
    }

    /* ---------- 主提取逻辑 ---------- */
    const cards = document.querySelectorAll(
        '[data-view-name="people-search-result"]'
    );

    const results = [];
    cards.forEach(card => {
        try {
            // 1. LinkedIn URL
            const linkEl = card.querySelector('a[href*="/in/"]');
            const linkedin_url = linkEl
                ? linkEl.href.split('?')[0].replace(/\/+$/, '')
                : '';

            // 2. 姓名 (aria-label 是最干净的来源)
            const figure = card.querySelector('figure[aria-label]');
            const rawName = figure ? figure.getAttribute('aria-label') : '';
            const name = cleanName(rawName);

            // 3. 叶子文本节点 —— 按 DOM 顺序收集
            //    结构: [headline, location, actionButton, extra...]
            const leafTexts = [];
            card.querySelectorAll('div, span').forEach(el => {
                // 只取叶子（不含子 div/a/button）
                if (el.querySelector('div') || el.querySelector('a') || el.querySelector('button')) return;
                const t = el.textContent.trim();
                if (!t || t.length < 2 || t.length > 300) return;
                if (t === name) return;
                // 跳过连接度标记 "• 1st" "• 2nd" "• 3rd+"
                if (/^[\u2022\u00b7]\s*(1st|2nd|3rd\+?)$/i.test(t)) return;
                leafTexts.push(t);
            });

            // 去重（保持顺序）
            const seen = new Set();
            const unique = [];
            for (const t of leafTexts) {
                if (!seen.has(t)) { seen.add(t); unique.push(t); }
            }

            // 4. 识别各字段
            //    第一个非噪音文本 = headline (职位/头衔)
            //    第二个非噪音文本 = location
            let headline = '', location = '';
            let fieldIdx = 0;
            for (const t of unique) {
                if (isNoise(t)) continue;
                if (fieldIdx === 0) { headline = t; fieldIdx++; }
                else if (fieldIdx === 1) { location = t; break; }
            }

            // 5. 拆分 headline → title + company
            const { title, company } = splitHeadline(headline);

            if (name && linkedin_url) {
                results.push({ name, title, company, location, linkedin_url });
            }
        } catch (e) { /* skip broken card */ }
    });

    return {
        count: results.length,
        cards_found: cards.length,
        page_url: location.href,
        results,
    };
})()
"""

# ---------------------------------------------------------------------------
# 个人主页提取：当前职位 + 公司
# ---------------------------------------------------------------------------
PROFILE_EXTRACT_JS = r"""
return (() => {
    const result = { title: '', company: '', location: '', headline: '' };

    // 1. headline (顶部描述)
    const headlineEl = document.querySelector('div.text-body-medium.break-words');
    if (headlineEl) result.headline = headlineEl.textContent.trim();

    // 2. 地点
    const locEl = document.querySelector('.text-body-small.inline.t-black--light.break-words');
    if (locEl) result.location = locEl.textContent.trim();

    // 3. 从 Experience 区块提取第一条经历（= 当前职位）
    const expAnchor = document.querySelector('#experience');
    if (expAnchor) {
        const section = expAnchor.closest('section');
        if (section) {
            const entities = section.querySelectorAll('[data-view-name="profile-component-entity"]');
            if (entities.length > 0) {
                const first = entities[0];

                // 职位: 第一个粗体 span
                const boldSpans = first.querySelectorAll('.t-bold span[aria-hidden="true"]');
                for (const s of boldSpans) {
                    const t = s.textContent.trim();
                    if (t && t.length > 1) { result.title = t; break; }
                }

                // 公司: .t-normal span 中，排除日期格式的
                const normalSpans = first.querySelectorAll('.t-normal span[aria-hidden="true"]');
                const datePattern = /^\w{3}\s+\d{4}\s*[-–]/;
                for (const s of normalSpans) {
                    const t = s.textContent.trim();
                    if (!t || t.length < 2) continue;
                    if (datePattern.test(t)) continue;
                    if (/^\d+\s*(yr|mo|year|month)/i.test(t)) continue;
                    // 跳过 "Full-time" / "Part-time" / "Contract" 等
                    if (/^(Full-time|Part-time|Contract|Internship|Freelance|Self-employed|Seasonal|Apprenticeship)$/i.test(t)) continue;
                    result.company = t;
                    break;
                }
            }
        }
    }

    // 4. 回退: 如果 Experience 没有找到，尝试从 headline 拆分
    if (!result.title && result.headline) {
        const h = result.headline;
        const idx = h.lastIndexOf(' at ');
        if (idx > 0) {
            result.title = h.slice(0, idx).trim();
            if (!result.company) result.company = h.slice(idx + 4).trim();
        } else {
            result.title = h.split('|')[0].trim();
        }
    }

    return result;
})()
"""

# ---------------------------------------------------------------------------
# 页面健康检查 JS (安全挑战 / 登录墙 / 频率限制)
# ---------------------------------------------------------------------------
PAGE_HEALTH_JS = r"""
return (() => {
    const url = location.href;
    const text = document.body ? document.body.innerText.slice(0, 2000) : '';
    const title = document.title || '';

    const checks = {
        ok: true,
        url: url,
        issue: null,
    };

    if (url.includes('/checkpoint/') || url.includes('/challenge/')) {
        checks.ok = false;
        checks.issue = 'security_challenge';
    } else if (url.includes('/authwall') || url.includes('/login') || url.includes('/uas/login')) {
        checks.ok = false;
        checks.issue = 'login_required';
    } else if (text.includes('unusual activity') || text.includes('security verification')) {
        checks.ok = false;
        checks.issue = 'security_challenge';
    } else if (text.includes('too many requests') || text.includes('rate limit')) {
        checks.ok = false;
        checks.issue = 'rate_limited';
    } else if (title.includes('Page not found') || url.includes('/404')) {
        checks.ok = false;
        checks.issue = 'page_not_found';
    }

    return checks;
})()
"""

# ---------------------------------------------------------------------------
# 获取当前页码和总结果数
# ---------------------------------------------------------------------------
PAGE_INFO_JS = r"""
return (() => {
    // 页码: 从 URL 的 page= 参数或激活的分页按钮获取
    let page = 1;
    const urlParams = new URLSearchParams(location.search);
    if (urlParams.has('page')) {
        page = parseInt(urlParams.get('page')) || 1;
    }

    // 总结果数: 搜索页顶部的 "About X results"
    let totalText = '';
    const h2s = document.querySelectorAll('h2');
    for (const h of h2s) {
        const t = h.textContent.trim();
        if (/result/i.test(t)) { totalText = t; break; }
    }
    // 也尝试从 div 中查找
    if (!totalText) {
        document.querySelectorAll('div').forEach(d => {
            if (d.children.length === 0) {
                const t = d.textContent.trim();
                if (/^\d[\d,]*\+?\s+results?$/i.test(t) || /^About\s+[\d,]+/i.test(t)) {
                    totalText = t;
                }
            }
        });
    }

    return { page, totalText };
})()
"""


class CDPDomExtractor:
    """
    通过 Selenium driver.execute_script() 在页面中运行 JS 提取联系人。
    不依赖 HTML 文件或 NLP 模型。
    """

    def __init__(self):
        logger.info("CDPDomExtractor 初始化完成")

    # ------------------------------------------------------------------
    # 核心提取
    # ------------------------------------------------------------------
    def extract_contacts(self, driver) -> List[Dict[str, Any]]:
        """
        从当前页面提取所有搜索结果联系人。

        Args:
            driver: Selenium WebDriver 实例（已在搜索结果页）

        Returns:
            联系人字典列表，每个包含 name/title/company/location/linkedin_url
        """
        try:
            result = driver.execute_script(EXTRACT_CONTACTS_JS)
        except Exception as e:
            logger.error(f"JS 提取执行失败: {e}")
            return []

        if not result or not isinstance(result, dict):
            logger.warning("JS 提取返回空结果")
            return []

        contacts = result.get("results", [])
        cards_found = result.get("cards_found", 0)
        logger.info(
            f"DOM 提取完成: {cards_found} 张卡片, {len(contacts)} 个联系人"
        )

        cleaned = []
        for c in contacts:
            contact = self._post_process(c)
            if contact:
                cleaned.append(contact)

        return cleaned

    # ------------------------------------------------------------------
    # 页面健康检查
    # ------------------------------------------------------------------
    @staticmethod
    def check_page_health(driver) -> Dict[str, Any]:
        """
        检查页面是否正常（未触发安全挑战、登录墙、频率限制等）。

        Returns:
            {'ok': True/False, 'issue': None/'security_challenge'/...}
        """
        try:
            return driver.execute_script(PAGE_HEALTH_JS) or {"ok": True, "issue": None}
        except Exception as e:
            logger.warning(f"页面健康检查失败: {e}")
            return {"ok": False, "issue": "check_failed", "error": str(e)}

    # ------------------------------------------------------------------
    # 页面信息
    # ------------------------------------------------------------------
    @staticmethod
    def get_page_info(driver) -> Dict[str, Any]:
        """获取当前页码和总结果数"""
        try:
            return driver.execute_script(PAGE_INFO_JS) or {"page": 1, "totalText": ""}
        except Exception:
            return {"page": 1, "totalText": ""}

    # ------------------------------------------------------------------
    # 个人主页信息提取（补全 company/title）
    # ------------------------------------------------------------------
    def extract_profile_details(self, driver) -> Dict[str, str]:
        """
        从当前打开的 LinkedIn 个人主页提取职位和公司。

        Returns:
            {'title': ..., 'company': ..., 'location': ..., 'headline': ...}
        """
        try:
            result = driver.execute_script(PROFILE_EXTRACT_JS)
            return result or {}
        except Exception as e:
            logger.warning(f"个人主页提取失败: {e}")
            return {}

    def enrich_contacts_from_profiles(
        self, driver, contacts: List[Dict[str, Any]],
        delay_between: float = 3.0,
        only_missing_company: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        遍历联系人列表，对缺少 company 的人打开其个人主页补全信息。

        Args:
            driver: Selenium WebDriver
            contacts: 联系人列表
            delay_between: 每次访问间隔（秒）
            only_missing_company: True=只补全缺 company 的；False=全部补全

        Returns:
            补全后的联系人列表（原地修改）
        """
        import time

        to_enrich = []
        for c in contacts:
            if only_missing_company and c.get("company"):
                continue
            if c.get("linkedin_url"):
                to_enrich.append(c)

        if not to_enrich:
            logger.info("所有联系人已有公司信息，无需补全")
            return contacts

        logger.warning(
            f"开始补全 {len(to_enrich)} 个联系人的公司信息..."
        )
        enriched_count = 0
        original_url = driver.current_url

        for i, contact in enumerate(to_enrich):
            try:
                url = contact["linkedin_url"]
                logger.info(f"[{i+1}/{len(to_enrich)}] {contact['name']} → {url}")

                driver.get(url)
                time.sleep(delay_between)

                # 健康检查
                health = self.check_page_health(driver)
                if not health.get("ok"):
                    logger.warning(
                        f"  页面异常: {health.get('issue')}, 跳过"
                    )
                    continue

                details = self.extract_profile_details(driver)
                if not details:
                    continue

                updated = False
                if details.get("company") and not contact.get("company"):
                    contact["company"] = details["company"]
                    updated = True
                if details.get("title") and not contact.get("title"):
                    contact["title"] = details["title"]
                    updated = True
                if details.get("location") and not contact.get("location"):
                    contact["location"] = details["location"]
                    updated = True

                if updated:
                    enriched_count += 1
                    logger.info(
                        f"  补全: {contact['name']} → "
                        f"{details.get('title','')} @ {details.get('company','')}"
                    )

            except Exception as e:
                logger.warning(f"  补全失败: {e}")
                continue

        # 回到原页面
        try:
            driver.get(original_url)
        except Exception:
            pass

        logger.warning(
            f"公司信息补全完成: {enriched_count}/{len(to_enrich)} 人补全成功"
        )
        return contacts

    # ------------------------------------------------------------------
    # 后处理
    # ------------------------------------------------------------------
    def _post_process(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Python 侧的二次清洗"""
        name = (raw.get("name") or "").strip()
        title = (raw.get("title") or "").strip()
        company = (raw.get("company") or "").strip()
        location = (raw.get("location") or "").strip()
        url = (raw.get("linkedin_url") or "").strip()

        if not name or not url:
            return None

        # 过滤非个人 profile URL（URN 格式或公司页）
        if "/company/" in url:
            return None

        # 名字额外清洗: 去掉残留的 Unicode 标记
        name = re.sub(r"[\u2022\u00b7]\s*(1st|2nd|3rd\+?)\s*$", "", name).strip()
        name = re.sub(r"\s*\(Open to Work\)\s*$", "", name, flags=re.IGNORECASE).strip()

        # company 清洗: 去掉前导 "the " (LinkedIn 偶尔保留)
        # 但保留如 "The Coca-Cola Company" 这样的正式名称
        # 只去掉全小写的 "the "
        if company.startswith("the ") and not company[4:5].isupper():
            company = company[4:]

        # location 清洗: 有时包含 "Area" 后缀，保持原样即可

        return {
            "name": name,
            "title": title,
            "company": company,
            "location": location,
            "linkedin_url": url,
        }
