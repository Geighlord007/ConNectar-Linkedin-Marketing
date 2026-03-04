#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM客户端模块
用于与AI模型进行交互，支持OpenAI兼容的API
"""

import json
import os
import re
import requests
import time
from typing import Dict, List, Optional, Any

try:
    from ..utils.config_loader import ConfigLoader
    from ..utils.logger import get_logger
except ImportError:
    from .config_loader import ConfigLoader
    from .logger import get_logger

class LLMClient:
    """LLM客户端类"""

    @staticmethod
    def _is_unresolved_placeholder(value: Any) -> bool:
        return isinstance(value, str) and bool(re.fullmatch(r"\$\{\w+\}", value.strip()))

    @staticmethod
    def _pick_env(keys: List[str]) -> str:
        for key in keys:
            value = (os.getenv(key) or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _resolve_placeholder_env(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        matched = re.fullmatch(r"\$\{(\w+)\}", value.strip())
        if not matched:
            return ""
        env_key = matched.group(1)
        return (os.getenv(env_key) or "").strip()

    def _resolve_runtime_config(self) -> Dict[str, Any]:
        llm_cfg = self.llm_config if isinstance(self.llm_config, dict) else {}
        api_key = llm_cfg.get("api_key")
        api_base = llm_cfg.get("api_base")
        model_name = llm_cfg.get("model_name")
        api_path = llm_cfg.get("api_path", "chat/completions")

        if self._is_unresolved_placeholder(api_key):
            api_key = self._resolve_placeholder_env(api_key)
        if self._is_unresolved_placeholder(api_base):
            api_base = self._resolve_placeholder_env(api_base)
        if self._is_unresolved_placeholder(model_name):
            model_name = self._resolve_placeholder_env(model_name)

        api_key = (str(api_key).strip() if api_key is not None else "") or self._pick_env(["LLM_API_KEY"])
        api_base = (str(api_base).strip() if api_base is not None else "") or self._pick_env(["LLM_API_BASE"])
        model_name = (str(model_name).strip() if model_name is not None else "") or self._pick_env(["LLM_MODEL"])

        if not api_base:
            api_base = "https://api.openai.com/v1"
        if not model_name:
            model_name = "gpt-4o-mini"

        if api_base and not str(api_base).startswith(("http://", "https://")):
            api_base = f"https://{str(api_base).lstrip('/')}"

        api_base = str(api_base).rstrip("/")
        api_path = str(api_path or "chat/completions").lstrip("/")
        api_url = f"{api_base}/{api_path}" if api_base else ""
        return {
            "api_key": api_key,
            "api_base": api_base,
            "model_name": model_name,
            "api_url": api_url,
        }
    
    def __init__(self, config_loader: ConfigLoader = None):
        """初始化LLM客户端
        
        Args:
            config_loader: 配置加载器
        """
        self.config_loader = config_loader or ConfigLoader()
        self.config = self.config_loader.load_settings()
        self.logger = get_logger("llm_client")
        self.llm_config = self.config.get('llm', {})
        
        if not self.llm_config.get('enabled', False):
            self.logger.warning("LLM功能未启用")
            self.enabled = False
            return
            
        self.enabled = True
        runtime = self._resolve_runtime_config()
        self.api_base = runtime.get("api_base", "")
        self.api_key = runtime.get("api_key", "")
        self.model_name = runtime.get("model_name", "")
        self.max_tokens = self.llm_config.get('max_tokens', 1000)
        self.temperature = self.llm_config.get('temperature', 0.3)
        self.timeout = self.llm_config.get('timeout', 30)
        self.retry_attempts = self.llm_config.get('retry_attempts', 3)
        self.thinking_type = str(self.llm_config.get('thinking_type', 'disabled') or '').strip().lower()

        self.api_url = runtime.get("api_url", "")
        if not self.api_key or not self.model_name or not self.api_url:
            self.logger.error("LLM配置不完整：请检查api_key/api_base/model_name")
            self.enabled = False
            return
        
        self.logger.info(f"LLM客户端初始化完成，模型: {self.model_name}")
    
    def is_enabled(self) -> bool:
        """检查LLM是否启用"""
        return self.enabled

    @staticmethod
    def _extract_json_text(raw_text: str) -> str:
        text = (raw_text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
            return text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start:end + 1].strip()
        return text

    def _build_payload(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        model_name = str(self.model_name or "")
        model_lower = model_name.lower()
        max_tokens = kwargs.get('max_tokens', self.max_tokens)
        temperature = kwargs.get('temperature', self.temperature)
        thinking_type_override = kwargs.get("thinking_type")
        content_length = sum(len(str(message.get("content", ""))) for message in messages if isinstance(message, dict))

        try:
            max_tokens = int(max_tokens)
        except Exception:
            max_tokens = 1024
        try:
            temperature = float(temperature)
        except Exception:
            temperature = 0.3

        # 不限制 max_tokens，根据实际需要分配
        # if content_length >= 25000:
        #     max_tokens = min(max_tokens, 3000)
        # elif content_length >= 12000:
        #     max_tokens = min(max_tokens, 5000)
        # else:
        #     max_tokens = min(max_tokens, 8000)

        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        thinking_type = str(thinking_type_override or self.thinking_type or "").strip().lower()
        api_base_lower = str(getattr(self, "api_base", "") or "").lower()
        supports_thinking_toggle = ("open.bigmodel.cn" in api_base_lower) or ("glm" in model_lower)
        if supports_thinking_toggle and thinking_type in ("enabled", "disabled"):
            payload["thinking"] = {"type": thinking_type}
        return payload
    
    def _make_request(self, messages: List[Dict[str, str]], **kwargs) -> Optional[str]:
        """发送请求到LLM API"""
        if not self.enabled:
            self.logger.warning("LLM功能未启用，无法发送请求")
            return None
        request_timeout = kwargs.get("timeout", self.timeout)
        retry_attempts = kwargs.get("retry_attempts", self.retry_attempts)
        try:
            request_timeout = float(request_timeout)
        except Exception:
            request_timeout = float(self.timeout)
        try:
            retry_attempts = int(retry_attempts)
        except Exception:
            retry_attempts = int(self.retry_attempts)
        retry_attempts = max(1, retry_attempts)
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = self._build_payload(messages, **kwargs)
        
        for attempt in range(retry_attempts):
            response = None
            try:
                self.logger.info(f"发送LLM请求 (尝试 {attempt + 1}/{retry_attempts})")
                self.logger.info(f"请求URL: {self.api_url}")
                self.logger.info(f"请求payload: {json.dumps(payload, ensure_ascii=False)[:500]}...")
                
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=request_timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    message = result['choices'][0]['message']
                    content = message.get('content', '')
                    if not content:
                        content = message.get('reasoning_content', '')
                    self.logger.debug("LLM请求成功")
                    return content.strip()
                else:
                    self.logger.error(f"LLM API错误: {response.status_code} - {response.text}")
                    response_text = str(response.text or "")
                    lowered = response_text.lower()
                    if response.status_code == 400:
                        if "invalid temperature" in lowered and payload.get("temperature") != 1.0:
                            payload["temperature"] = 1.0
                            continue
                        if ("\"code\":\"1210\"" in response_text or "参数有误" in response_text) and int(payload.get("max_tokens", 0)) > 4096:
                            payload["max_tokens"] = 4096
                            continue
                        if ("\"code\":\"1210\"" in response_text or "参数有误" in response_text) and int(payload.get("max_tokens", 0)) > 2048:
                            payload["max_tokens"] = 2048
                            continue
                    
            except requests.exceptions.Timeout:
                self.logger.warning(f"LLM请求超时 (尝试 {attempt + 1}/{self.retry_attempts})")
                if int(payload.get("max_tokens", 0)) > 2048:
                    payload["max_tokens"] = max(2048, int(payload.get("max_tokens", 0)) // 2)
            except requests.exceptions.RequestException as e:
                self.logger.error(f"LLM请求异常: {str(e)}")
            except Exception as e:
                self.logger.error(f"LLM处理异常: {str(e)}")
            
            if attempt < retry_attempts - 1:
                # 对于速率限制错误，使用更长的等待时间
                if response and response.status_code == 429:
                    wait_time = 20 + (attempt * 10)  # 20秒起步，每次增加10秒
                    self.logger.info(f"遇到速率限制，等待 {wait_time} 秒后重试")
                    time.sleep(wait_time)
                else:
                    time.sleep(2 ** attempt)  # 指数退避
        
        self.logger.error("LLM请求失败，已达到最大重试次数")
        return None
    
    def classify_contact_tags(self, contact_info: Dict[str, Any], filter_criteria: str) -> Dict[str, Any]:
        """使用LLM对联系人进行标签分类和匹配评分
        
        Args:
            contact_info: 联系人信息字典
            filter_criteria: 筛选条件描述
            
        Returns:
            包含标签和评分的字典
        """
        if not self.enabled:
            return {
                'tags': [],
                'match_score': 0.0,
                'match_reasons': [],
                'industry_category': 'unknown',
                'seniority_level': 'unknown'
            }
        
        # 构建提示词
        prompt = f"""
