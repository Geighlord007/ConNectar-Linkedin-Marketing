import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .scoring_engine import ScoringEngine, ScoringResult


class ContactFilter:
    def __init__(self, config_path: str = "config/settings.json"):
        self.scoring_engine = ScoringEngine(config_path=config_path)
        self.stats = {
            "total_processed": 0,
            "total_matched": 0,
            "processing_time": 0.0,
            "start_time": None,
            "end_time": None,
        }

    def _convert_result(self, result: ScoringResult, detailed_output: bool) -> Dict[str, Any]:
        original = result.original_contact or {}
        converted = dict(original)
        converted["name"] = converted.get("name", result.contact_name)
        converted["title"] = converted.get("title", "N/A")
        converted["company"] = converted.get("company", "N/A")
        converted["location"] = converted.get("location", "N/A")
        converted["job_score"] = float(result.job_score)
        converted["company_score"] = float(result.company_score)
        converted["location_score"] = float(result.location_score)
        converted["skill_score"] = float(result.skill_score)
        converted["match_score"] = float(result.match_score)
        return converted

    def _build_stats(
        self,
        scoring_results: List[ScoringResult],
        filtered_results: List[ScoringResult],
        min_score: float,
        elapsed: float,
    ) -> Dict[str, Any]:
        total = len(scoring_results)
        matched = len(filtered_results)
        avg = sum(r.match_score for r in scoring_results) / total if total else 0.0
        return {
            "scoring_mode": "rule_based",
            "total_contacts": total,
            "filtered_contacts": matched,
            "match_rate": (matched / total) if total else 0.0,
            "min_score": min_score,
            "average_score": avg,
            "basic_stats": {
                "total_contacts": total,
                "matched_contacts": matched,
                "match_rate": (matched / total) if total else 0.0,
                "contacts_per_second": (total / elapsed) if elapsed > 0 else 0.0,
            },
        }

    def filter_contacts(
        self,
        contacts: List[Dict[str, Any]],
        requirements_input: str = "",
        min_score: float = 0.3,
        output_file: Optional[str] = None,
        detailed_output: bool = True,
        detailed: Optional[bool] = None,
        require_llm: bool = False,
    ):
        if detailed is not None:
            detailed_output = bool(detailed)
        if require_llm and not self.scoring_engine.is_llm_ready():
            raise RuntimeError("LLM未就绪，请检查 settings.json 的 llm 配置或 .env 变量")

        start = time.time()
        self.stats["start_time"] = datetime.now()
        contacts = contacts or []
        filtering_cfg = self.scoring_engine.config.get("filtering", {}) if isinstance(self.scoring_engine.config, dict) else {}
        show_progress = bool(filtering_cfg.get("llm_show_progress", True))
        llm_batch_size = filtering_cfg.get("llm_batch_size", 100)
        try:
            llm_batch_size = int(llm_batch_size)
        except Exception:
            llm_batch_size = 100
        llm_batch_size = max(1, llm_batch_size)
        total_input_contacts = len(contacts)
        contacts_batches = [
            contacts[idx:idx + llm_batch_size]
            for idx in range(0, len(contacts), llm_batch_size)
        ] if contacts else []
        contacts_for_profile = contacts_batches[0] if contacts_batches else []
        if show_progress:
            print(f"🧠 正在生成需求增强，联系人样本数: {len(contacts_for_profile)}", flush=True)
        requirement_profile = self.scoring_engine.build_requirement_profile(
            requirements_input=requirements_input,
            contacts=contacts_for_profile,
        )
        if show_progress:
            print("✅ 需求增强完成，开始逐条评分", flush=True)
        def score_one_batch(batch_contacts: List[Dict[str, Any]], batch_index: int, batch_total: int) -> List[ScoringResult]:
            if show_progress and batch_total > 1:
                print(f"📦 处理批次 {batch_index}/{batch_total}（{len(batch_contacts)} 人）", flush=True)
            if show_progress:
                print(f"🧩 单次多联系人评分中，单请求人数: {len(batch_contacts)}", flush=True)
            return self.scoring_engine.score_contacts_batch(
                contacts=batch_contacts,
                requirements_input=requirements_input,
                requirement_profile=requirement_profile,
            )
        scoring_results: List[ScoringResult] = []
        total_batches = len(contacts_batches)
        for batch_idx, batch_contacts in enumerate(contacts_batches, 1):
            scoring_results.extend(score_one_batch(batch_contacts, batch_idx, total_batches))

        filtered_results = [r for r in scoring_results if float(r.match_score) >= float(min_score)]
        filtered_results.sort(key=lambda r: r.match_score, reverse=True)
        output_contacts = [self._convert_result(r, detailed_output=detailed_output) for r in filtered_results]

        elapsed = time.time() - start
        self.stats["total_processed"] = len(scoring_results)
        self.stats["total_matched"] = len(filtered_results)
        self.stats["processing_time"] = elapsed
        self.stats["end_time"] = datetime.now()
        stats = self._build_stats(scoring_results, filtered_results, float(min_score), elapsed)
        stats["scoring_mode"] = "llm_resume_style"
        stats["requirements_input"] = requirements_input
        stats["requirement_profile"] = requirement_profile
        stats["llm_ready"] = self.scoring_engine.is_llm_ready()
        stats["workers"] = 1
        stats["input_contacts"] = total_input_contacts
        stats["scored_contacts"] = len(scoring_results)
        stats["llm_batch_size"] = llm_batch_size
        stats["batch_count"] = total_batches
        stats["llm_request_count"] = total_batches
        stats["truncated"] = False

        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump({"contacts": output_contacts, "stats": stats}, f, ensure_ascii=False, indent=2)
            stats["output_file"] = str(output_path)

        if detailed is not None:
            return output_contacts
        return output_contacts, stats

    def analyze_contact(self, contact: Dict[str, Any]) -> Dict[str, Any]:
        result = self.scoring_engine.score_contact(contact or {})
        return {
            "name": result.contact_name,
            "final_scores": {
                "job_score": result.job_score,
                "company_score": result.company_score,
                "location_score": result.location_score,
                "skill_score": result.skill_score,
                "match_score": result.match_score,
            },
            "original_contact": result.original_contact,
        }
