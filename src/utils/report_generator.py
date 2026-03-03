#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析报告生成器
Analysis Report Generator

用于生成筛选结果的详细分析报告
"""

import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import Counter
import statistics

class FilterReportGenerator:
    """筛选结果分析报告生成器"""
    
    def __init__(self, project_root: str = None):
        """初始化报告生成器
        
        Args:
            project_root: 项目根目录
        """
        self.project_root = project_root or os.getcwd()
        self.reports_dir = os.path.join(self.project_root, 'data', 'reports')
        
        # 确保报告目录存在
        os.makedirs(self.reports_dir, exist_ok=True)
    
    def generate_filter_report(self, 
                             filtered_contacts: List[Dict[str, Any]], 
                             original_count: int = None,
                             min_score: float = None,
                             filter_config: Dict = None,
                             processing_time: float = None) -> str:
        """生成筛选分析报告
        
        Args:
            filtered_contacts: 筛选后的联系人列表
            original_count: 原始联系人数量
            min_score: 最低分数阈值
            filter_config: 筛选配置信息
            processing_time: 处理时间（秒）
            
        Returns:
            报告文件路径
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_filename = f'filter_analysis_report_{timestamp}.md'
        report_path = os.path.join(self.reports_dir, report_filename)
        
        # 分析数据
        analysis = self._analyze_filtered_contacts(filtered_contacts)
        
        # 生成报告内容
        report_content = self._generate_report_content(
            analysis=analysis,
            filtered_contacts=filtered_contacts,
            original_count=original_count,
            min_score=min_score,
            filter_config=filter_config,
            processing_time=processing_time,
            timestamp=timestamp
        )
        
        # 保存报告
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        return report_path
    
    def _analyze_filtered_contacts(self, contacts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析筛选后的联系人数据
        
        Args:
            contacts: 联系人列表
            
        Returns:
            分析结果字典
        """
        if not contacts:
            return {
                'total_count': 0,
                'score_stats': {},
                'title_distribution': {},
                'company_distribution': {},
                'location_distribution': {},
                'score_distribution': {}
            }
        
        # 提取分数
        scores = []
        for contact in contacts:
            score = contact.get('total_score') or contact.get('match_score') or contact.get('job_score', 0)
            scores.append(float(score))
        
        # 分数统计
        score_stats = {
            'mean': statistics.mean(scores) if scores else 0,
            'median': statistics.median(scores) if scores else 0,
            'min': min(scores) if scores else 0,
            'max': max(scores) if scores else 0,
            'std': statistics.stdev(scores) if len(scores) > 1 else 0
        }
        
        # 职位分布
        titles = [contact.get('title', 'Unknown') for contact in contacts]
        title_distribution = dict(Counter(titles).most_common(10))
        
        # 公司分布
        companies = [contact.get('company', 'Unknown') for contact in contacts]
        company_distribution = dict(Counter(companies).most_common(10))
        
        # 地区分布
        locations = [contact.get('location', 'Unknown') for contact in contacts]
        location_distribution = dict(Counter(locations).most_common(10))
        
        # 分数区间分布
        score_ranges = {
            '0.9-1.0 (优秀)': len([s for s in scores if 0.9 <= s <= 1.0]),
            '0.7-0.9 (良好)': len([s for s in scores if 0.7 <= s < 0.9]),
            '0.5-0.7 (中等)': len([s for s in scores if 0.5 <= s < 0.7]),
            '0.3-0.5 (一般)': len([s for s in scores if 0.3 <= s < 0.5]),
            '0.0-0.3 (较低)': len([s for s in scores if 0.0 <= s < 0.3])
        }
        
        return {
            'total_count': len(contacts),
            'score_stats': score_stats,
            'title_distribution': title_distribution,
            'company_distribution': company_distribution,
            'location_distribution': location_distribution,
            'score_distribution': score_ranges
        }
    
    def _generate_report_content(self, 
                               analysis: Dict[str, Any],
                               filtered_contacts: List[Dict[str, Any]],
                               original_count: int = None,
                               min_score: float = None,
                               filter_config: Dict = None,
                               processing_time: float = None,
                               timestamp: str = None) -> str:
        """生成报告内容
        
        Args:
            analysis: 分析结果
            filtered_contacts: 筛选后的联系人
            original_count: 原始数量
            min_score: 最低分数
            filter_config: 筛选配置
            processing_time: 处理时间
            timestamp: 时间戳
            
        Returns:
            报告内容字符串
        """
        report_lines = []
        
        # 报告标题
        report_lines.append(f"# LinkedIn联系人筛选分析报告")
        report_lines.append(f"")
        report_lines.append(f"**生成时间**: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")
        report_lines.append(f"**报告ID**: {timestamp}")
        report_lines.append(f"")
        
        # 筛选概览
        report_lines.append(f"## 筛选概览")
        report_lines.append(f"")
        if original_count:
            filter_rate = (analysis['total_count'] / original_count) * 100
            report_lines.append(f"- **原始联系人数量**: {original_count:,}")
            report_lines.append(f"- **筛选后数量**: {analysis['total_count']:,}")
            report_lines.append(f"- **筛选通过率**: {filter_rate:.1f}%")
        else:
            report_lines.append(f"- **筛选结果数量**: {analysis['total_count']:,}")
        
        if min_score:
            report_lines.append(f"- **最低分数阈值**: {min_score}")
        
        if processing_time:
            avg_time = (processing_time / max(analysis['total_count'], 1)) * 1000
            report_lines.append(f"- **处理时间**: {processing_time:.2f}秒")
            report_lines.append(f"- **平均每人处理时间**: {avg_time:.2f}毫秒")
        
        report_lines.append(f"")
        
        # 分数统计
        if analysis['score_stats']:
            stats = analysis['score_stats']
            report_lines.append(f"## 分数统计")
            report_lines.append(f"")
            report_lines.append(f"- **平均分数**: {stats['mean']:.3f}")
            report_lines.append(f"- **中位数分数**: {stats['median']:.3f}")
            report_lines.append(f"- **最高分数**: {stats['max']:.3f}")
            report_lines.append(f"- **最低分数**: {stats['min']:.3f}")
            report_lines.append(f"- **标准差**: {stats['std']:.3f}")
            report_lines.append(f"")
        
        # 分数分布
        if analysis['score_distribution']:
            report_lines.append(f"## 分数分布")
            report_lines.append(f"")
            for range_name, count in analysis['score_distribution'].items():
                percentage = (count / analysis['total_count']) * 100 if analysis['total_count'] > 0 else 0
                report_lines.append(f"- **{range_name}**: {count}人 ({percentage:.1f}%)")
            report_lines.append(f"")
        
        # 职位分布
        if analysis['title_distribution']:
            report_lines.append(f"## 热门职位 (Top 10)")
            report_lines.append(f"")
            for i, (title, count) in enumerate(analysis['title_distribution'].items(), 1):
                percentage = (count / analysis['total_count']) * 100 if analysis['total_count'] > 0 else 0
                report_lines.append(f"{i}. **{title}**: {count}人 ({percentage:.1f}%)")
            report_lines.append(f"")
        
        # 公司分布
        if analysis['company_distribution']:
            report_lines.append(f"## 热门公司 (Top 10)")
            report_lines.append(f"")
            for i, (company, count) in enumerate(analysis['company_distribution'].items(), 1):
                percentage = (count / analysis['total_count']) * 100 if analysis['total_count'] > 0 else 0
                report_lines.append(f"{i}. **{company}**: {count}人 ({percentage:.1f}%)")
            report_lines.append(f"")
        
        # 地区分布
        if analysis['location_distribution']:
            report_lines.append(f"## 热门地区 (Top 10)")
            report_lines.append(f"")
            for i, (location, count) in enumerate(analysis['location_distribution'].items(), 1):
                percentage = (count / analysis['total_count']) * 100 if analysis['total_count'] > 0 else 0
                report_lines.append(f"{i}. **{location}**: {count}人 ({percentage:.1f}%)")
            report_lines.append(f"")
        
        # 高分联系人示例
        if filtered_contacts:
            high_score_contacts = sorted(
                filtered_contacts, 
                key=lambda x: x.get('total_score') or x.get('match_score') or x.get('job_score', 0), 
                reverse=True
            )[:10]
            
            if high_score_contacts:
                report_lines.append(f"## 高分联系人示例 (Top 10)")
                report_lines.append(f"")
                for i, contact in enumerate(high_score_contacts, 1):
                    name = contact.get('name', 'N/A')
                    title = contact.get('title', 'N/A')
                    company = contact.get('company', 'N/A')
                    score = contact.get('total_score') or contact.get('match_score') or contact.get('job_score', 0)
                    
                    report_lines.append(f"{i}. **{name}** - {title}")
                    report_lines.append(f"   - 公司: {company}")
                    report_lines.append(f"   - 分数: {score:.3f}")
                    
                    # 显示匹配原因（如果有）
                    if 'match_reasons' in contact and contact['match_reasons']:
                        reasons = ', '.join(contact['match_reasons'][:3])  # 只显示前3个原因
                        report_lines.append(f"   - 匹配原因: {reasons}")
                    
                    report_lines.append(f"")
        
        # 筛选配置信息
        if filter_config:
            report_lines.append(f"## 筛选配置")
            report_lines.append(f"")
            report_lines.append(f"```json")
            report_lines.append(json.dumps(filter_config, indent=2, ensure_ascii=False))
            report_lines.append(f"```")
            report_lines.append(f"")
        
        # 报告结尾
        report_lines.append(f"---")
        report_lines.append(f"*本报告由LinkedIn营销自动化系统自动生成*")
        
        return '\n'.join(report_lines)
    
    def generate_comparison_report(self, 
                                 reports: List[str], 
                                 output_filename: str = None) -> str:
        """生成多次筛选结果的对比报告
        
        Args:
            reports: 报告文件路径列表
            output_filename: 输出文件名
            
        Returns:
            对比报告文件路径
        """
        if not output_filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_filename = f'comparison_report_{timestamp}.md'
        
        output_path = os.path.join(self.reports_dir, output_filename)
        
        # TODO: 实现对比报告逻辑
        # 这里可以添加多次筛选结果的对比分析
        
        return output_path