#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 数据精炼器 — 用大模型从 headline 中拆分出真正的职位和公司。

解决的问题：LinkedIn 搜索结果的 headline 是用户自定义的一行文字，
格式千变万化，规则无法穷举。比如：
  "Owner, Director Optimum Nutrition & Training"
  "PhD Student | Machine Learning | NLP"
  "Helping Healthcare Providers Streamline Admin Tasks"

LLM 能理解语义，正确拆分出 title 和 company。
"""

import json
import logging
import time
from typing import List, Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a data cleaning expert. Your task is to split LinkedIn headlines into separate "title" (job title/role) and "company" (organization name) fields.

Rules:
- If the headline contains a company name (after "at", "@", ",", "|", or by context), extract it
- Common patterns: "Job Title at Company", "Job Title, Company", "Job Title | Company"
- If the headline is purely a job description or self-promotion, company should be empty
- If the headline IS a company/organization name (not a person's role), title should be empty and company should have the name
- Keep original text, do not translate
- For "Self-employed" / "Freelance" type roles, company = "" (empty)
- Employment type suffixes like "· Self-employed", "· Part-time", "· Full-time" should be stripped from company

Respond with ONLY a valid JSON array, no other text."""

USER_PROMPT_TEMPLATE = """Split these LinkedIn headlines into title and company. Input:

{input_json}

Output format (JSON array, same order, same ids):
[{{"id": 0, "title": "...", "company": "..."}}, ...]"""


class LLMRefiner:
    """用 LLM 精炼联系人数据（拆分 headline → title + company）"""

    def __init__(self, config: Dict[str, Any] = None):
        if not config:
            config = self._load_config()
        self.enabled = config.get("enabled", False)
        self.api_base = config.get("api_base", "")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model_name", "")
        self.batch_size = config.get("batch_size", 20)
        self.temperature = config.get("temperature", 0.1)
        self.timeout = config.get("timeout", 30)

        if self.enabled and self.api_key:
            logger.info(f"LLMRefiner 就绪: {self.model}")
        else:
            logger.warning("LLMRefiner 未启用（缺少配置或 API key）")

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        """从 settings.json 读取 llm_enrichment 配置，${ENV_VAR} 自动替换"""
        import os, re
        paths = [
            os.path.join(os.getcwd(), "config", "settings.json"),
            os.path.join(os.path.dirname(__file__), "..", "..", "config", "settings.json"),
        ]
        for p in paths:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        raw = json.load(f).get("llm_enrichment", {})
                    resolved = {}
                    for k, v in raw.items():
                        if isinstance(v, str):
                            v = re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), m.group(0)), v)
                        resolved[k] = v
                    return resolved
                except Exception:
                    continue
        return {}

    def refine_contacts(self, contacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        对联系人列表中的 title 字段用 LLM 拆分，补全 company。

        原地修改并返回 contacts 列表。
        """
        if not self.enabled or not self.api_key:
            logger.warning("LLM 精炼未启用，跳过")
            return contacts

        # 筛选需要处理的联系人：有 title 但缺 company，或 title 看起来包含公司名
        to_refine = []
        for i, c in enumerate(contacts):
            title = c.get("title", "")
            company = c.get("company", "")
            if not title:
                continue
            # 已有 company 且 title 不含公司名特征的，跳过
            if company and not self._title_might_contain_company(title):
                continue
            to_refine.append((i, c))

        if not to_refine:
            logger.info("所有联系人的 title/company 已足够清晰，无需 LLM 精炼")
            return contacts

        logger.warning(f"开始 LLM 精炼 {len(to_refine)} 个联系人的 title/company...")

        # 分批处理
        refined_count = 0
        for batch_start in range(0, len(to_refine), self.batch_size):
            batch = to_refine[batch_start:batch_start + self.batch_size]
            batch_num = batch_start // self.batch_size + 1
            total_batches = (len(to_refine) + self.batch_size - 1) // self.batch_size

            logger.info(f"LLM 批次 {batch_num}/{total_batches} ({len(batch)} 人)")

            input_items = []
            for j, (idx, c) in enumerate(batch):
                input_items.append({
                    "id": j,
                    "headline": c.get("title", ""),
                    "current_company": c.get("company", ""),
                })

            results = self._call_llm(input_items)
            if not results:
                continue

            for item in results:
                try:
                    j = item["id"]
                    if j < 0 or j >= len(batch):
                        continue
                    idx, contact = batch[j]
                    new_title = (item.get("title") or "").strip()
                    new_company = (item.get("company") or "").strip()

                    # 清理工作类型后缀
                    for suffix in ["· Self-employed", "· Part-time", "· Full-time",
                                   "· Contract", "· Freelance", "· Internship"]:
                        new_company = new_company.replace(suffix, "").strip()

                    updated = False
                    if new_title and new_title != contact.get("title", ""):
                        contact["title"] = new_title
                        updated = True
                    if new_company and not contact.get("company"):
                        contact["company"] = new_company
                        updated = True
                    elif new_company and new_company != contact.get("company", ""):
                        contact["company"] = new_company
                        updated = True

                    if updated:
                        refined_count += 1
                except (KeyError, IndexError, TypeError):
                    continue

            # 简单限流
            if batch_start + self.batch_size < len(to_refine):
                time.sleep(0.5)

        logger.warning(f"LLM 精炼完成: {refined_count}/{len(to_refine)} 人更新")
        return contacts

    def _call_llm(self, items: List[Dict]) -> Optional[List[Dict]]:
        """调用 LLM API"""
        input_json = json.dumps(items, ensure_ascii=False, indent=2)
        user_msg = USER_PROMPT_TEMPLATE.format(input_json=input_json)

        url = f"{self.api_base.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "temperature": self.temperature,
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()

            # 提取 JSON（可能被 markdown 代码块包裹）
            if content.startswith("```"):
                lines = content.split("\n")
                json_lines = []
                inside = False
                for line in lines:
                    if line.startswith("```") and not inside:
                        inside = True
                        continue
                    elif line.startswith("```") and inside:
                        break
                    elif inside:
                        json_lines.append(line)
                content = "\n".join(json_lines)

            return json.loads(content)

        except requests.exceptions.Timeout:
            logger.warning("LLM 请求超时")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"LLM 返回的 JSON 解析失败: {e}")
            return None
        except Exception as e:
            logger.warning(f"LLM 调用失败: {e}")
            return None

    @staticmethod
    def _title_might_contain_company(title: str) -> bool:
        """启发式判断 title 是否可能包含公司名"""
        if not title:
            return False
        indicators = [
            " at ", " @ ", " - ", " | ",
            "Founder", "Owner", "CEO", "CTO", "COO",
            "Director", "Head of", "President",
            "Co-founder", "Co-Founder",
        ]
        return any(ind in title for ind in indicators)
