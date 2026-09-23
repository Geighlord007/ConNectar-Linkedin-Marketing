import copy
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.utils.llm_client import LLMClient
from src.utils.config_loader import ConfigLoader


@dataclass
class ScoringResult:
    contact_name: str
    job_score: float
    company_score: float
    location_score: float
    skill_score: float
    match_score: float
    match_reasons: List[str] = field(default_factory=list)
    original_contact: Dict[str, Any] = field(default_factory=dict)


class RuleEngine:
    def __init__(self, config: Dict[str, Any]):
        self.logger = logging.getLogger(__name__)
        self.config = config if isinstance(config, dict) else {}
        self.company_rules = self.config.get("company_rules", {}) or {}
        self.job_rules = self.config.get("job_rules", {}) or {}
        self.industry_rules = self.config.get("industry_rules", {}) or {}
        self.special_rules = self.config.get("special_rules", {}) or {}

    def _get_title(self, contact: Dict[str, Any]) -> str:
        return str((contact or {}).get("title", "") or "").strip().lower()

    def _get_company(self, contact: Dict[str, Any]) -> str:
        return str((contact or {}).get("company", "") or "").strip().lower()

    def _get_industry_text(self, contact: Dict[str, Any]) -> str:
        contact = contact or {}
        parts = [
            str(contact.get("industry", "") or ""),
            str(contact.get("company", "") or ""),
            str(contact.get("title", "") or ""),
            str(contact.get("search_keyword", "") or ""),
        ]
        return " ".join(parts).strip().lower()

    def _check_general_manager(self, title: str) -> bool:
        cfg = self.special_rules.get("general_manager", {}) or {}
        if not cfg.get("enabled", False):
            return "general manager" in title
        if cfg.get("requires_both_words", True):
            return "general" in title and "manager" in title
        return "general manager" in title

    def calculate_job_score(self, contact: Dict[str, Any]) -> Tuple[float, str]:
        title = self._get_title(contact)
        weights = self.job_rules.get("weights", {}) or {}
        irrelevant = [str(x).lower() for x in self.job_rules.get("irrelevant_keywords", [])]
        executive = [str(x).lower() for x in self.job_rules.get("executive_keywords", [])]
        director = [str(x).lower() for x in self.job_rules.get("director_keywords", [])]
        scientist = [str(x).lower() for x in self.job_rules.get("scientist_keywords", [])]

        for keyword in irrelevant:
            if keyword and keyword in title:
                score = float(weights.get("irrelevant", 0.0))
                return max(0.0, min(1.0, score)), f"不相关职位: {keyword}"

        if self._check_general_manager(title):
            score = float(weights.get("executive", 1.0))
            return max(0.0, min(1.0, score)), "高管职位匹配: general manager"

        for keyword in executive:
            if keyword and keyword in title:
                score = float(weights.get("executive", 1.0))
                return max(0.0, min(1.0, score)), f"高管职位匹配: {keyword}"

        for keyword in director:
            if keyword and keyword in title:
                score = float(weights.get("director", 0.8))
                return max(0.0, min(1.0, score)), f"总监职位匹配: {keyword}"

        for keyword in scientist:
            if keyword and keyword in title:
                score = float(weights.get("scientist", 0.9))
                return max(0.0, min(1.0, score)), f"科学职位匹配: {keyword}"

        if "manager" in title or "lead" in title:
            return 0.6, "管理类职位基础匹配"
        if title:
            return 0.2, "存在职位信息，弱相关"
        return 0.0, "缺少职位信息"

    def calculate_company_score(self, contact: Dict[str, Any]) -> Tuple[float, str]:
        company = self._get_company(contact)
        target_companies = [str(x).lower() for x in self.company_rules.get("target_companies", [])]
        excluded_companies = [str(x).lower() for x in self.company_rules.get("excluded_companies", [])]
        weights = self.company_rules.get("weights", {}) or {}

        for excluded in excluded_companies:
            if excluded and excluded in company:
                score = float(weights.get("excluded_penalty", 0.0))
                return max(0.0, min(1.0, score)), f"排除公司命中: {excluded}"

        for target in target_companies:
            if target and target == company:
                score = float(weights.get("exact_match", 1.0))
                return max(0.0, min(1.0, score)), f"目标公司精确匹配: {target}"

        for target in target_companies:
            if target and target in company:
                score = float(weights.get("partial_match", 0.8))
                return max(0.0, min(1.0, score)), f"目标公司部分匹配: {target}"

        if company:
            return 0.1, "非目标公司"
        return 0.0, "缺少公司信息"

    def calculate_industry_score(self, contact: Dict[str, Any]) -> Tuple[float, str]:
        industry_text = self._get_industry_text(contact)
        keywords = [str(x).lower() for x in self.industry_rules.get("high_value_keywords", [])]
        weights = self.industry_rules.get("weights", {}) or {}
        high_value = float(weights.get("high_value", 1.2))
        standard = float(weights.get("standard", 1.0))

        for keyword in keywords:
            if keyword and keyword in industry_text:
                return high_value, f"高价值行业匹配: {keyword}"
        return standard, "标准行业分数"