请分析以下联系人信息，并根据筛选条件进行评估：

联系人信息：
- 姓名: {contact_info.get('name', 'N/A')}
- 职位: {contact_info.get('title', 'N/A')}
- 公司: {contact_info.get('company', 'N/A')}
- 地点: {contact_info.get('location', 'N/A')}

筛选条件: {filter_criteria}

请返回JSON格式的分析结果，包含以下字段：
{{
  "tags": ["相关标签列表"],
  "match_score": 0.85,  // 0-1之间的匹配分数
  "match_reasons": ["匹配原因列表"],
  "industry_category": "行业分类",
  "seniority_level": "资历级别(junior/mid/senior/executive)",
  "key_skills": ["关键技能列表"],
  "relevance_analysis": "相关性分析说明"
}}

请确保返回有效的JSON格式，不要包含其他文本。
"""
        
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的人才分析师，擅长根据职位信息和筛选条件进行精准的人才匹配分析。请始终返回有效的JSON格式结果。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        try:
            response = self._make_request(messages)
            if response:
                cleaned = self._extract_json_text(response)
                result = json.loads(cleaned)
                normalized = self._normalize_tag_result(result)
                self.logger.debug(f"LLM标签分类完成: {contact_info.get('name', 'Unknown')} - 分数: {normalized['match_score']}")
                return normalized
        except json.JSONDecodeError as e:
            self.logger.error(f"LLM响应JSON解析失败: {str(e)}")
        except Exception as e:
            self.logger.error(f"LLM标签分类异常: {str(e)}")
        
        # 返回默认结果
        return {
            'tags': [],
            'match_score': 0.0,
            'match_reasons': [],
            'industry_category': 'unknown',
            'seniority_level': 'unknown',
            'key_skills': [],
            'relevance_analysis': 'LLM分析失败'
        }

    def classify_contacts_tags_batch(self, contacts_info: List[Dict[str, Any]], filter_criteria: str) -> List[Dict[str, Any]]:
        if not self.enabled:
            return [self._normalize_tag_result({}) for _ in contacts_info]
        contacts_payload = []
        for idx, contact in enumerate(contacts_info):
            contacts_payload.append({
                "id": idx,
                "name": contact.get('name', 'N/A'),
                "title": contact.get('title', 'N/A'),
                "company": contact.get('company', 'N/A'),
                "location": contact.get('location', 'N/A')
            })
        prompt = f"""
