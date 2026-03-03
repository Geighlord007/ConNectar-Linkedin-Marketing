#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试和修复原始数据传递问题
"""

import json
import logging
from pathlib import Path
from typing import Dict, List

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 添加项目路径
import sys
sys.path.append(str(Path(__file__).parent.parent / "src"))

from filter.scoring_engine import ScoringEngine
from filter.contact_filter import ContactFilter

def test_original_data_preservation():
    """测试原始数据保存"""
    logger.info("=== 测试原始数据保存 ===")
    
    # 创建测试数据
    test_contact = {
        "name": "Test Person",
        "title": "Senior Manager", 
        "company": "Smithfield Foods",
        "location": "Virginia, USA",
        "industry": "Food Production"
    }
    
    logger.info(f"原始测试联系人: {json.dumps(test_contact, indent=2)}")
    
    # 测试评分引擎
    config_path = str(Path(__file__).parent.parent / "config" / "scoring_rules.yaml")
    scoring_engine = ScoringEngine(config_path=config_path)
    
    logger.info("\n--- 测试评分引擎 ---")
    result = scoring_engine.score_contact(test_contact)
    
    logger.info(f"评分结果:")
    logger.info(f"  联系人姓名: {result.contact_name}")
    logger.info(f"  总评分: {result.match_score:.3f}")
    logger.info(f"  原始数据是否保存: {result.original_contact is not None}")
    
    if result.original_contact:
        logger.info(f"  保存的原始数据: {json.dumps(result.original_contact, indent=2)}")
        
        # 验证数据完整性
        for key in ['name', 'title', 'company', 'location']:
            original_value = test_contact.get(key, '')
            preserved_value = result.original_contact.get(key, '')
            match = original_value == preserved_value
            logger.info(f"  {key}: 原始='{original_value}' 保存='{preserved_value}' 匹配={match}")
            if not match:
                logger.error(f"    ❌ {key} 字段数据不匹配！")
    else:
        logger.error("  ❌ 原始数据未保存！")
    
    # 测试SmartFilterV3
    logger.info("\n--- 测试SmartFilterV3 ---")
    smart_filter = ContactFilter(config_path=config_path)
    
    filter_results = smart_filter.filter_contacts([test_contact], min_score=0.0)
    
    if filter_results:
        # 处理可能的嵌套列表格式
        if isinstance(filter_results[0], list):
            first_result = filter_results[0][0] if filter_results[0] else None
        else:
            first_result = filter_results[0]
            
        if first_result:
            logger.info(f"筛选结果:")
            logger.info(f"  姓名: {first_result.get('name', 'N/A')}")
            logger.info(f"  职位: {first_result.get('title', 'N/A')}")
            logger.info(f"  公司: {first_result.get('company', 'N/A')}")
            logger.info(f"  位置: {first_result.get('location', 'N/A')}")
            logger.info(f"  总评分: {first_result.get('match_score', 0):.3f}")
            
            # 检查N/A问题
            na_fields = []
            for field in ['title', 'company', 'location']:
                if first_result.get(field) == 'N/A':
                    na_fields.append(field)
            
            if na_fields:
                logger.error(f"  ❌ 发现N/A字段: {na_fields}")
                logger.error("  这表明原始数据没有正确传递到输出格式")
            else:
                logger.info("  ✅ 所有字段都正确显示")
        else:
            logger.error("  ❌ 筛选结果为空")
    else:
        logger.error("  ❌ 没有筛选结果")

def test_real_data_sample():
    """测试真实数据样本"""
    logger.info("\n=== 测试真实数据样本 ===")
    
    # 加载真实数据
    data_file = Path(__file__).parent.parent / "data" / "raw" / "smithfield Foods_contacts.json"
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            all_contacts = json.load(f)
        
        # 取前3个联系人进行测试
        test_contacts = all_contacts[:3]
        logger.info(f"加载了 {len(test_contacts)} 个测试联系人")
        
        config_path = str(Path(__file__).parent.parent / "config" / "scoring_rules.yaml")
        smart_filter = ContactFilter(config_path=config_path)
        
        # 逐个测试
        for i, contact in enumerate(test_contacts, 1):
            logger.info(f"\n--- 测试联系人 {i}: {contact.get('name', 'Unknown')} ---")
            logger.info(f"原始数据:")
            logger.info(f"  职位: '{contact.get('title', '')}'")
            logger.info(f"  公司: '{contact.get('company', '')}'")
            logger.info(f"  位置: '{contact.get('location', '')}'")
            
            # 筛选单个联系人
            results = smart_filter.filter_contacts([contact], min_score=0.0)
            
            if results:
                # 处理可能的嵌套列表格式
                if isinstance(results[0], list):
                    result = results[0][0] if results[0] else None
                else:
                    result = results[0]
                    
                if result:
                    logger.info(f"筛选结果:")
                    logger.info(f"  职位: '{result.get('title', 'N/A')}'")
                    logger.info(f"  公司: '{result.get('company', 'N/A')}'")
                    logger.info(f"  位置: '{result.get('location', 'N/A')}'")
                    logger.info(f"  评分: {result.get('match_score', 0):.3f}")
                    
                    # 检查数据一致性
                    title_match = contact.get('title', '') == result.get('title', '')
                    company_match = contact.get('company', '') == result.get('company', '')
                    location_match = contact.get('location', '') == result.get('location', '')
                    
                    logger.info(f"数据一致性检查:")
                    logger.info(f"  职位匹配: {title_match}")
                    logger.info(f"  公司匹配: {company_match}")
                    logger.info(f"  位置匹配: {location_match}")
                    
                    if not (title_match and company_match and location_match):
                        logger.error(f"  ❌ 数据不一致！")
                    else:
                        logger.info(f"  ✅ 数据一致")
                else:
                    logger.warning(f"  ⚠️  筛选结果为空")
            else:
                logger.warning(f"  ⚠️  没有筛选结果")
                
    except FileNotFoundError:
        logger.error(f"数据文件未找到: {data_file}")
    except Exception as e:
        logger.error(f"测试真实数据时出错: {e}")

def main():
    """主函数"""
    logger.info("开始原始数据传递问题诊断...")
    
    # 测试1: 基础原始数据保存
    test_original_data_preservation()
    
    # 测试2: 真实数据样本
    test_real_data_sample()
    
    logger.info("\n=== 诊断完成 ===")
    logger.info("如果发现N/A字段问题，说明需要修复_convert_to_output_format方法")

if __name__ == "__main__":
    main()