class ScoringEngine:
    def __init__(self, config_path: str = "config/settings.json"):
        self.logger = logging.getLogger(__name__)
        self.config = self._load_config()
        self.llm_client = LLMClient()

    def _load_config(self) -> Dict[str, Any]:
        try:
            settings = ConfigLoader().load_settings()
            filtering = settings.get("filtering", {}) if isinstance(settings, dict) else {}
            return {"filtering": filtering if isinstance(filtering, dict) else {}}
        except Exception as e:
            self.logger.error(f"加载配置失败: {e}")
            return {"filtering": {}}

    def _safe_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _normalize_contact(self, contact: Dict[str, Any]) -> Dict[str, Any]:
        contact = contact or {}
        return {
            "name": self._safe_text(contact.get("name")) or "Unknown",
            "title": self._safe_text(contact.get("title")),
            "company": self._safe_text(contact.get("company")),
            "location": self._safe_text(contact.get("location")),
            "industry": self._safe_text(contact.get("industry")),
            "search_keyword": self._safe_text(contact.get("search_keyword")),
            **contact,
        }

    def is_llm_ready(self) -> bool:
        return bool(self.llm_client.is_enabled())

    def _clamp_100(self, value: Any) -> float:
        try:
            score = float(value)
        except Exception:
            score = 0.0
        if 0.0 <= score <= 1.0:
            score = score * 100.0
        return max(0.0, min(100.0, score))

    def _build_llm_prompt(self, contact: Dict[str, Any], requirements_input: str, requirement_profile: Optional[Dict[str, Any]]) -> str:
        profile_json = json.dumps(requirement_profile or {}, ensure_ascii=False)
        enhancement_json = json.dumps((requirement_profile or {}).get("industry_enhancement", {}), ensure_ascii=False)
        return f"""
你是招聘筛选系统中的高级简历评估器。请对候选人做结构化打分，遵循“硬性条件优先 + 可解释证据 + 风险扣分”。

需求描述:
{requirements_input}

结构化需求标签:
{profile_json}

行业增强信息:
{enhancement_json}

候选人信息:
- 姓名: {contact.get("name", "")}
- 职位: {contact.get("title", "")}
- 公司: {contact.get("company", "")}
- 地点: {contact.get("location", "")}
- 行业: {contact.get("industry", "")}
- 关键词来源: {contact.get("search_keyword", "")}

请按如下JSON返回:
{{
  "dimension_scores": {{
    "must_have_match": 0,
    "role_relevance": 0,
    "seniority_fit": 0,
    "industry_company_fit": 0,
    "evidence_quality": 0,
    "location_fit": 0
  }},
  "bonus": 0,
  "penalty": 0,
  "overall_score": 0,
  "decision": "strong_yes|yes|borderline|no",
  "matched_keywords": ["..."],
  "missing_must_have": ["..."],
  "risk_flags": ["..."],
  "match_reasons": ["..."],
  "analysis_summary": "..."
}}

要求:
1) 所有分数区间0-100，bonus和penalty区间0-15。
2) overall_score由你按专业判断给出，综合维度、加分和扣分。
3) 必须只返回JSON，不要任何额外文本。
"""

    def _collect_company_hints(self, contacts: Optional[List[Dict[str, Any]]]) -> List[str]:
        if not contacts:
            return []
        counter: Counter = Counter()
        for row in contacts:
            if not isinstance(row, dict):
                continue
            name = self._safe_text(row.get("company"))
            if not name:
                continue
            counter[name] += 1
        ranked = [item[0] for item in counter.most_common(40)]
        return ranked

    def _build_enhancement_prompt(
        self,
        requirements_input: str,
        requirement_profile: Dict[str, Any],
        company_hints: List[str],
    ) -> str:
        profile_json = json.dumps(requirement_profile or {}, ensure_ascii=False)
        hints_json = json.dumps(company_hints or [], ensure_ascii=False)
        return f"""
你是招聘需求语义增强器。请根据用户需求自动补全行业相关词、公司别名和产业链近邻概念。

用户需求:
{requirements_input}

已解析需求:
{profile_json}

当前联系人中常见公司样本:
{hints_json}

请输出JSON:
{{
  "related_industries": ["..."],
  "synonyms": ["..."],
  "upstream_downstream_keywords": ["..."],
  "related_company_examples": ["..."],
  "region_hints": ["..."],
  "logic_notes": ["..."]
}}

要求:
1) 输出尽量短，避免无关泛化词。
2) 若是垂直行业需求，优先补全同义词、上下游词和可能出现的公司别名。
3) 只返回JSON。
"""

    def _build_dynamic_industry_enhancement(
        self,
        requirements_input: str,
        requirement_profile: Dict[str, Any],
        contacts: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        if not requirements_input or not self.llm_client.is_enabled():
            return {}
        company_hints = self._collect_company_hints(contacts)
        prompt = self._build_enhancement_prompt(
            requirements_input=requirements_input,
            requirement_profile=requirement_profile,
            company_hints=company_hints,
        )
        messages = [
            {"role": "system", "content": "你是结构化信息抽取助手，只能返回JSON对象。"},
            {"role": "user", "content": prompt},
        ]
        filtering_cfg = self.config.get("filtering", {}) if isinstance(self.config, dict) else {}
        enhance_timeout = filtering_cfg.get("llm_enhance_timeout_seconds", 12)
        enhance_retries = filtering_cfg.get("llm_enhance_retry_attempts", 1)
        enhance_max_tokens = filtering_cfg.get("llm_enhance_max_tokens", 450)
        enhance_temperature = filtering_cfg.get("llm_enhance_temperature", 0.2)
        enhance_thinking_type = filtering_cfg.get("llm_enhance_thinking_type", "enabled")
        response = self.llm_client._make_request(
            messages,
            temperature=enhance_temperature,
            max_tokens=enhance_max_tokens,
            timeout=enhance_timeout,
            retry_attempts=enhance_retries,
            thinking_type=enhance_thinking_type,
        )
        if not response:
            return {}
        try:
            cleaned = self.llm_client._extract_json_text(response)
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _merge_requirement_profile(
        self,
        base_profile: Dict[str, Any],
        enhancement: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged = dict(base_profile or {})
        enhancement = enhancement if isinstance(enhancement, dict) else {}
        def _merge_list(key: str, extra: List[Any]):
            existing = merged.get(key, [])
            if not isinstance(existing, list):
                existing = []
            items = []
            seen = set()
            for value in list(existing) + list(extra or []):
                text = self._safe_text(value)
                if not text:
                    continue
                norm = text.lower()
                if norm in seen:
                    continue
                seen.add(norm)
                items.append(text)
            merged[key] = items
        _merge_list("industries", enhancement.get("related_industries", []))
        _merge_list("companies", enhancement.get("related_company_examples", []))
        _merge_list("skills", enhancement.get("upstream_downstream_keywords", []))
        _merge_list("company_types", enhancement.get("synonyms", []))
        _merge_list("locations", enhancement.get("region_hints", []))
        merged["industry_enhancement"] = enhancement
        return merged

    def _score_with_llm(
        self,
        normalized: Dict[str, Any],
        requirements_input: str,
        requirement_profile: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not str(requirements_input or "").strip():
            return None
        if not self.llm_client.is_enabled():
            return None
        prompt = self._build_llm_prompt(normalized, requirements_input, requirement_profile)
        messages = [
            {
                "role": "system",
                "content": "你是招聘筛选评分器。输出必须为JSON对象。",
            },
            {"role": "user", "content": prompt},
        ]
        filtering_cfg = self.config.get("filtering", {}) if isinstance(self.config, dict) else {}
        score_timeout = filtering_cfg.get("llm_score_timeout_seconds", 12)
        score_retries = filtering_cfg.get("llm_score_retry_attempts", 1)
        score_max_tokens = filtering_cfg.get("llm_score_max_tokens", 700)
        score_temperature = filtering_cfg.get("llm_score_temperature", 0.2)
        score_thinking_type = filtering_cfg.get("llm_score_thinking_type", "disabled")
        response = self.llm_client._make_request(
            messages,
            temperature=score_temperature,
            max_tokens=score_max_tokens,
            timeout=score_timeout,
            retry_attempts=score_retries,
            thinking_type=score_thinking_type,
        )
        if not response:
            return None
        try:
            cleaned = self.llm_client._extract_json_text(response)
            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict):
                return None
            return parsed
        except Exception:
            return None

    def _build_bulk_llm_prompt(
        self,
        contacts: List[Dict[str, Any]],
        requirements_input: str,
        requirement_profile: Optional[Dict[str, Any]],
    ) -> str:
        profile_json = json.dumps(requirement_profile or {}, ensure_ascii=False)
        contacts_payload = []
        for idx, contact in enumerate(contacts):
            contacts_payload.append(
                {
                    "index": idx,
                    "name": contact.get("name", ""),
                    "title": contact.get("title", ""),
                    "company": contact.get("company", ""),
                    "location": contact.get("location", ""),
                    "industry": contact.get("industry", ""),
                    "search_keyword": contact.get("search_keyword", ""),
                }
            )
        contacts_json = json.dumps(contacts_payload, ensure_ascii=False)
        return f"""
你是招聘筛选系统评分器。请一次性评估多个候选人，并只返回JSON对象。

需求描述:
{requirements_input}

结构化需求标签:
{profile_json}

候选人列表:
{contacts_json}

返回格式:
{{
  "results": [
    {{
      "index": 0,
      "dimension_scores": {{
        "role_relevance": 0,
        "industry_company_fit": 0,
        "location_fit": 0,
        "evidence_quality": 0
      }},
      "job_score": 0,
      "company_score": 0,
      "location_score": 0,
      "skill_score": 0,
      "overall_score": 0,
      "match_reasons": ["..."],
      "risk_flags": ["..."]
    }}
  ]
}}

要求:
1) 所有分数区间0-100。
2) results长度与输入人数一致，index必须对应输入index。
3) 输出尽量精简，每个候选人最多2条match_reasons和1条risk_flags。
4) 只返回JSON，不要额外文本。
"""

    def _score_with_llm_bulk(
        self,
        contacts: List[Dict[str, Any]],
        requirements_input: str,
        requirement_profile: Optional[Dict[str, Any]],
    ) -> Optional[List[Optional[Dict[str, Any]]]]:
        if not contacts:
            return []
        if not str(requirements_input or "").strip():
            return None
        if not self.llm_client.is_enabled():
            return None
        prompt = self._build_bulk_llm_prompt(contacts, requirements_input, requirement_profile)
        messages = [
            {"role": "system", "content": "你是招聘筛选评分器。输出必须为JSON对象。"},
            {"role": "user", "content": prompt},
        ]
        filtering_cfg = self.config.get("filtering", {}) if isinstance(self.config, dict) else {}
        score_timeout = filtering_cfg.get("llm_score_timeout_seconds", 12)
        score_retries = filtering_cfg.get("llm_score_retry_attempts", 1)
        score_max_tokens = filtering_cfg.get("llm_score_max_tokens", 700)
        bulk_max_tokens = filtering_cfg.get("llm_score_bulk_max_tokens", max(int(score_max_tokens), 1600))
        score_temperature = filtering_cfg.get("llm_score_temperature", 0.2)
        score_thinking_type = filtering_cfg.get("llm_score_thinking_type", "disabled")
        response = self.llm_client._make_request(
            messages,
            temperature=score_temperature,
            max_tokens=bulk_max_tokens,
            timeout=score_timeout,
            retry_attempts=score_retries,
            thinking_type=score_thinking_type,
        )
        if not response:
            return None
        try:
            cleaned = self.llm_client._extract_json_text(response)
            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict):
                return None
            rows = parsed.get("results", [])
            if not isinstance(rows, list):
                return None
            aligned: List[Optional[Dict[str, Any]]] = [None] * len(contacts)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    idx = int(row.get("index"))
                except Exception:
                    continue
                if 0 <= idx < len(aligned):
                    aligned[idx] = row
            return aligned
        except Exception:
            return None

    def _normalize_dimension_scores(self, raw: Dict[str, Any]) -> Dict[str, float]:
        if not isinstance(raw, dict):
            return {}
        normalized: Dict[str, float] = {}
        for key, value in raw.items():
            normalized[key] = self._clamp_100(value)
        return normalized

    def _build_result_from_payload(
        self,
        normalized: Dict[str, Any],
        original_contact: Dict[str, Any],
        llm_payload: Optional[Dict[str, Any]],
    ) -> ScoringResult:
        if llm_payload is None:
            dimensions = {}
            overall = 0.0
            role_score = 0.0
            company_score = 0.0
            reasons = ["LLM分析失败或未启用"]
        else:
            dimensions = self._normalize_dimension_scores(llm_payload.get("dimension_scores", {}))
            overall = self._clamp_100(llm_payload.get("overall_score", 0.0))
            if overall <= 0.0:
                overall = self._clamp_100(llm_payload.get("match_score", 0.0))
            role_base = llm_payload.get("job_score", dimensions.get("role_relevance", 0.0))
            company_base = llm_payload.get("company_score", dimensions.get("industry_company_fit", 0.0))
            location_base = llm_payload.get("location_score", dimensions.get("location_fit", 0.0))
            evidence_base = llm_payload.get("skill_score", dimensions.get("evidence_quality", 0.0))
            role_score = max(0.0, min(1.0, self._clamp_100(role_base) / 100.0))
            company_score = max(0.0, min(1.0, self._clamp_100(company_base) / 100.0))
            reasons = list(llm_payload.get("match_reasons", []))
            dimensions.setdefault("location_fit", self._clamp_100(location_base))
            dimensions.setdefault("evidence_quality", self._clamp_100(evidence_base))

        match_score = max(0.0, min(1.0, overall / 100.0))
        location_score = max(0.0, min(1.0, dimensions.get("location_fit", 0.0) / 100.0))
        skill_score = max(0.0, min(1.0, dimensions.get("evidence_quality", 0.0) / 100.0))
        reasons = reasons[:6] if reasons else ["缺少明确匹配证据"]
        if llm_payload and llm_payload.get("risk_flags"):
            for flag in llm_payload.get("risk_flags", [])[:2]:
                reasons.append(f"风险: {flag}")

        return ScoringResult(
            contact_name=normalized.get("name", "Unknown"),
            job_score=role_score,
            company_score=company_score,
            location_score=location_score,
            skill_score=skill_score,
            match_score=match_score,
            match_reasons=reasons,
            original_contact=original_contact,
        )

    def score_contact(
        self,
        contact: Dict[str, Any],
        requirements_input: str = "",
        requirement_profile: Optional[Dict[str, Any]] = None,
    ) -> ScoringResult:
        normalized = self._normalize_contact(contact)
        original_contact = copy.deepcopy(contact or {})

        llm_payload = self._score_with_llm(
            normalized=normalized,
            requirements_input=requirements_input,
            requirement_profile=requirement_profile,
        )
        return self._build_result_from_payload(
            normalized=normalized,
            original_contact=original_contact,
            llm_payload=llm_payload,
        )

    def score_contacts_batch(
        self,
        contacts: List[Dict[str, Any]],
        requirements_input: str = "",
        requirement_profile: Optional[Dict[str, Any]] = None,
    ) -> List[ScoringResult]:
        if not contacts:
            return []
        single_llm_handler = getattr(self, "_score_with_llm", None)
        use_single_scoring_path = (
            callable(single_llm_handler)
            and (
                not hasattr(single_llm_handler, "__func__")
                or single_llm_handler.__func__ is not ScoringEngine._score_with_llm
            )
        )
        if use_single_scoring_path:
            return [
                self.score_contact(
                    contact=contact,
                    requirements_input=requirements_input,
                    requirement_profile=requirement_profile,
                )
                for contact in contacts
            ]
        normalized_contacts = [self._normalize_contact(c) for c in contacts]
        payloads = self._score_with_llm_bulk(
            contacts=normalized_contacts,
            requirements_input=requirements_input,
            requirement_profile=requirement_profile,
        )
        if payloads is None:
            payloads = [None] * len(contacts)
        if len(payloads) < len(contacts):
            payloads = list(payloads) + [None] * (len(contacts) - len(payloads))
        final_results: List[ScoringResult] = []
        for idx, contact in enumerate(contacts):
            payload = payloads[idx] if idx < len(payloads) else None
            final_results.append(
                self._build_result_from_payload(
                    normalized=normalized_contacts[idx],
                    original_contact=copy.deepcopy(contact or {}),
                    llm_payload=payload,
                )
            )
        return final_results

    def build_requirement_profile(
        self,
        requirements_input: str,
        contacts: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if not requirements_input:
            return {}
        if not self.llm_client.is_enabled():
            return {}
        try:
            profile = self.llm_client.extract_keywords_from_criteria(requirements_input)
            profile = profile if isinstance(profile, dict) else {}
            enhancement = self._build_dynamic_industry_enhancement(
                requirements_input=requirements_input,
                requirement_profile=profile,
                contacts=contacts,
            )
            return self._merge_requirement_profile(profile, enhancement)
        except Exception:
            return {}