请根据筛选条件，对以下联系人逐一评分并返回JSON。

筛选条件: {filter_criteria}

联系人列表:
{json.dumps(contacts_payload, ensure_ascii=False)}

请返回JSON格式：
{{
  "results": [
    {{
      "id": 0,
      "tags": ["相关标签列表"],
      "match_score": 0.85,
      "match_reasons": ["匹配原因列表"],
      "industry_category": "行业分类",
      "seniority_level": "资历级别(junior/mid/senior/executive)"
    }}
  ]
}}

要求：
1. 每个输入联系人都必须在results中返回一个对象
2. id必须与输入id一致
3. 仅返回JSON，不要返回其他文本
"""
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的人才分析师，擅长根据职位信息和筛选条件进行精准的人才匹配分析。请始终返回有效的JSON格式结果。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        try:
            response = self._make_request(messages)
            if not response:
                return [self._normalize_tag_result({}) for _ in contacts_info]
            cleaned = self._extract_json_text(response)
            parsed = json.loads(cleaned)
            items = parsed.get('results', []) if isinstance(parsed, dict) else parsed
            if not isinstance(items, list):
                return [self._normalize_tag_result({}) for _ in contacts_info]
            by_id = {}
            for item in items:
                if not isinstance(item, dict):
                    continue
                try:
                    item_id = int(item.get('id'))
                except Exception:
                    continue
                by_id[item_id] = self._normalize_tag_result(item)
            ordered = []
            for idx in range(len(contacts_info)):
                ordered.append(by_id.get(idx, self._normalize_tag_result({})))
            return ordered
        except Exception as e:
            self.logger.error(f"LLM批量标签分类异常: {str(e)}")
            return [self._normalize_tag_result({}) for _ in contacts_info]

    def _normalize_tag_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(result, dict):
            result = {}
        normalized = dict(result)
        required_fields = ['tags', 'match_score', 'match_reasons', 'industry_category', 'seniority_level']
        for field in required_fields:
            if field not in normalized:
                normalized[field] = [] if field in ['tags', 'match_reasons'] else 'unknown' if field in ['industry_category', 'seniority_level'] else 0.0
        try:
            normalized['match_score'] = max(0.0, min(1.0, float(normalized.get('match_score', 0.0))))
        except Exception:
            normalized['match_score'] = 0.0
        return normalized
    
    def extract_keywords_from_criteria(self, criteria: str) -> dict:
        """
        Convert user requirements into standardized filtering labels using LLM
        
        Args:
            criteria: Natural language filtering requirements
            
        Returns:
            dict: Standardized labels for matching against contact data
        """
        if not self.enabled:
            return self._get_empty_criteria()
        
        prompt = f"""
