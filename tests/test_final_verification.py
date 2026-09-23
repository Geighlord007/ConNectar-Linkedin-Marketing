#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终验证测试 - 确认所有问题已修复
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

from filter.contact_filter import ContactFilter

def test_final_verification():
    """最终验证测试"""
    logger.info("=== 最终验证测试 ===")
    
    # 加载真实数据
    data_file = Path(__file__).parent.parent / "data" / "raw" / "smithfield Foods_contacts.json"
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            all_contacts = json.load(f)
        
        logger.info(f"加载了 {len(all_contacts)} 个联系人")
        
        # 初始化筛选器
        config_path = str(Path(__file__).parent.parent / "config" / "scoring_rules.yaml")
        smart_filter = ContactFilter(config_path=config_path)
        
        # 测试不同阈值的筛选
        test_thresholds = [0.3, 0.5, 0.7]
        
        for threshold in test_thresholds:
            logger.info(f"\n--- 测试阈值 {threshold} ---")
            
            results = smart_filter.filter_contacts(all_contacts, min_score=threshold)
            
            if results:
                # 处理可能的嵌套列表格式
                if isinstance(results[0], list):
                    actual_results = results[0]
                else:
                    actual_results = results
                    
                logger.info(f"筛选结果: {len(actual_results)} 个联系人通过")
                
                # 检查前5个结果的数据完整性
                for i, contact in enumerate(actual_results[:5], 1):
                    name = contact.get('name', 'Unknown')
                    title = contact.get('title', 'N/A')
                    company = contact.get('company', 'N/A')
                    location = contact.get('location', 'N/A')
                    score = contact.get('match_score', 0)
                    
                    logger.info(f"  {i}. {name} (评分: {score:.3f})")
                    logger.info(f"     职位: {title}")
                    logger.info(f"     公司: {company}")
                    logger.info(f"     位置: {location}")
                    
                    # 检查N/A字段
                    na_fields = []
                    if title == 'N/A':
                        na_fields.append('title')
                    if company == 'N/A':
                        na_fields.append('company')
                    if location == 'N/A':
                        na_fields.append('location')
                    
                    if na_fields:
                        logger.warning(f"     ⚠️  发现N/A字段: {na_fields}")
                    else:
                        logger.info(f"     ✅ 数据完整")
                
                # 统计N/A字段的总体情况
                total_na_title = sum(1 for c in actual_results if c.get('title') == 'N/A')
                total_na_company = sum(1 for c in actual_results if c.get('company') == 'N/A')
                total_na_location = sum(1 for c in actual_results if c.get('location') == 'N/A')
                
                logger.info(f"\n  数据完整性统计:")
                logger.info(f"    N/A职位: {total_na_title}/{len(actual_results)} ({total_na_title/len(actual_results)*100:.1f}%)")
                logger.info(f"    N/A公司: {total_na_company}/{len(actual_results)} ({total_na_company/len(actual_results)*100:.1f}%)")
                logger.info(f"    N/A位置: {total_na_location}/{len(actual_results)} ({total_na_location/len(actual_results)*100:.1f}%)")
                
                # 评估修复效果
                if total_na_title + total_na_company + total_na_location == 0:
                    logger.info(f"    🎉 完美！所有字段都有数据")
                elif (total_na_title + total_na_company + total_na_location) < len(actual_results) * 0.1:
                    logger.info(f"    ✅ 很好！N/A字段比例很低")
                else:
                    logger.warning(f"    ⚠️  仍有较多N/A字段")
            else:
                logger.warning(f"  没有联系人通过阈值 {threshold}")
        
        # 测试特定联系人
        logger.info(f"\n--- 测试特定联系人 ---")
        test_names = ["Elizabeth Cooper", "Leanne Brooks", "Lindsay Barnaba"]
        
        for name in test_names:
            # 查找包含该姓名的联系人
            matching_contacts = [c for c in all_contacts if name.lower() in c.get('name', '').lower()]
            
            if matching_contacts:
                contact = matching_contacts[0]
                logger.info(f"\n测试联系人: {contact.get('name', 'Unknown')}")
                logger.info(f"  原始职位: {contact.get('title', '')}")
                logger.info(f"  原始公司: {contact.get('company', '')}")
                logger.info(f"  原始位置: {contact.get('location', '')}")
                
                # 单独筛选
                results = smart_filter.filter_contacts([contact], min_score=0.0)
                
                if results:
                    # 处理可能的嵌套列表格式
                    if isinstance(results[0], list):
                        result = results[0][0] if results[0] else None
                    else:
                        result = results[0]
                        
                        if result:
                            logger.info(f"  筛选后职位: {result.get('title', 'N/A')}")
                            logger.info(f"  筛选后公司: {result.get('company', 'N/A')}")
                            logger.info(f"  筛选后位置: {result.get('location', 'N/A')}")
                            logger.info(f"  评分: {result.get('match_score', 0):.3f}")
                            
                            # 验证数据一致性
                            title_match = contact.get('title', '') == result.get('title', '')
                            company_match = contact.get('company', '') == result.get('company', '')
                            location_match = contact.get('location', '') == result.get('location', '')
                            
                            if title_match and company_match and location_match:
                                logger.info(f"  ✅ 数据传递完全正确")
                            else:
                                logger.error(f"  ❌ 数据传递有问题")
                                logger.error(f"    职位匹配: {title_match}")
                                logger.error(f"    公司匹配: {company_match}")
                                logger.error(f"    位置匹配: {location_match}")
                else:
                    logger.warning(f"  ⚠️  没有筛选结果")
            else:
                logger.warning(f"未找到联系人: {name}")
        
        logger.info(f"\n=== 最终验证完成 ===")
        logger.info(f"如果看到大量✅标记，说明原始数据传递问题已完全修复！")
        
    except FileNotFoundError:
        logger.error(f"数据文件未找到: {data_file}")
    except Exception as e:
        logger.error(f"测试过程中出错: {e}")

if __name__ == "__main__":
    test_final_verification()
