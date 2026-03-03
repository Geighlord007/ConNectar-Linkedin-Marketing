#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能筛选器单元测试
专门用于调试当前筛选问题
"""

import pytest
import json
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.filter.contact_filter import ContactFilter
from src.filter.scoring_engine import ScoringResult
from src.cli import LinkedInMarketingCLI

class TestSmartFilterV3:
    """SmartFilterV3 测试类"""
    
    @pytest.fixture
    def filter_instance(self):
        """创建筛选器实例"""
        return ContactFilter()
    
    @pytest.fixture
    def sample_contacts(self):
        """样本联系人数据"""
        return [
            {
                "name": "Elizabeth Cooper, PhD",
                "title": "Current: Nutritionist",
                "company": "Smithfield Foods",
                "location": "",
                "linkedin_url": "https://www.linkedin.com/in/elizabeth-cooper",
                "search_keyword": "smithfield Foods",
                "extracted_at": "2025-08-06 11:32:30"
            },
            {
                "name": "Corey Conlin",
                "title": "Camp Counselor",
                "company": "Smithfield YMCA",
                "location": "United States",
                "linkedin_url": "https://www.linkedin.com/in/corey-conlin-07b079352",
                "search_keyword": "smithfield",
                "extracted_at": "2025-08-06 07:23:42"
            },
            {
                "name": "Brian Smith",
                "title": "Current: Founder - President - Smithfield Markets",
                "company": "Smithfield Markets d/b/a Barnstable Market - Peterson's...",
                "location": "Cotuit, MA",
                "linkedin_url": "https://www.linkedin.com/in/brian-smith-438224233",
                "search_keyword": "smithfield",
                "extracted_at": "2025-08-06 07:23:42"
            }
        ]
    
    def test_elizabeth_cooper_scoring(self, filter_instance, sample_contacts):
        """测试Elizabeth Cooper的评分过程"""
        elizabeth = sample_contacts[0]
        
        # 直接测试评分引擎
        result = filter_instance.scoring_engine.score_contact(elizabeth)
        
        print(f"\n=== Elizabeth Cooper 评分调试 ===")
        print(f"联系人姓名: {result.contact_name}")
        print(f"原始联系人数据: {result.original_contact}")
        print(f"职位分数: {result.job_score}")
        print(f"公司分数: {result.company_score}")
        print(f"总分: {result.match_score}")
        
        # 验证原始数据是否正确保存
        assert result.original_contact is not None, "原始联系人数据应该被保存"
        assert result.original_contact.get('title') == "Current: Nutritionist", "原始标题应该被保存"
        assert result.original_contact.get('company') == "Smithfield Foods", "原始公司应该被保存"
        
        return result
    
    def test_filter_contacts_output_format(self, filter_instance, sample_contacts):
        """测试筛选输出格式"""
        # 执行筛选
        results, stats = filter_instance.filter_contacts(
            sample_contacts,
            min_score=0.5
        )
        
        print(f"\n=== 筛选结果调试 ===")
        print(f"筛选到的联系人数量: {len(results)}")
        
        for i, contact in enumerate(results):
            print(f"\n联系人 {i+1}:")
            print(f"  姓名: {contact.get('name', 'N/A')}")
            print(f"  标题: {contact.get('title', 'N/A')}")
            print(f"  公司: {contact.get('company', 'N/A')}")
            print(f"  位置: {contact.get('location', 'N/A')}")
            print(f"  总分: {contact.get('match_score', 'N/A')}")
        
        # 验证输出格式
        if results:
            first_result = results[0]
            assert 'name' in first_result, "结果应包含姓名"
            assert 'title' in first_result, "结果应包含标题"
            assert 'company' in first_result, "结果应包含公司"
            assert 'match_score' in first_result, "结果应包含匹配分数"
            
            # 检查是否还有N/A值
            if first_result.get('title') == 'N/A':
                print(f"警告: 标题显示为N/A，需要调试原始数据传递")
            if first_result.get('company') == 'N/A':
                print(f"警告: 公司显示为N/A，需要调试原始数据传递")
        
        return results, stats
    
    def test_scoring_threshold_analysis(self, filter_instance, sample_contacts):
        """分析不同分数阈值下的筛选结果"""
        thresholds = [0.1, 0.3, 0.5, 0.7, 0.9]
        
        print(f"\n=== 分数阈值分析 ===")
        for threshold in thresholds:
            results, stats = filter_instance.filter_contacts(
                sample_contacts,
                min_score=threshold
            )
            print(f"阈值 {threshold}: {len(results)} 个联系人通过筛选")
            
            if results:
                scores = [r.get('match_score', 0) for r in results]
                print(f"  分数范围: {min(scores):.3f} - {max(scores):.3f}")
    
    def test_raw_data_loading(self):
        """测试原始数据加载"""
        raw_file = project_root / "data" / "raw" / "smithfield_contacts.json"
        
        if raw_file.exists():
            with open(raw_file, 'r', encoding='utf-8') as f:
                contacts = json.load(f)
            
            print(f"\n=== 原始数据分析 ===")
            print(f"总联系人数: {len(contacts)}")
            
            # 查找Elizabeth Cooper
            elizabeth = None
            for contact in contacts:
                if "Elizabeth Cooper" in contact.get('name', ''):
                    elizabeth = contact
                    break
            
            if elizabeth:
                print(f"\n找到Elizabeth Cooper:")
                for key, value in elizabeth.items():
                    print(f"  {key}: {value}")
            else:
                print("未找到Elizabeth Cooper")
            
            return contacts
        else:
            print(f"原始数据文件不存在: {raw_file}")
            return []


class TestCliLlmSimple:
    def test_get_filter_mode(self):
        cli = LinkedInMarketingCLI()
        cli._load_scoring_rules = lambda: {"filtering": {"mode": "llm_simple"}}
        assert cli._get_filter_mode() == "llm_simple"
        cli._load_scoring_rules = lambda: {"filtering": {"mode": "invalid_mode"}}
        assert cli._get_filter_mode() == "hybrid"

    def test_filter_contacts_with_llm_simple(self, monkeypatch):
        class FakeLLMClient:
            def is_enabled(self):
                return True

            def classify_contact_tags(self, contact_info, filter_criteria):
                title = (contact_info.get("title") or "").lower()
                if "director" in title:
                    score = 0.92
                elif "manager" in title:
                    score = 0.72
                else:
                    score = 0.2
                return {
                    "tags": ["test"],
                    "match_score": score,
                    "match_reasons": [f"criteria={filter_criteria}"],
                    "industry_category": "food",
                    "seniority_level": "senior"
                }

        monkeypatch.setattr("src.utils.llm_client.LLMClient", FakeLLMClient)
        cli = LinkedInMarketingCLI()
        cli._load_scoring_rules = lambda: {"filtering": {"llm_simple_workers": 1}}
        contacts = [
            {"name": "A", "title": "Sales Director", "company": "X", "location": "US"},
            {"name": "B", "title": "Product Manager", "company": "Y", "location": "US"},
            {"name": "C", "title": "Intern", "company": "Z", "location": "US"},
        ]
        results, stats = cli._filter_contacts_with_llm_simple(
            contacts_data=contacts,
            requirements_input="食品行业销售负责人",
            min_score=0.7
        )
        assert stats["scoring_mode"] == "llm_simple"
        assert stats["evaluated_contacts"] == 3
        assert stats["truncated"] is False
        assert len(results) == 2
        assert results[0]["name"] == "A"
        assert results[0]["match_score"] >= results[1]["match_score"]
        assert results[0]["scoring_mode"] == "llm_simple"

    def test_filter_contacts_with_llm_simple_optimum_small_sample(self, monkeypatch):
        class RubricLLMClient:
            def is_enabled(self):
                return True

            def classify_contact_tags(self, contact_info, filter_criteria):
                title = (contact_info.get("title") or "").lower()
                company = (contact_info.get("company") or "").lower()
                location = (contact_info.get("location") or "").lower()
                score = 0.05
                reasons = []

                if any(k in title for k in ["director", "head", "vp", "vice president"]):
                    score += 0.55
                    reasons.append("职位层级匹配（director/head/vp）")
                elif any(k in title for k in ["manager", "lead"]):
                    score += 0.35
                    reasons.append("职位相关（manager/lead）")
                elif any(k in title for k in ["intern", "assistant", "coordinator"]):
                    score += 0.02
                    reasons.append("职位较初级")
                else:
                    score += 0.15
                    reasons.append("职位信息中性匹配")

                if "optimum" in company or "nutrition" in company:
                    score += 0.25
                    reasons.append("公司/行业关键词匹配（optimum/nutrition）")

                if any(k in location for k in ["us", "united states", "canada", "north america"]):
                    score += 0.10
                    reasons.append("地域匹配（北美）")

                score = max(0.0, min(1.0, score))
                return {
                    "tags": ["small_sample_demo"],
                    "match_score": score,
                    "match_reasons": reasons + [f"criteria={filter_criteria}"],
                    "industry_category": "nutrition",
                    "seniority_level": "senior" if score >= 0.7 else "mid"
                }

        monkeypatch.setattr("src.utils.llm_client.LLMClient", RubricLLMClient)
        cli = LinkedInMarketingCLI()
        cli._load_scoring_rules = lambda: {"filtering": {"llm_simple_max_contacts": 12}}
        data_path = project_root / "data" / "raw" / "Optimum_Nutrition_contacts.json"
        with open(data_path, "r", encoding="utf-8") as f:
            contacts = json.load(f)
        sample = contacts[:12]

        results, stats = cli._filter_contacts_with_llm_simple(
            contacts_data=sample,
            requirements_input="北美营养补剂行业，目标职位：研发总监、产品总监、BD负责人，优先Optimum Nutrition",
            min_score=0.4
        )
        assert stats["scoring_mode"] == "llm_simple"
        assert stats["evaluated_contacts"] == 12
        assert len(results) >= 1
        assert results[0]["match_score"] >= results[-1]["match_score"]
        print("\n=== 小样本打分预览（Top 5）===")
        for idx, row in enumerate(results[:5], 1):
            print(f"{idx}. {row.get('name', '')} | {row.get('title', '')} | {row.get('company', '')}")
            print(f"   score={row.get('match_score', 0):.2f} reasons={row.get('match_reasons', [])}")

    def test_filter_contacts_with_llm_simple_disabled(self, monkeypatch):
        class DisabledLLMClient:
            def is_enabled(self):
                return False

        monkeypatch.setattr("src.utils.llm_client.LLMClient", DisabledLLMClient)
        cli = LinkedInMarketingCLI()
        with pytest.raises(RuntimeError):
            cli._filter_contacts_with_llm_simple(
                contacts_data=[{"name": "A", "title": "Director", "company": "X", "location": "US"}],
                requirements_input="测试",
                min_score=0.5
            )

    def test_filter_contacts_with_llm_simple_batch_mode(self, monkeypatch):
        class BatchLLMClient:
            single_calls = 0
            batch_calls = 0

            def is_enabled(self):
                return True

            def classify_contact_tags(self, contact_info, filter_criteria):
                BatchLLMClient.single_calls += 1
                return {
                    "tags": ["single"],
                    "match_score": 0.1,
                    "match_reasons": [f"criteria={filter_criteria}"],
                    "industry_category": "test",
                    "seniority_level": "mid"
                }

            def classify_contacts_tags_batch(self, contacts_info, filter_criteria):
                BatchLLMClient.batch_calls += 1
                result = []
                for item in contacts_info:
                    title = (item.get("title") or "").lower()
                    score = 0.9 if "director" in title else 0.6
                    result.append({
                        "tags": ["batch"],
                        "match_score": score,
                        "match_reasons": [f"criteria={filter_criteria}"],
                        "industry_category": "test",
                        "seniority_level": "senior" if score >= 0.8 else "mid"
                    })
                return result

        monkeypatch.setattr("src.utils.llm_client.LLMClient", BatchLLMClient)
        cli = LinkedInMarketingCLI()
        cli._load_scoring_rules = lambda: {"filtering": {"llm_simple_batch_size": 2, "llm_simple_workers": 1}}
        contacts = [
            {"name": "A", "title": "Sales Director", "company": "X", "location": "US"},
            {"name": "B", "title": "Product Manager", "company": "Y", "location": "US"},
            {"name": "C", "title": "Intern", "company": "Z", "location": "US"},
            {"name": "D", "title": "Marketing Director", "company": "K", "location": "US"},
            {"name": "E", "title": "BD Lead", "company": "N", "location": "US"},
        ]
        results, stats = cli._filter_contacts_with_llm_simple(
            contacts_data=contacts,
            requirements_input="食品行业销售负责人",
            min_score=0.6
        )
        assert stats["evaluated_contacts"] == 5
        assert stats["llm_batch_size"] == 2
        assert BatchLLMClient.batch_calls == 3
        assert BatchLLMClient.single_calls == 0
        assert len(results) == 5

def load_sample_data():
    """加载样本数据"""
    data_file = Path(__file__).parent.parent / "data" / "raw" / "smithfield Foods_contacts.json"
    
    if not data_file.exists():
        print(f"数据文件不存在: {data_file}")
        return []
    
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 取前100个联系人进行测试，确保包含Elizabeth Cooper
    return data[:100]

if __name__ == "__main__":
    # 创建测试实例
    test_instance = TestSmartFilterV3()
    
    # 获取样本数据
    sample_data = load_sample_data()
    
    if not sample_data:
        # 如果无法加载外部数据，使用内置样本数据
        sample_data = [
            {
                "name": "Elizabeth Cooper, PhD",
                "title": "Current: Nutritionist",
                "company": "Smithfield Foods",
                "location": "",
                "linkedin_url": "https://www.linkedin.com/in/elizabeth-cooper",
                "search_keyword": "smithfield Foods",
                "extracted_at": "2025-08-06 11:32:30"
            },
            {
                "name": "Corey Conlin",
                "title": "Camp Counselor",
                "company": "Smithfield YMCA",
                "location": "United States",
                "linkedin_url": "https://www.linkedin.com/in/corey-conlin-07b079352",
                "search_keyword": "smithfield",
                "extracted_at": "2025-08-06 07:23:42"
            },
            {
                "name": "Brian Smith",
                "title": "Current: Founder - President - Smithfield Markets",
                "company": "Smithfield Markets d/b/a Barnstable Market - Peterson's...",
                "location": "Cotuit, MA",
                "linkedin_url": "https://www.linkedin.com/in/brian-smith-438224233",
                "search_keyword": "smithfield",
                "extracted_at": "2025-08-06 07:23:42"
            }
        ]
    
    # 创建筛选器实例，使用绝对路径
    config_path = Path(__file__).parent.parent / "config" / "scoring_rules.yaml"
    filter_inst = ContactFilter(str(config_path))
    
    print("开始调试测试...")
    
    # 运行调试测试
    print("\n=== 开始Elizabeth Cooper评分测试 ===")
    
    # 查找Elizabeth Cooper
    elizabeth = None
    for contact in sample_data:
        if "Elizabeth Cooper" in contact.get('name', ''):
            elizabeth = contact
            break
    
    print(f"\n=== Elizabeth Cooper 评分调试 ===")
    if elizabeth:
        print(f"找到Elizabeth Cooper: {elizabeth['name']}")
        print(f"原始数据: {elizabeth}")
        
        # 测试评分过程
        result = filter_inst.scoring_engine.score_contact(elizabeth)
        
        print(f"\n评分结果:")
        print(f"联系人姓名: {result.contact_name}")
        print(f"职位分数: {result.job_score}")
        print(f"公司分数: {result.company_score}")
        print(f"总分: {result.match_score}")
        
        # 检查原始数据保存
        if hasattr(result, 'original_contact') and result.original_contact:
            print(f"\n原始联系人数据已保存:")
            print(f"  标题: {result.original_contact.get('title')}")
            print(f"  公司: {result.original_contact.get('company')}")
            print(f"  位置: {result.original_contact.get('location')}")
            
            # 验证数据完整性
            assert result.original_contact.get('title') == "Current: Nutritionist", f"标题不匹配: {result.original_contact.get('title')}"
            assert result.original_contact.get('company') == "Smithfield Foods", f"公司不匹配: {result.original_contact.get('company')}"
            print("✓ 原始数据验证通过")
        else:
            print("✗ 原始联系人数据未保存")
    else:
        print("未找到Elizabeth Cooper")
        print(f"可用联系人: {[c.get('name', 'Unknown') for c in sample_data[:5]]}")
    
    print("\n=== 开始输出格式转换测试 ===")
    test_instance.test_filter_contacts_output_format(filter_inst, sample_data)
    
    print("\n=== 开始分数阈值分析测试 ===")
    test_instance.test_scoring_threshold_analysis(filter_inst, sample_data)
    
    print("\n=== 开始原始数据加载测试 ===")
    test_instance.test_raw_data_loading()
    
    print("\n=== 所有调试测试完成 ===")