将以下招聘需求转换为标准化标签：{criteria}

返回JSON格式：
{{
    "job_titles": ["职位名称和变体"],
    "companies": ["具体公司名称"],
    "seniority_levels": ["职级层次"],
    "industries": ["行业领域"],
    "skills": ["技能要求"],
    "locations": ["地理位置"],
    "company_types": ["公司类型"]
}}

转换规则：
- CTO/技术VP → ["CTO", "Chief Technology Officer", "VP Technology", "技术副总裁"]
- 高管 → ["CEO", "CFO", "CTO", "VP", "Director"]
- smithfield company → ["Smithfield", "Smithfield Foods"]
- 科技公司 → ["Technology", "Software", "Tech", "IT"]

只返回JSON，无其他文本。
"""
        
        messages = [
            {
                "role": "system",
                "content": "You are an expert in translating hiring requirements into standardized tags. Your job is to convert non-standard terms (like C-suite, tech roles, etc.) into specific, matchable keywords that can be found in professional profiles."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        try:
            response = self._make_request(messages)
            if response:
                # 清理响应文本，移除可能的markdown格式
                cleaned_response = response.strip()
                if cleaned_response.startswith('```json'):
                    cleaned_response = cleaned_response[7:]
                if cleaned_response.endswith('```'):
                    cleaned_response = cleaned_response[:-3]
                cleaned_response = cleaned_response.strip()
                
                self.logger.info(f"LLM原始响应: {response[:200]}...")
                self.logger.info(f"清理后响应: {cleaned_response[:200]}...")
                
                result = json.loads(cleaned_response)
                
                # Validate required fields
                required_fields = ["job_titles", "seniority_levels", "industries", "skills", "locations", "company_types"]
                for field in required_fields:
                    if field not in result:
                        result[field] = []
                
                total_labels = sum(len(result[field]) for field in required_fields)
                self.logger.info(f"LLM标准化成功: 提取了 {total_labels} 个标签")
                
                return result
            else:
                self.logger.error("LLM响应为空")
                return self._get_empty_criteria()
                
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON解析失败: {str(e)}")
            self.logger.error(f"原始响应: {response}")
            return self._get_empty_criteria()
        except Exception as e:
            self.logger.error(f"LLM标准化失败: {str(e)}")
            return self._get_empty_criteria()
    
    def _get_empty_criteria(self) -> dict:
        """Return empty criteria structure"""
        return {
            "job_titles": [],
            "seniority_levels": [],
            "industries": [],
            "skills": [],
            "locations": [],
            "company_types": []
        }
    
    def classify_contact_tags_with_llm(self, contact: dict, filter_criteria: str) -> dict:
        """使用LLM对联系人进行智能标签分类和匹配评分"""
        if not self.is_enabled():
            return {'match_score': 0.0, 'match_reasons': []}
        
        # 构建联系人信息
        contact_info = f"""
