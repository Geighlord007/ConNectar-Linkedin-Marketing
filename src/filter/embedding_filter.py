#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Embedding筛选引擎
使用Embedding-3向量模型 + 规则匹配进行快速筛选

核心特性：
- 需求增强（LLM扩展关键词库）
- Embedding-3向量相似度计算
- 规则匹配加分（公司、职位）
- 极快速度：150人约2秒
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import requests
import numpy as np

from ..utils.config_loader import ConfigLoader

# 确保 .env 环境变量被加载
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
    load_dotenv(env_path, override=False)
except ImportError:
    pass


@dataclass
class ScoringResult:
    """评分结果"""
    contact_name: str
    job_score: float
    company_score: float
    location_score: float
    skill_score: float
    match_score: float

    # 详细信息
    embedding_similarity: float = 0.0
    company_rule_score: float = 0.0
    job_rule_score: float = 0.0

    # 原始数据
    original_index: int = 0
    original_contact: Dict = field(default_factory=dict)


class EmbeddingFilter:
    """基于Embedding的筛选器"""

    def __init__(self, config_path: str = "config/settings.json"):
        self.logger = logging.getLogger(__name__)
        self.config = self._load_config(config_path)

        # 初始化组件
        self.requirement_enhancement = None
        self.embedding_client = None

        # 缓存
        self._requirement_embedding = None

    def _load_config(self, config_path: str) -> Dict:
        """加载配置"""
        try:
            loader = ConfigLoader()
            settings = loader.load_settings()
            self.logger.info(f"配置加载成功: {config_path}")
            return settings if isinstance(settings, dict) else {}
        except Exception as e:
            self.logger.error(f"配置加载失败: {e}")
            return {}

    def _get_api_key(self) -> Optional[str]:
        """获取Embedding API Key"""
        # 优先从环境变量读取
        api_key = os.getenv("ZHIPU_EMBEDDING_KEY")
        if api_key:
            return api_key

        # 从配置文件读取
        key = self.config.get("embedding_model", {}).get("api_key")
        if key and not key.startswith("${"):
            return key

        return None

    def _get_api_base(self) -> str:
        """获取Embedding API Base URL"""
        # 优先从环境变量读取
        api_base = os.getenv("ZHIPU_EMBEDDING_BASE")
        if api_base:
            return api_base

        # 从配置文件读取
        base = self.config.get("embedding_model", {}).get("api_base")
        if base and not base.startswith("${"):
            return base

        return "https://open.bigmodel.cn/api/paas/v4"

    def enhance_requirement(self, requirements_input: str,
                           contacts_sample: List[Dict] = None) -> Dict:
        """增强需求（LLM扩展关键词库）

        返回：
        {
            "target_companies": [...],
            "job_keywords": [...],
            "industry_keywords": [...],
            "related_companies": [...],
            "job_synonyms": [...],
            "location_aliases": [...]
        }
        """
        if not self.config.get("llm_enhancement", {}).get("enabled", False):
            return self._fallback_requirement_parsing(requirements_input)

        api_key = self._get_api_key()
        if not api_key:
            self.logger.warning("未找到API Key，使用本地解析")
            return self._fallback_requirement_parsing(requirements_input)

        # 收集公司样本作为提示
        company_hints = []
        if contacts_sample:
            companies = [c.get("company", "") for c in contacts_sample if c.get("company")]
            # 统计频率
            from collections import Counter
            company_counter = Counter(companies)
            company_hints = [c for c, _ in company_counter.most_common(20)]

        # 构建增强Prompt
        prompt = self._build_enhancement_prompt(
            requirements_input,
            company_hints
        )

        try:
            url = self._get_api_base().rstrip('/') + '/chat/completions'
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }

            llm_config = self.config.get("llm_enhancement", {})
            model = llm_config.get("model_name", "glm-4.5-air")
            timeout = llm_config.get('timeout', 60)

            # 如果是环境变量格式，解析它
            if model.startswith("${") and model.endswith("}"):
                var_name = model[2:-1].split(":-")[0]
                model = os.getenv(var_name, "glm-4.5-air")

            payload = {
                'model': model,
                'messages': [
                    {'role': 'system', 'content': '你是招聘需求语义增强器。只返回JSON。'},
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': llm_config.get('temperature', 0.2),
                'max_tokens': llm_config.get('max_tokens', 2000),
                'timeout': timeout
            }

            response = requests.post(url, headers=headers, json=payload,
                                    timeout=timeout)
            result = response.json()

            if 'choices' not in result:
                self.logger.error(f"LLM响应错误: {result}")
                return self._fallback_requirement_parsing(requirements_input)

            content = result['choices'][0]['message']['content']

            # 解析JSON
            # 去掉可能的markdown代码块标记
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```\s*$', '', content)
            content = content.strip()

            enhanced = json.loads(content)

            self.logger.info(f"需求增强完成: {len(enhanced.get('target_companies', []))} 公司, "
                          f"{len(enhanced.get('job_keywords', []))} 职位关键词")

            return enhanced

        except Exception as e:
            self.logger.error(f"需求增强失败: {e}")
            return self._fallback_requirement_parsing(requirements_input)

    def _build_enhancement_prompt(self, requirements_input: str,
                                 company_hints: List[str]) -> str:
        """构建需求增强Prompt"""
        hints_str = ", ".join(company_hints[:20]) if company_hints else "无"

        return f"""你是招聘需求语义增强器。根据用户需求扩展关键词库。

【用户需求】
{requirements_input}

【当前候选人中常见公司样本】
{hints_str}

【任务】
扩展以下4个类别的关键词，每个类别返回5-10个词：
1. target_companies: 目标公司名称（包括子公司、相关公司）
2. job_keywords: 目标职位关键词（包括同义词、类似职位）
3. industry_keywords: 行业关键词（包括上下游、相关领域）
4. location_aliases: 地点别名（包括城市别名、区域名称）

【要求】
- 中英文都可以
- 扩展词要相关、精准，不要泛泛的词
- 只返回JSON，格式如下:
{{
  "target_companies": ["...", "..."],
  "job_keywords": ["...", "..."],
  "industry_keywords": ["...", "..."],
  "location_aliases": ["...", "..."]
}}
"""

    def _fallback_requirement_parsing(self, requirements_input: str) -> Dict:
        """回退：本地解析需求"""
        # 简单的关键词提取
        text = requirements_input.lower()
        companies = []
        jobs = []
        locations = []

        # 常见职位关键词
        job_patterns = [
            r'ceo|cto|cfo|coo', r'vp|vice president', r'director',
            r'manager|管理', r'executive|高管', r'president|总裁'
        ]
        for pattern in job_patterns:
            matches = re.findall(pattern, text)
            jobs.extend(matches)

        # 常见公司名（简化）
        company_match = re.search(r'([^,，。！？!?\s]+)(?:公司|company|corp)', requirements_input, re.IGNORECASE)
        if company_match:
            companies.append(company_match.group(1).strip())

        # 地点关键词
        location_patterns = [r'usa|us|united states', r'china|中国', r'北美|north america']
        for pattern in location_patterns:
            if re.search(pattern, text):
                locations.extend(re.findall(pattern, text))

        return {
            "target_companies": companies,
            "job_keywords": list(set(jobs)),
            "industry_keywords": [],
            "location_aliases": locations
        }

    def compute_requirement_embedding(self, requirement_text: str) -> np.ndarray:
        """计算需求文本的向量"""
        if not self.config.get("embedding_model", {}).get("enabled", False):
            return None

        api_key = self._get_api_key()
        if not api_key:
            self.logger.warning("未找到Embedding API Key")
            return None

        try:
            url = self._get_api_base().rstrip('/') + '/embeddings'
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }

            emb_config = self.config.get("embedding_model", {})
            model = emb_config.get("model_name", "embedding-3")

            # 如果是环境变量格式，解析它
            if model.startswith("${") and model.endswith("}"):
                var_name = model[2:-1].split(":-")[0]
                model = os.getenv(var_name, "embedding-3")

            payload = {
                'model': model,
                'input': [requirement_text],
                'dimensions': emb_config.get('dimensions', 2048)
            }

            response = requests.post(url, headers=headers, json=payload,
                                    timeout=emb_config.get('timeout', 30))
            result = response.json()

            if 'data' not in result:
                self.logger.error(f"Embedding响应错误: {result}")
                return None

            embedding = np.array(result['data'][0]['embedding'])
            self._requirement_embedding = embedding
            return embedding

        except Exception as e:
            self.logger.error(f"计算需求向量失败: {e}")
            return None

    def compute_contact_embeddings(self, contacts: List[Dict]) -> List[np.ndarray]:
        """批量计算联系人职位向量（支持分批处理）"""
        if self._requirement_embedding is None:
            self.logger.warning("需求向量为空，无法计算相似度")
            return [None] * len(contacts)

        if not self.config.get("embedding_model", {}).get("enabled", False):
            return [None] * len(contacts)

        api_key = self._get_api_key()
        if not api_key:
            return [None] * len(contacts)

        try:
            url = self._get_api_base().rstrip('/') + '/embeddings'
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }

            emb_config = self.config.get("embedding_model", {})
            model = emb_config.get("model_name", "embedding-3")
            timeout = emb_config.get('timeout', 60)

            # 如果是环境变量格式，解析它
            if model.startswith("${") and model.endswith("}"):
                var_name = model[2:-1].split(":-")[0]
                model = os.getenv(var_name, "embedding-3")

            # 构建输入：职位 + 公司 + 行业（组合文本）
            inputs = []
            for contact in contacts:
                title = contact.get("title", "")
                company = contact.get("company", "")
                industry = contact.get("industry", "")
                # 组合职位、公司和行业，提高匹配精度
                text = f"{title} at {company}" if title and company else title or company
                if industry:
                    text += f" in {industry}"
                inputs.append(text)

            # 分批处理（智谱API限制一次最多64条）
            batch_size = emb_config.get('batch_size', 50)
            all_embeddings = []

            for batch_start in range(0, len(inputs), batch_size):
                batch_inputs = inputs[batch_start:batch_start + batch_size]
                batch_num = batch_start // batch_size + 1
                total_batches = (len(inputs) + batch_size - 1) // batch_size

                self.logger.info(f"Embedding批次 {batch_num}/{total_batches} ({len(batch_inputs)} 条)")

                payload = {
                    'model': model,
                    'input': batch_inputs,
                    'dimensions': emb_config.get('dimensions', 2048)
                }

                response = requests.post(url, headers=headers, json=payload, timeout=timeout)
                result = response.json()

                if 'data' not in result:
                    self.logger.error(f"Embedding批量计算错误: {result}")
                    return [None] * len(contacts)

                batch_embeddings = [np.array(item['embedding']) for item in result['data']]
                all_embeddings.extend(batch_embeddings)

            # 如果批次处理后的数量不匹配，填充None
            if len(all_embeddings) != len(contacts):
                self.logger.warning(f"Embedding数量不匹配: 期望{len(contacts)}, 实际{len(all_embeddings)}")
                while len(all_embeddings) < len(contacts):
                    all_embeddings.append(None)

            return all_embeddings

        except Exception as e:
            self.logger.error(f"批量计算联系人向量失败: {e}")
            return [None] * len(contacts)

    def calculate_similarity(self, contact_embedding: np.ndarray) -> float:
        """计算相似度（余弦相似度）"""
        if contact_embedding is None or self._requirement_embedding is None:
            return 0.0

        try:
            # 余弦相似度
            similarity = np.dot(self._requirement_embedding, contact_embedding) / (
                np.linalg.norm(self._requirement_embedding) * np.linalg.norm(contact_embedding)
            )
            return float(similarity)
        except:
            return 0.0

    def calculate_rule_scores(self, contact: Dict, enhanced: Dict) -> Tuple[float, float, float]:
        """计算规则匹配分数

        Returns:
            (公司分数, 职位分数, 地点分数)
        """
        company_score = 0.0
        job_score = 0.0
        location_score = 0.0

        rule_config = self.config.get("filtering", {}).get("rule_scores", {})

        # 公司匹配
        company = contact.get("company", "").lower()
        target_companies = [c.lower() for c in enhanced.get("target_companies", [])]

        if company:
            # 精确匹配
            if company in target_companies:
                company_score = rule_config.get("company_exact_match", 0.8)
            else:
                # 部分匹配
                for target in target_companies:
                    if target in company or company in target:
                        company_score = rule_config.get("company_partial_match", 0.5)
                        break

        # 职位关键词匹配
        title = contact.get("title", "").lower()
        job_keywords = [j.lower() for j in enhanced.get("job_keywords", [])]

        if title:
            matched_keywords = [kw for kw in job_keywords if kw in title]
            if matched_keywords:
                job_score = min(rule_config.get("job_keyword_match", 0.3) * len(matched_keywords), 1.0)

        # 地点匹配
        location = contact.get("location", "").lower()
        location_aliases = [l.lower() for l in enhanced.get("location_aliases", [])]

        if location:
            for alias in location_aliases:
                if alias in location or location in alias:
                    location_score = 0.3  # 地点匹配加分
                    break

        return company_score, job_score, location_score

    def filter_contacts(self,
                       contacts: List[Dict],
                       requirements_input: str,
                       min_score: float = 0.3) -> Tuple[List[Dict], Dict]:
        """筛选联系人

        Args:
            contacts: 联系人列表
            requirements_input: 需求描述
            min_score: 最低分数

        Returns:
            (筛选结果, 统计信息)
        """
        start_time = time.time()

        self.logger.info(f"开始筛选 {len(contacts)} 个联系人")

        # 1. 需求增强
        self.logger.info("正在增强需求...")
        sample_contacts = contacts[:50] if len(contacts) > 50 else contacts
        enhanced = self.enhance_requirement(requirements_input, sample_contacts)

        # 2. 计算需求向量
        self.logger.info("正在计算需求向量...")
        self.compute_requirement_embedding(requirements_input)

        if self._requirement_embedding is None:
            self.logger.warning("需求向量计算失败，回退到规则匹配")
            return self._filter_by_rules_only(contacts, enhanced, min_score)

        # 3. 批量计算联系人向量
        self.logger.info(f"正在计算 {len(contacts)} 个联系人向量...")
        contact_embeddings = self.compute_contact_embeddings(contacts)

        # 4. 评分
        self.logger.info("正在评分...")
        results = []
        weights = self.config.get("filtering", {}).get("weights", {})

        for i, (contact, embedding) in enumerate(zip(contacts, contact_embeddings)):
            # 向量相似度
            similarity = self.calculate_similarity(embedding)

            # 规则分数
            company_rule, job_rule, location_rule = self.calculate_rule_scores(contact, enhanced)

            # 整合向量相似度到各项分数中
            # job_score: 规则匹配(40%) + 向量相似度(60%)
            job_score = job_rule * 0.4 + similarity * 0.6

            # company_score: 规则匹配(50%) + 向量相似度(50%)
            company_score = company_rule * 0.5 + similarity * 0.5

            # location_score: 仅规则匹配（暂不使用向量）
            location_score = location_rule

            # 综合评分：使用整合后的分数
            match_score = (
                similarity * weights.get("embedding_similarity", 0.3) +
                company_score * weights.get("company_match", 0.4) +
                job_score * weights.get("job_keywords", 0.3)
            )

            # 创建结果
            result = ScoringResult(
                contact_name=contact.get("name", "Unknown"),
                job_score=job_score,
                company_score=company_score,
                location_score=location_score,
                skill_score=0.0,
                match_score=match_score,
                embedding_similarity=similarity,
                company_rule_score=company_rule,
                job_rule_score=job_rule,
                original_index=i,
                original_contact=contact
            )

            if match_score >= min_score:
                results.append(result)

        # 排序
        results.sort(key=lambda x: x.match_score, reverse=True)

        # 转换为输出格式
        output_contacts = [self._convert_result(r) for r in results]

        # 统计
        end_time = time.time()
        stats = {
            "total_input": len(contacts),
            "total_output": len(results),
            "match_rate": len(results) / len(contacts) if contacts else 0,
            "processing_time": end_time - start_time,
            "contacts_per_second": len(contacts) / (end_time - start_time) if end_time > start_time else 0,
            "filter_version": "EmbeddingFilter",
            "enhancement": {
                "target_companies": len(enhanced.get("target_companies", [])),
                "job_keywords": len(enhanced.get("job_keywords", [])),
                "industry_keywords": len(enhanced.get("industry_keywords", []))
            }
        }

        self.logger.info(f"筛选完成: {len(results)}/{len(contacts)}, 耗时{end_time - start_time:.2f}秒")

        return output_contacts, stats

    def _filter_by_rules_only(self, contacts: List[Dict], enhanced: Dict,
                             min_score: float) -> Tuple[List[Dict], Dict]:
        """仅使用规则匹配（向量计算失败时的回退）"""
        results = []
        weights = self.config.get("filtering", {}).get("weights", {})
        rule_config = self.config.get("filtering", {}).get("rule_scores", {})

        for i, contact in enumerate(contacts):
            company_rule, job_rule, location_rule = self.calculate_rule_scores(contact, enhanced)

            # 无向量相似度时，提高规则权重
            total_weight = weights.get("company_match", 0.35) + weights.get("job_keywords", 0.15)
            match_score = (company_rule * weights.get("company_match", 0.35) +
                          job_rule * weights.get("job_keywords", 0.15)) / total_weight

            if match_score >= min_score:
                result = ScoringResult(
                    contact_name=contact.get("name", "Unknown"),
                    job_score=job_rule,
                    company_score=company_rule,
                    location_score=location_rule,
                    skill_score=0.0,
                    match_score=match_score,
                    embedding_similarity=0.0,
                    company_rule_score=company_rule,
                    job_rule_score=job_rule,
                    original_index=i,
                    original_contact=contact
                )
                results.append(result)

        results.sort(key=lambda x: x.match_score, reverse=True)
        output_contacts = [self._convert_result(r) for r in results]

        stats = {
            "total_input": len(contacts),
            "total_output": len(results),
            "match_rate": len(results) / len(contacts) if contacts else 0,
            "filter_version": "EmbeddingFilter (Rules Only)",
            "enhancement": {
                "target_companies": len(enhanced.get("target_companies", [])),
                "job_keywords": len(enhanced.get("job_keywords", []))
            }
        }

        return output_contacts, stats

    def _convert_result(self, result: ScoringResult) -> Dict:
        """转换结果为输出格式"""
        original = result.original_contact or {}

        return {
            "index": result.original_index,
            "name": result.contact_name,
            "title": original.get("title", ""),
            "company": original.get("company", ""),
            "location": original.get("location", ""),
            "industry": original.get("industry", ""),
            "match_score": round(result.match_score, 3),
            "job_score": round(result.job_score, 3),
            "company_score": round(result.company_score, 3),
            "location_score": round(result.location_score, 3),
            "skill_score": round(result.skill_score, 3),
            # 保留原始数据中的其他字段
            **{k: v for k, v in original.items() if k not in ["name", "title", "company", "location", "industry"]}
        }