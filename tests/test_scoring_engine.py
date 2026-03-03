#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化的评分引擎单元测试
专注于核心评分逻辑的单元测试，提供详细的调试信息
"""

import pytest
import json
import logging
from pathlib import Path
from typing import Dict, List

# 设置详细日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加项目路径
import sys
sys.path.append(str(Path(__file__).parent.parent / "src"))

from filter.scoring_engine import ScoringEngine
from filter.contact_filter import ContactFilter

class TestScoringEngine:
    """评分引擎核心功能测试"""
    
    @pytest.fixture
    def scoring_engine(self):
        """创建评分引擎实例"""
        config_path = Path(__file__).parent.parent / "config" / "scoring_rules.yaml"
        return ScoringEngine(config_path=str(config_path))
    
    @pytest.fixture
    def sample_contacts(self):
        """测试用联系人数据"""
        return [
            {
                "name": "John Smith",
                "title": "General Manager - Smithfield Bioscience",
                "company": "Smithfield Foods",
                "location": "Virginia, USA",
                "industry": "Food Production"
            },
            {
                "name": "Jane Doe", 
                "title": "Software Engineer",
                "company": "Tech Corp",
                "location": "California, USA",
                "industry": "Technology"
            },
            {
                "name": "Bob Wilson",
                "title": "Director of Sales - Smithfield Foods", 
                "company": "Smithfield Foods",
                "location": "North Carolina, USA",
                "industry": "Food Production"
            }
        ]
    
    def test_general_manager_gets_high_score(self, scoring_engine, sample_contacts):
        """测试总经理职位获得高分"""
        contact = sample_contacts[0]  # John Smith - General Manager
        def fake_score_with_llm(normalized, requirements_input, requirement_profile):
            title = (normalized.get("title") or "").lower()
            company = (normalized.get("company") or "").lower()
            base = 20
            if "general manager" in title:
                base += 45
            if "smithfield" in company:
                base += 25
            return {
                "overall_score": min(100, base),
                "job_score": 90 if "general manager" in title else 40,
                "company_score": 88 if "smithfield" in company else 25,
                "location_score": 75,
                "skill_score": 70,
                "match_reasons": ["命中职位与公司特征"]
            }
        scoring_engine._score_with_llm = fake_score_with_llm
        
        logger.info(f"\n=== 测试总经理评分 ===")
        logger.info(f"联系人: {contact['name']}")
        logger.info(f"原始职位: {contact['title']}")
        logger.info(f"公司: {contact['company']}")
        
        result = scoring_engine.score_contact(contact, requirements_input="动物营养公司总经理")
        
        logger.info(f"职位评分: {result.job_score:.3f}")
        logger.info(f"公司评分: {result.company_score:.3f}")
        logger.info(f"总评分: {result.match_score:.3f}")
        
        # 验证原始数据保存
        assert result.original_contact is not None, "原始联系人数据应该被保存"
        assert result.original_contact['title'] == contact['title'], "原始标题应该被保存"
        assert result.original_contact['company'] == contact['company'], "原始公司应该被保存"
        
        # 验证评分逻辑
        assert result.job_score > 0.5, f"总经理职位应该获得高分，实际得分: {result.job_score}"
        assert result.company_score > 0.8, f"目标公司应该获得高分，实际得分: {result.company_score}"
        
    def test_unrelated_company_gets_low_score(self, scoring_engine, sample_contacts):
        """测试非目标公司获得低分"""
        contact = sample_contacts[1]  # Jane Doe - Tech Corp
        def fake_score_with_llm(normalized, requirements_input, requirement_profile):
            company = (normalized.get("company") or "").lower()
            return {
                "overall_score": 22 if "tech" in company else 55,
                "job_score": 30,
                "company_score": 20 if "tech" in company else 70,
                "location_score": 60,
                "skill_score": 50,
                "match_reasons": ["公司相关性较低"]
            }
        scoring_engine._score_with_llm = fake_score_with_llm
        
        logger.info(f"\n=== 测试非目标公司评分 ===")
        logger.info(f"联系人: {contact['name']}")
        logger.info(f"公司: {contact['company']}")
        
        result = scoring_engine.score_contact(contact, requirements_input="动物营养公司技术负责人")
        
        logger.info(f"公司评分: {result.company_score:.3f}")
        
        assert result.company_score < 0.3, f"非目标公司应该获得低分，实际得分: {result.company_score}"
        
    def test_company_in_title_handling(self, scoring_engine, sample_contacts):
        """测试职位中包含公司名称的处理"""
        contact = sample_contacts[2]  # Bob Wilson - Director of Sales - Smithfield Foods
        def fake_score_with_llm(normalized, requirements_input, requirement_profile):
            title = (normalized.get("title") or "").lower()
            return {
                "overall_score": 73,
                "job_score": 78 if "director" in title else 40,
                "company_score": 80,
                "location_score": 70,
                "skill_score": 66,
                "match_reasons": ["职位语义匹配"]
            }
        scoring_engine._score_with_llm = fake_score_with_llm
        
        logger.info(f"\n=== 测试职位中公司名称处理 ===")
        logger.info(f"联系人: {contact['name']}")
        logger.info(f"原始职位: {contact['title']}")
        
        result = scoring_engine.score_contact(contact, requirements_input="动物营养销售总监")
        
        logger.info(f"职位评分: {result.job_score:.3f}")
        
        # 验证职位评分合理（应该基于Director of Sales，而不是公司名称）
        assert result.job_score > 0.4, f"销售总监应该获得合理评分，实际得分: {result.job_score}"
        
    def test_batch_scoring_consistency(self, scoring_engine, sample_contacts):
        """测试批量评分与单个评分的一致性"""
        logger.info(f"\n=== 测试批量评分一致性 ===")
        def fake_score_with_llm(normalized, requirements_input, requirement_profile):
            title = (normalized.get("title") or "").lower()
            if "general manager" in title:
                score = 92
            elif "director" in title:
                score = 76
            else:
                score = 28
            return {
                "overall_score": score,
                "job_score": score,
                "company_score": score,
                "location_score": 60,
                "skill_score": 50,
                "match_reasons": ["批量一致性测试"]
            }
        scoring_engine._score_with_llm = fake_score_with_llm
        
        # 单个评分
        single_results = [scoring_engine.score_contact(contact, requirements_input="动物营养相关岗位") for contact in sample_contacts]
        
        # 批量评分
        batch_results = scoring_engine.score_contacts_batch(sample_contacts, requirements_input="动物营养相关岗位")
        
        assert len(single_results) == len(batch_results), "批量评分结果数量应该一致"
        
        for i, (single, batch) in enumerate(zip(single_results, batch_results)):
            logger.info(f"联系人 {i+1}: 单个评分={single.match_score:.3f}, 批量评分={batch.match_score:.3f}")
            
            # 允许小的浮点误差
            assert abs(single.match_score - batch.match_score) < 0.001, \
                f"联系人 {i+1} 评分不一致: 单个={single.match_score}, 批量={batch.match_score}"

class TestSmartFilterV3:
    """ContactFilter 集成测试"""
    
    @pytest.fixture
    def smart_filter(self):
        """创建ContactFilter实例"""
        config_path = Path(__file__).parent.parent / "config" / "scoring_rules.yaml"
        return ContactFilter(config_path=str(config_path))
    
    @pytest.fixture
    def real_contacts(self):
        """加载真实联系人数据（前20个）"""
        data_file = Path(__file__).parent.parent / "smithfield Foods_contacts.json"
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                all_contacts = json.load(f)
            return all_contacts[:20]  # 只取前20个进行快速测试
        except FileNotFoundError:
            logger.warning(f"数据文件未找到: {data_file}")
            return []
    
    def test_filter_output_format(self, smart_filter, real_contacts):
        """测试筛选输出格式"""
        if not real_contacts:
            pytest.skip("没有真实数据文件")
            
        logger.info(f"\n=== 测试筛选输出格式 ===")
        logger.info(f"输入联系人数量: {len(real_contacts)}")
        
        # 使用较低的阈值确保有结果
        results = smart_filter.filter_contacts(real_contacts, min_score=0.0, detailed=True)
        
        logger.info(f"筛选结果数量: {len(results)}")
        
        assert isinstance(results, list), "结果应该是列表"
        
        if results:
            first_result = results[0]
            logger.info(f"第一个结果示例: {json.dumps(first_result, indent=2, ensure_ascii=False)}")
            
            # 验证必要字段
            required_fields = ['name', 'title', 'company', 'location', 'match_score']
            for field in required_fields:
                assert field in first_result, f"缺少必要字段: {field}"
                
            # 验证原始数据不是N/A
            if first_result['title'] == 'N/A':
                logger.warning(f"联系人 {first_result['name']} 的title显示为N/A")
            if first_result['company'] == 'N/A':
                logger.warning(f"联系人 {first_result['name']} 的company显示为N/A")
                
    def test_score_distribution_analysis(self, smart_filter, real_contacts):
        """分析评分分布"""
        if not real_contacts:
            pytest.skip("没有真实数据文件")
            
        logger.info(f"\n=== 评分分布分析 ===")
        
        # 获取所有结果（不设置最低分数）
        all_results = smart_filter.filter_contacts(real_contacts, min_score=0.0, detailed=True)
        
        if not all_results:
            logger.error("没有获得任何评分结果")
            return
            
        scores = [r['match_score'] for r in all_results]
        scores.sort(reverse=True)
        
        logger.info(f"总联系人数: {len(scores)}")
        logger.info(f"最高分: {max(scores):.3f}")
        logger.info(f"最低分: {min(scores):.3f}")
        logger.info(f"平均分: {sum(scores)/len(scores):.3f}")
        
        # 分析不同阈值下的筛选结果
        thresholds = [0.1, 0.3, 0.5, 0.7]
        for threshold in thresholds:
            count = len([s for s in scores if s >= threshold])
            logger.info(f"评分 >= {threshold}: {count} 个联系人 ({count/len(scores)*100:.1f}%)")
            
        # 显示前5名详细信息
        logger.info("\n前5名联系人详细信息:")
        top_5 = sorted(all_results, key=lambda x: x['match_score'], reverse=True)[:5]
        for i, contact in enumerate(top_5, 1):
            logger.info(f"{i}. {contact['name']} - 总分: {contact['match_score']:.3f}")
            logger.info(f"   职位: {contact['title']} (评分: {contact['job_score']:.3f})")
            logger.info(f"   公司: {contact['company']} (评分: {contact['company_score']:.3f})")
            logger.info("")

def run_debug_tests():
    """运行调试测试"""
    logger.info("开始运行优化的评分引擎测试...")
    
    # 运行pytest
    import subprocess
    import sys
    
    test_file = __file__
    cmd = [sys.executable, "-m", "pytest", test_file, "-v", "-s"]
    
    logger.info(f"执行命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    print("STDOUT:")
    print(result.stdout)
    print("\nSTDERR:")
    print(result.stderr)
    print(f"\n返回码: {result.returncode}")

if __name__ == "__main__":
    run_debug_tests()