联系人信息：
姓名：{contact.get('name', '未知')}
职位：{contact.get('title', '未知')}
公司：{contact.get('company', '未知')}
地点：{contact.get('location', '未知')}
"""
        
        prompt = f"""
请分析以下联系人是否符合筛选条件，并给出匹配评分。

{contact_info}

筛选条件：{filter_criteria}

请按以下JSON格式返回结果：
{{
    "match_score": 0.85,
    "match_reasons": [
        "职位匹配：目标职位与联系人职位高度相关",
        "地理位置匹配：位于目标区域"
    ],
    "analysis": {{
        "job_relevance": 0.9,
        "location_match": 0.8,
        "company_relevance": 0.7,
        "overall_fit": 0.85
    }}
}}

注意：
1. 匹配分数应该综合考虑职位相关性、地理位置、公司背景等因素
2. 如果某些信息缺失，请基于现有信息进行合理评估
3. 匹配原因要具体明确，说明为什么匹配或不匹配
4. 只返回JSON格式，不要添加其他文字说明
"""
        
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的人才分析师，擅长根据职位信息和筛选条件进行精准的人才匹配分析。请始终返回有效的JSON格式结果。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        try:
            response = self._make_request(messages)
            
            # 尝试解析JSON响应
            try:
                result = json.loads(response)
                
                # 验证必要字段
                if 'match_score' not in result:
                    result['match_score'] = 0.0
                if 'match_reasons' not in result:
                    result['match_reasons'] = []
                
                # 确保分数在合理范围内
                result['match_score'] = max(0.0, min(1.0, float(result['match_score'])))
                
                self.logger.debug(f"联系人分类完成: {contact.get('name', '未知')} - 分数: {result['match_score']}")
                return result
                
            except json.JSONDecodeError:
                self.logger.warning(f"LLM返回的不是有效JSON格式: {response}")
                # 尝试从文本中提取分数
                import re
                score_match = re.search(r'"match_score"\s*:\s*([0-9.]+)', response)
                if score_match:
                    score = float(score_match.group(1))
                    return {
                        'match_score': max(0.0, min(1.0, score)),
                        'match_reasons': ['基于LLM文本分析的匹配结果']
                    }
                else:
                    return {'match_score': 0.0, 'match_reasons': ['LLM响应格式错误']}
                    
        except Exception as e:
            self.logger.error(f"LLM联系人分类失败: {str(e)}")
            return {'match_score': 0.0, 'match_reasons': ['LLM分析失败']}
