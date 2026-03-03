#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LinkedIn营销系统命令行界面
提供简单易用的命令行操作界面
"""

import os
import sys
import json
import argparse
import sqlite3
import time
import re
import webbrowser
import urllib.parse
import urllib.request
import shlex
from typing import List, Dict, Any, Tuple
from datetime import datetime

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.main_controller import LinkedInMarketingController, quick_start
from src.utils.logger import get_logger
from src.utils.helpers import save_json_file
from src.utils.config_loader import ConfigLoader

class LinkedInMarketingCLI:
    """LinkedIn营销系统命令行界面"""
    
    def __init__(self):
        self.controller = None
        self.logger = get_logger("cli")
        
    def print_banner(self):
        """打印系统横幅（简洁等宽版，避免中英文混排错位）"""
        title = "LinkedIn营销自动化系统 | LinkedIn Marketing Automation"
        sep = "-" * max(60, len(title))
        print(sep)
        print(title)
        print(sep)
        print("功能: 搜索 → 筛选 → 营销  |  Features: Search → Filter → Marketing")
        print(sep)
    
    def print_help(self):
        """打印帮助信息"""
        help_text = """
🚀 LinkedIn营销系统使用指南

📋 基本命令:
  init                     - 初始化系统
  start                    - 启动浏览器会话
  scrape                   - 爬取联系人（交互式输入搜索内容和页数）
  scrape-sales             - Sales Navigator爬取
  filter                   - 智能筛选联系人（支持 llm_simple / hybrid）
  report                   - 生成筛选结果分析报告
  connect                  - 交互式选择招呼语与数据来源（视图/队列/基表），自动监听“Add a note”并填充，写入营销记录（pending）
  email "subject" "body"    - 发送邮件
  status                   - 查看系统状态
  export [type]            - 导出/转换：
                             - 直接加参数(json/csv)：从数据库导出
                             - 无参数：打开导出菜单（含 raw 合并、raw→CSV/SQL、processed→CSV/SQLite、DB 导出）
  backup                   - 备份系统数据
  cleanup [days]           - 清理旧数据
  import-db                - 导入 processed/trimmed_contacts_*.json 到数据库 contacts 表
  queue-connect            - 从 contacts 中按分数挑选待触达并写入 marketing_records（pending）
   
  help                     - 显示帮助信息
  journey                  - 显示推荐产品流程（从命令到爬取到触达）
  quit/exit                - 退出系统
  trim                     - 精简最新筛选结果，仅保留所需字段；并尝试从 raw/merged_* 补回 linkedin_url

💡 使用示例:
  scrape                     - 交互式爬取（输入搜索内容和页数）
  scrape --keywords "ceo,food scientist" --pages 3  - 直接按关键词批量爬取
  scrape-sales               - Sales Navigator爬取
  filter                     - 选择文件并输入需求词进行智能筛选
  report                     - 为最新筛选结果生成分析报告
  connect                   - 选择招呼语与数据来源后批量打开URL并监控标签页关闭（每批默认20个）
  export csv                   - 导出CSV格式数据

⚠️ 注意事项:
  1. 使用前请确保Chrome浏览器已启动调试模式
  2. 请先登录LinkedIn账户
  3. 多页爬取时请适当控制页数，避免过度频繁操作
  4. Sales Navigator需要先在浏览器中设置好搜索条件
  5. 所有步骤都可以输入'back'返回主菜单
  6. 遵守LinkedIn使用条款
        """
        print(help_text)

    def _parse_inline_options(self, args_text: str) -> Dict[str, str]:
        try:
            tokens = shlex.split(args_text or "")
        except Exception:
            tokens = (args_text or "").split()
        opts: Dict[str, str] = {}
        i = 0
        while i < len(tokens):
            t = tokens[i]
            if t.startswith('--'):
                key = t[2:].strip()
                val = 'true'
                if i + 1 < len(tokens) and not tokens[i + 1].startswith('--'):
                    val = tokens[i + 1]
                    i += 1
                opts[key] = val
            i += 1
        return opts

    def _load_scoring_rules(self) -> Dict[str, Any]:
        try:
            cfg = ConfigLoader()
            settings = cfg.load_settings() if hasattr(cfg, 'load_settings') else {}
            filtering = settings.get('filtering', {}) if isinstance(settings, dict) else {}
            return {'filtering': filtering if isinstance(filtering, dict) else {}}
        except Exception:
            return {}

    def _get_default_filter_min_score(self) -> float:
        try:
            rules = self._load_scoring_rules()
            if isinstance(rules, dict):
                filtering_cfg = rules.get('filtering', {})
                if isinstance(filtering_cfg, dict) and filtering_cfg.get('default_min_score') is not None:
                    return float(filtering_cfg.get('default_min_score'))
            cfg = ConfigLoader()
            val = cfg.get_setting('filtering.min_match_score', 0.3)
            return float(val)
        except Exception:
            return 0.3

    def _get_filter_mode(self) -> str:
        try:
            rules = self._load_scoring_rules()
            filtering_cfg = rules.get('filtering', {}) if isinstance(rules, dict) else {}
            mode = str(filtering_cfg.get('mode', 'hybrid')).strip().lower()
            if mode in ('hybrid', 'llm_simple'):
                return mode
            return 'hybrid'
        except Exception:
            return 'hybrid'

    def _prepare_llm_candidates(
        self,
        contacts_data: List[Dict[str, Any]],
        requirements_input: str
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        _ = requirements_input
        ordered_contacts = list(contacts_data)
        return ordered_contacts, {
            'prefiltered': False,
            'prefilter_pool_size': len(ordered_contacts),
            'llm_budget': len(ordered_contacts)
        }

    def _filter_contacts_with_llm_simple(
        self,
        contacts_data: List[Dict[str, Any]],
        requirements_input: str,
        min_score: float
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        from src.utils.llm_client import LLMClient
        llm_client = LLMClient()
        if not llm_client.is_enabled():
            raise RuntimeError("LLM未启用，请先配置后再使用llm_simple模式")

        rules = self._load_scoring_rules()
        filtering_cfg = rules.get('filtering', {}) if isinstance(rules, dict) else {}
        llm_batch_size = int(filtering_cfg.get('llm_batch_size', 100))
        progress_step = int(filtering_cfg.get('llm_simple_progress_step', 20))
        llm_fail_fast = bool(filtering_cfg.get('llm_simple_fail_fast', True))
        contacts_to_score, prefilter_meta = self._prepare_llm_candidates(
            contacts_data=contacts_data,
            requirements_input=requirements_input
        )

        print(f"🤖 LLM简化评分中，待评估 {len(contacts_to_score)} 个联系人（总量 {len(contacts_data)}）...")
        print(f"⚙️ 当前生效配置: llm_batch_size={llm_batch_size}, fail_fast={llm_fail_fast}")
        if prefilter_meta.get('prefiltered'):
            print(f"⚡ 已启用快速预排序：候选池 {prefilter_meta.get('prefilter_pool_size')}，LLM预算 {prefilter_meta.get('llm_budget')}")
        matched_contacts: List[Dict[str, Any]] = []
        progress_step = max(1, progress_step)
        llm_batch_size = max(1, llm_batch_size)

        def _build_contact_info(contact: Dict[str, Any]) -> Dict[str, Any]:
            return {
                'name': contact.get('name', ''),
                'title': contact.get('title', ''),
                'company': contact.get('company', ''),
                'location': contact.get('location', ''),
            }

        def _enrich_contact(contact: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
            try:
                score = float(result.get('match_score', 0.0) or 0.0)
            except Exception:
                score = 0.0
            enriched_contact = dict(contact)
            enriched_contact['match_score'] = score
            enriched_contact['match_reasons'] = result.get('match_reasons', [])
            enriched_contact['llm_tags'] = result.get('tags', [])
            enriched_contact['industry_category'] = result.get('industry_category', 'unknown')
            enriched_contact['seniority_level'] = result.get('seniority_level', 'unknown')
            enriched_contact['scoring_mode'] = 'llm_simple'
            return enriched_contact

        total_to_score = len(contacts_to_score)
        completed = 0
        total_batches = (total_to_score + llm_batch_size - 1) // llm_batch_size if total_to_score else 0
        if total_batches:
            print(f"  批量模式：共 {total_batches} 批，每批固定 {llm_batch_size} 人（最后一批可能不足）")
        for start in range(0, total_to_score, llm_batch_size):
            batch_idx = (start // llm_batch_size) + 1
            batch_contacts = contacts_to_score[start:start + llm_batch_size]
            batch_info = [_build_contact_info(c) for c in batch_contacts]
            batch_start_ts = time.perf_counter()
            print(f"  开始第 {batch_idx}/{total_batches} 批（{len(batch_contacts)} 人）")
            try:
                batch_results = llm_client.classify_contacts_tags_batch(batch_info, requirements_input) or []
            except Exception as batch_error:
                if llm_fail_fast:
                    raise RuntimeError(f"[LLM_BATCH_FAILED] 第 {batch_idx} 批失败并中止: {batch_error}") from batch_error
                batch_results = []
            if len(batch_results) != len(batch_contacts):
                batch_results = (batch_results + [{} for _ in range(len(batch_contacts))])[:len(batch_contacts)]
            for contact, result in zip(batch_contacts, batch_results):
                enriched_contact = _enrich_contact(contact, result if isinstance(result, dict) else {})
                if enriched_contact.get('match_score', 0.0) >= min_score:
                    matched_contacts.append(enriched_contact)
                completed += 1
                if completed % progress_step == 0 or completed == total_to_score:
                    print(f"  已评估 {completed}/{total_to_score}")
            batch_elapsed = time.perf_counter() - batch_start_ts
            print(f"  完成第 {batch_idx}/{total_batches} 批，用时 {batch_elapsed:.1f}s")

        matched_contacts.sort(key=lambda x: x.get('match_score', 0.0), reverse=True)
        evaluated_total = len(contacts_to_score)
        match_rate = (len(matched_contacts) / evaluated_total) if evaluated_total else 0.0
        stats = {
            'scoring_mode': 'llm_simple',
            'total_contacts': len(contacts_data),
            'evaluated_contacts': evaluated_total,
            'filtered_contacts': len(matched_contacts),
            'match_rate': match_rate,
            'min_score': min_score,
            'truncated': False,
            'prefiltered': prefilter_meta.get('prefiltered', False),
            'prefilter_pool_size': prefilter_meta.get('prefilter_pool_size', evaluated_total),
            'llm_budget': prefilter_meta.get('llm_budget', evaluated_total),
            'llm_batch_size': llm_batch_size
        }
        return matched_contacts, stats

    def _print_pipeline_guide(self) -> None:
        print("\n🧭 推荐流程（产品视角）")
        print("  1) init                初始化组件、配置、数据库连接")
        print("  2) start               连接 Chrome 调试会话（确保已登录 LinkedIn）")
        print("  3) scrape / scrape-sales 采集线索")
        print("     - 常规爬取: scrape --keywords \"关键词1,关键词2\" --pages 3")
        print("     - 销售导航: scrape-sales")
        print("  4) filter              用自然语言需求做打分筛选")
        print("  5) queue-connect       将高分联系人写入待触达队列")
        print("  6) connect             分批打开并处理连接请求")
        print("  7) status/report/export 复盘结果与导出")
        print("  关键输入是关键词（或已在 Sales Navigator 页面设置条件），不是固定模板。")
    
    def initialize_system(self) -> bool:
        """初始化系统"""
        try:
            print("🔧 正在初始化LinkedIn营销系统...")
            self.controller = LinkedInMarketingController(project_root)
            
            if self.controller.initialize_system():
                print("✅ 系统初始化成功")
                return True
            else:
                print("❌ 系统初始化失败")
                return False
        except Exception as e:
            print(f"❌ 初始化过程中发生错误: {e}")
            return False
    

    
    def scrape_llm_from_file(self) -> bool:
        """从data/raw目录选择文件进行LLM筛选"""
        try:
            if not self.controller or not self.controller.is_initialized:
                print("❌ 请先初始化系统")
                return False
            
            # 获取data/raw目录下的文件
            raw_dir = os.path.join(project_root, 'data', 'raw')
            if not os.path.exists(raw_dir):
                print("❌ data/raw目录不存在")
                return False
            
            # 列出所有JSON文件
            json_files = [f for f in os.listdir(raw_dir) if f.endswith('.json')]
            if not json_files:
                print("❌ data/raw目录下没有找到JSON文件")
                return False
            
            # 显示文件列表供用户选择
            print("\n📁 data/raw目录下的文件:")
            width = len(str(len(json_files)))
            for i, filename in enumerate(json_files, 1):
                file_path = os.path.join(raw_dir, filename)
                file_size = os.path.getsize(file_path) / 1024  # KB
                print(f"  {i:>{width}}. {filename} ({file_size:.1f} KB)")
            
            # 用户选择文件
            while True:
                try:
                    choice = input(f"\n请选择文件 (1-{len(json_files)}): ").strip()
                    if not choice:
                        print("❌ 请输入文件编号")
                        continue
                    
                    choice_num = int(choice)
                    if 1 <= choice_num <= len(json_files):
                        selected_file = json_files[choice_num - 1]
                        break
                    else:
                        print(f"❌ 请输入1到{len(json_files)}之间的数字")
                        continue
                except ValueError:
                    print("❌ 请输入有效的数字")
                    continue
            
            # 询问最低分数
            min_score = 0.3
            try:
                min_score_input = input("请输入最低匹配分数（0.0-1.0，默认0.3）: ").strip()
                if min_score_input:
                    min_score = float(min_score_input)
                    if not (0.0 <= min_score <= 1.0):
                        print("⚠️ 分数超出范围，使用默认值0.3")
                        min_score = 0.3
            except ValueError:
                print("⚠️ 分数格式错误，使用默认值0.3")
                min_score = 0.3
            
            # 加载选中的文件
            selected_file_path = os.path.join(raw_dir, selected_file)
            print(f"\n📂 正在加载文件: {selected_file}")
            
            with open(selected_file_path, 'r', encoding='utf-8') as f:
                contacts_data = json.load(f)
            
            print(f"📊 文件包含 {len(contacts_data)} 个联系人")
            
            # 使用控制器进行LLM筛选
            print(f"🚀 开始LLM智能筛选，最低分数: {min_score}")
            
            # 使用控制器的筛选方法，传入联系人数据
            filtered_contacts = self.controller.filter_contacts_from_data(contacts_data, min_score=min_score)
            
            if filtered_contacts:
                print(f"✅ LLM筛选完成，找到 {len(filtered_contacts)} 个匹配联系人")
                
                # 显示前5个结果
                print("\n🎯 LLM筛选结果预览:")
                for i, contact in enumerate(filtered_contacts[:5], 1):
                    print(f"  {i}. {contact.get('name', 'N/A')} - {contact.get('title', 'N/A')}")
                    print(f"     公司: {contact.get('company', 'N/A')}")
                    print(f"     总分: {contact.get('total_score', contact.get('match_score', 0)):.2f}")
                    print()
                
                if len(filtered_contacts) > 5:
                    print(f"... 还有 {len(filtered_contacts) - 5} 个结果")
                
                # 保存筛选结果到processed目录
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_file = os.path.join(project_root, 'data', 'processed', f'llm_filtered_contacts_{timestamp}.json')
                save_json_file(filtered_contacts, output_file)
                print(f"💾 LLM筛选结果已保存到: {output_file}")
                
                return True
            else:
                print("❌ LLM筛选没有找到匹配的联系人")
                return False
                
        except Exception as e:
            print(f"❌ LLM筛选失败: {e}")
            return False
    
    def scrape_sales_navigator(self, max_pages: int = None) -> bool:
        """Sales Navigator爬取"""
        try:
            if not self.controller:
                print("❌ 系统未初始化，请先运行 'init' 命令")
                return False
            
            # 询问爬取页数
            if max_pages is None:
                while True:
                    try:
                        pages_input = input("请输入Sales Navigator爬取页数（1-100，超过100为最大值，默认3页）: ").strip()
                        if not pages_input:
                            max_pages = 3
                            break
                        
                        max_pages = int(pages_input)
                        if max_pages <= 0:
                            print("❌ 页数必须大于0")
                            continue
                        elif max_pages > 100:
                            max_pages = 100
                            print("⚠️ 页数超过100，已设置为最大值100")
                        break
                    except ValueError:
                        print("❌ 请输入有效的数字")
                        continue
            else:
                max_pages = max(1, min(int(max_pages), 100))
            
            print(f"🔍 开始Sales Navigator爬取，页数: {max_pages}")
            print("⚠️ 请确保已在浏览器中打开Sales Navigator并设置好搜索条件")
            
            # 使用爬虫的搜索管理器进行Sales Navigator搜索
            results = self.controller.scraper.search_manager.search_people_sales_navigator(
                max_results=50 * max_pages,
                max_pages=max_pages
            )
            
            if results:
                print(f"✅ 成功从Sales Navigator爬取 {len(results)} 个联系人（{max_pages}页）")
                return True
            else:
                print("❌ 未找到任何联系人")
                return False
                
        except Exception as e:
            print(f"❌ Sales Navigator爬取失败: {str(e)}")
            return False
    
    def start_browser(self) -> bool:
        """启动浏览器会话"""
        try:
            if not self.controller:
                print("❌ 请先初始化系统 (使用 'init' 命令)")
                return False
            
            print("🌐 正在启动浏览器会话...")
            if self.controller.start_browser_session():
                print("✅ 浏览器会话启动成功")
                print("💡 请确保已登录LinkedIn账户")
                return True
            else:
                print("❌ 浏览器会话启动失败")
                print("\n💡 Chrome调试模式启动方法:")
                print("   方法1: 运行 auto_start_chrome.bat (推荐)")
                print("   方法2: 运行 scripts/start_chrome_debug.ps1")
                print("   方法3: 手动启动Chrome调试模式")
                print("\n🔧 如果问题持续，系统会自动尝试启动Chrome调试模式")
                return False
                
        except Exception as e:
            print(f"❌ 启动浏览器失败: {e}")
            return False
    
    def scrape_contacts(self, search_input: str = None, max_pages: int = None) -> bool:
        """交互式爬取联系人数据"""
        try:
            if not self.controller or not self.controller.is_initialized:
                print("❌ 请先初始化系统并启动浏览器")
                return False
            
            # 交互式输入搜索内容
            if search_input is None:
                while True:
                    search_input = input("请输入在LinkedIn搜索的内容（输入'back'返回主菜单）: ").strip()
                    if search_input.lower() == 'back':
                        return False
                    if search_input:
                        break
                    print("❌ 搜索内容不能为空")
            else:
                search_input = str(search_input).strip()
                if not search_input:
                    print("❌ 搜索内容不能为空")
                    return False
            
            # 解析关键词
            keywords = [k.strip() for k in search_input.split(',') if k.strip()]
            
            # 询问爬取页数
            if max_pages is None:
                while True:
                    try:
                        pages_input = input("请输入爬取页数（1-100，输入'back'返回主菜单）: ").strip()
                        if pages_input.lower() == 'back':
                            return False
                        if not pages_input:
                            max_pages = 1
                            break
                        
                        max_pages = int(pages_input)
                        if max_pages <= 0:
                            print("❌ 页数必须大于0")
                            continue
                        elif max_pages > 100:
                            max_pages = 100
                            print("⚠️ 页数超过100，已设置为最大值100")
                        break
                    except ValueError:
                        print("❌ 请输入有效的数字")
                        continue
            else:
                max_pages = max(1, min(int(max_pages), 100))
            
            print(f"🔍 开始爬取联系人数据（{max_pages}页）...")
            print(f"📝 搜索关键词: {', '.join(keywords)}")
            print(f"🏢 爬取后将自动访问个人主页补全公司信息")
            
            results = self.controller.scrape_keywords(keywords, max_results_per_keyword=None, max_pages=max_pages, enrich_profiles=True)
            
            if results.get('success'):
                print(f"✅ 爬取完成!")
                print(f"📊 处理关键词: {results['keywords_processed']}")
                print(f"👥 总联系人: {results['total_contacts']}")
                print(f"💾 导入数据库: {results['import_stats']['total_imported']}")
                print(f"⏭️ 跳过重复: {results['import_stats']['total_skipped']}")
                
                # 显示每个关键词的结果
                print("\n📋 各关键词结果:")
                for keyword, count in results['results_by_keyword'].items():
                    print(f"  • {keyword}: {count} 个联系人")
                
                return True
            else:
                print(f"❌ 爬取失败: {results.get('error', '未知错误')}")
                return False
                
        except Exception as e:
            print(f"❌ 爬取失败: {e}")
            return False
    
    def filter_contacts(self) -> List[Dict[str, Any]]:
        """交互式智能筛选联系人"""
        try:
            # 列出data/raw中的文件
            raw_dir = os.path.join(project_root, 'data', 'raw')
            if not os.path.exists(raw_dir):
                print("❌ data/raw目录不存在，请先进行爬取")
                return []
            
            # 获取所有JSON文件
            json_files = [f for f in os.listdir(raw_dir) if f.endswith('.json')]
            if not json_files:
                print("❌ data/raw目录中没有找到JSON文件")
                return []
            
            # 显示文件列表供用户选择
            print("\n📁 data/raw目录中的文件:")
            width = len(str(len(json_files)))
            for i, filename in enumerate(json_files, 1):
                file_path = os.path.join(raw_dir, filename)
                file_size = os.path.getsize(file_path) / 1024  # KB
                print(f"  {i:>{width}}. {filename} ({file_size:.1f} KB)")
            
            # 用户选择文件
            while True:
                try:
                    choice_input = input(f"\n请选择文件编号（1-{len(json_files)}，输入'back'返回主菜单）: ").strip()
                    if choice_input.lower() == 'back':
                        return []
                    
                    choice = int(choice_input)
                    if 1 <= choice <= len(json_files):
                        selected_file = json_files[choice - 1]
                        break
                    else:
                        print(f"❌ 请输入1到{len(json_files)}之间的数字")
                except ValueError:
                    print("❌ 请输入有效的数字")
            
            selected_file_path = os.path.join(raw_dir, selected_file)
            print(f"✅ 已选择文件: {selected_file}")
            
            # 输入需求描述
            while True:
                requirements_input = input("\n请输入您的需求描述（自然语言，输入'back'返回主菜单）: ").strip()
                if requirements_input.lower() == 'back':
                    return []
                if requirements_input:
                    break
                print("❌ 需求描述不能为空")
            
            print(f"📝 原始需求: {requirements_input}")
            
            class _InlineRequirementsAdapter:
                def parse_requirements(self, text: str) -> Dict[str, Any]:
                    return {'raw_requirements': text}

                def format_for_display(self, parsed: Dict[str, Any]) -> str:
                    return f"  原始需求: {parsed.get('raw_requirements', '')}"

                def update_scoring_config(self, parsed: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
                    updated = dict(config or {})
                    updated.setdefault('runtime_requirements', {})
                    updated['runtime_requirements']['raw_requirements'] = parsed.get('raw_requirements', '')
                    return updated

            parser = _InlineRequirementsAdapter()
            parsed_requirements = parser.parse_requirements(requirements_input)
            
            print("\n🔍 需求解析结果:")
            print(parser.format_for_display(parsed_requirements))
            
            # 加载选中的文件数据
            try:
                with open(selected_file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                
                # 如果文件包含联系人数据，提取联系人列表
                if isinstance(file_data, list):
                    contacts_data = file_data
                elif isinstance(file_data, dict) and 'contacts' in file_data:
                    contacts_data = file_data['contacts']
                else:
                    # 尝试从all_contacts.json加载（作为备选）
                    all_contacts_path = os.path.join(project_root, 'data', 'processed', 'all_contacts.json')
                    if os.path.exists(all_contacts_path):
                        with open(all_contacts_path, 'r', encoding='utf-8') as f:
                            contacts_data = json.load(f)
                        print(f"⚠️ 从{selected_file}无法提取联系人数据，使用all_contacts.json")
                    else:
                        print("❌ 无法从选中文件提取联系人数据")
                        return []
                
                if not contacts_data:
                    print("❌ 文件中没有联系人数据")
                    return []
                
                print(f"📊 加载了 {len(contacts_data)} 个联系人")
                
            except Exception as load_error:
                print(f"❌ 加载文件失败: {load_error}")
                return []
            
            # 加载和更新运行配置
            try:
                config = self._load_scoring_rules()
                # 根据解析的需求更新配置
                updated_config = parser.update_scoring_config(parsed_requirements, config)
                
                default_min_score = self._get_default_filter_min_score()
                min_score = default_min_score
                min_score_input = input(f"请输入筛选阈值（默认{default_min_score:.2f}）: ").strip()
                if min_score_input:
                    try:
                        min_score = float(min_score_input)
                    except Exception:
                        min_score = default_min_score
                score_mode = 'llm_resume_style'
                print(f"🚀 开始智能筛选，模式: {score_mode}")
                from src.filter.contact_filter import ContactFilter
                filter_engine = ContactFilter()
                if isinstance(updated_config, dict):
                    filter_engine.scoring_engine.config = updated_config
                filtering_cfg = filter_engine.scoring_engine.config.get('filtering', {}) if isinstance(filter_engine.scoring_engine.config, dict) else {}
                try:
                    llm_batch_size = max(1, int(filtering_cfg.get('llm_batch_size', 100)))
                except Exception:
                    llm_batch_size = 100
                print(f"⚙️ 当前生效配置: llm_batch_size={llm_batch_size}")
                try:
                    llm_score_timeout = float(filtering_cfg.get('llm_score_timeout_seconds', 12))
                except Exception:
                    llm_score_timeout = 12.0
                try:
                    llm_score_retries = max(1, int(filtering_cfg.get('llm_score_retry_attempts', 1)))
                except Exception:
                    llm_score_retries = 1
                scoped_contacts = len(contacts_data)
                batch_count = (max(0, scoped_contacts - 1) // llm_batch_size + 1) if scoped_contacts else 0
                llm_call_count = batch_count
                estimated_upper_seconds = int(llm_call_count * llm_score_timeout * llm_score_retries)
                print(
                    f"⏱️ 预计处理人数: {scoped_contacts} 人, 批次={batch_count}, 每批={llm_batch_size}, 预计LLM请求={llm_call_count}, "
                    f"理论最长约 {estimated_upper_seconds}s",
                    flush=True
                )
                filtered_contacts, stats = filter_engine.filter_contacts(
                    contacts=contacts_data,
                    requirements_input=requirements_input,
                    min_score=min_score,
                    require_llm=True
                )
                
            except Exception as config_error:
                print(f"❌ 配置加载失败: {config_error}")
                return []
            
            if filtered_contacts:
                print(f"✅ V3筛选完成，找到 {len(filtered_contacts)} 个匹配联系人")
                print(f"📊 匹配率: {stats.get('match_rate', 0)*100:.1f}%")
                if stats.get('truncated'):
                    print(
                        f"⚠️ 本次仅评分 {stats.get('scored_contacts', 0)}/{stats.get('input_contacts', 0)} 条，"
                        f"批大小为 llm_batch_size={stats.get('llm_batch_size', 0)}"
                    )
                
                # 显示前5个结果
                print("\n🎯 V3筛选结果预览:")
                preview_count = 5
                try:
                    preview_count = int(self._load_scoring_rules().get('filtering', {}).get('preview_count', 5))
                except Exception:
                    preview_count = 5
                for i, contact in enumerate(filtered_contacts[:preview_count], 1):
                    print(f"  {i}. {contact.get('name', 'N/A')} - {contact.get('title', 'N/A')}")
                    print(f"     公司: {contact.get('company', 'N/A')}")
                    print(f"     总分: {contact.get('match_score', 0):.3f}")
                    print()
                
                if len(filtered_contacts) > preview_count:
                    print(f"... 还有 {len(filtered_contacts) - preview_count} 个结果")
                
                # 保存筛选结果到data/filter_results
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filter_results_root = os.path.join(project_root, 'data', 'filter_results')
                run_dir = os.path.join(filter_results_root, f'run_{timestamp}')
                os.makedirs(run_dir, exist_ok=True)
                output_file = os.path.join(run_dir, 'filter_result.json')
                
                # 构建完整的输出数据
                output_data = {
                    'contacts': filtered_contacts,
                    'stats': stats,
                    'filter_config': {
                        'source_file': selected_file,
                        'requirements': requirements_input,
                        'min_score': min_score,
                        'mode': stats.get('scoring_mode', self._get_filter_mode()),
                        'filtered_at': timestamp
                    },
                    'metadata': {
                        'total_contacts': len(contacts_data),
                        'filtered_contacts': len(filtered_contacts),
                        'filter_version': 'SmartFilterV3',
                        'run_dir': run_dir
                    }
                }
                
                save_json_file(output_data, output_file)
                print(f"💾 V3筛选结果已保存到: {output_file}")
                
                return filtered_contacts
            else:
                print("❌ V3筛选没有找到匹配的联系人")
                return []
                
        except Exception as e:
            print(f"❌ V3筛选失败: {e}")
            return []
    
    def analyze_contact(self, contact_name: str):
        """使用V3引擎分析单个联系人"""
        try:
            if not self.controller or not self.controller.is_initialized:
                print("❌ 请先初始化系统")
                return
            
            print(f"🔍 开始V3分析联系人: {contact_name}")
            
            analysis_result = self.controller.analyze_contact(contact_name)
            
            if analysis_result:
                print(f"\n✅ V3分析完成")
                print(f"👤 姓名: {analysis_result.get('name', 'N/A')}")
                print(f"💼 职位: {analysis_result.get('title', 'N/A')}")
                print(f"🏢 公司: {analysis_result.get('company', 'N/A')}")
                print(f"📊 总分: {analysis_result.get('total_score', 0):.2f}")
                
                if analysis_result.get('score_breakdown'):
                    print("\n📋 分数详情:")
                    breakdown = analysis_result['score_breakdown']
                    for key, value in breakdown.items():
                        print(f"  • {key}: {value:.2f}")
                
                if analysis_result.get('analysis_summary'):
                    print(f"\n📝 分析摘要: {analysis_result['analysis_summary']}")
            else:
                print("❌ 未找到该联系人或分析失败")
                
        except Exception as e:
            print(f"❌ V3分析失败: {e}")
    
    def send_connections(self, message: str, contacts: List[Dict[str, Any]] = None) -> bool:
        """发送连接请求"""
        try:
            if not self.controller or not self.controller.is_initialized:
                print("❌ 请先初始化系统并启动浏览器")
                return False
            
            # 如果没有提供联系人，使用最近的筛选结果
            if not contacts:
                print("💡 未指定联系人，将使用最近的筛选结果")
                # 这里可以从数据库获取最近筛选的联系人
                # 暂时提示用户先进行筛选
                print("❌ 请先使用 'filter' 命令筛选联系人")
                return False
            
            print(f"📤 准备发送 {len(contacts)} 个连接请求...")
            print(f"💬 连接消息: {message[:50]}..." if len(message) > 50 else f"💬 连接消息: {message}")
            
            # 确认发送
            confirm = input("\n⚠️ 确认发送连接请求? (y/N): ").strip().lower()
            if confirm != 'y':
                print("❌ 操作已取消")
                return False
            
            results = self.controller.send_connection_requests(contacts, message)
            
            if results.get('success'):
                print(f"✅ 连接请求发送完成!")
                print(f"📤 成功发送: {results.get('sent', 0)}")
                print(f"❌ 发送失败: {results.get('failed', 0)}")
                print(f"⏭️ 跳过处理: {results.get('skipped', 0)}")
                return True
            else:
                print(f"❌ 发送失败: {results.get('error', '未知错误')}")
                return False
                
        except Exception as e:
            print(f"❌ 发送连接请求失败: {e}")
            return False
    
    def _list_db_views(self) -> List[str]:
        """列出 SQLite 中的视图名称"""
        try:
            db_path = self.controller.database_manager.db_path
            with sqlite3.connect(db_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")
                rows = cur.fetchall()
                return [r[0] for r in rows]
        except Exception as e:
            self.logger.warning(f"获取视图失败: {e}")
            return []

    def _ensure_view_min_score(self, view_name: str, min_score: float) -> bool:
        """确保存在一个基于 match_score 阈值的视图。如不存在则创建。
        注意：SQLite 的 CREATE VIEW 不支持参数占位，这里做最小的白名单校验。
        """
        try:
            safe_name = ''.join(ch for ch in view_name if ch.isalnum() or ch == '_' )
            if not safe_name:
                return False
            threshold = float(min_score)
            db_path = self.controller.database_manager.db_path
            with sqlite3.connect(db_path) as conn:
                cur = conn.cursor()
                sql = (
                    f"CREATE VIEW IF NOT EXISTS {safe_name} AS "
                    "SELECT id, name, title, company, location, linkedin_url, match_score "
                    "FROM contacts "
                    f"WHERE COALESCE(match_score, 0.0) >= {threshold}"
                )
                cur.execute(sql)
                conn.commit()
            return True
        except Exception as e:
            self.logger.warning(f"创建视图失败: {e}")
            return False

    def init_default_views(self) -> bool:
        """创建默认视图：v_contacts_score_030 (match_score>=0.3)"""
        try:
            ok = self._ensure_view_min_score('v_contacts_score_030', 0.3)
            if ok:
                print("✅ 已确保存在视图: v_contacts_score_030 (match_score>=0.3)")
            else:
                print("❌ 视图创建失败: v_contacts_score_030")
            return ok
        except Exception as e:
            print(f"❌ 视图初始化失败: {e}")
            return False

    def _load_contacts_from_source(self, choice: str, min_score: float = 0.6, limit: int = 100) -> List[Dict[str, Any]]:
        """根据来源选择加载联系人集：
        - choice == '__contacts__': 从 contacts 按分数筛选
        - choice == '__queue__': 从 marketing_records pending 队列
        - 其他: 作为视图名直接 SELECT * FROM view
        返回至少包含 id、name、company、linkedin_url、match_score 的字典列表
        """
        results: List[Dict[str, Any]] = []
        try:
            db_path = self.controller.database_manager.db_path
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                if choice == '__contacts__':
                    cur.execute(
                        """
                        SELECT id, name, company, title, location, linkedin_url, match_score
                        FROM contacts
                        WHERE (match_score IS NULL OR match_score >= ?)
                        ORDER BY COALESCE(match_score, 0) DESC, created_at DESC
                        LIMIT ?
                        """,
                        (min_score, limit)
                    )
                    rows = cur.fetchall()
                    results = [dict(r) for r in rows]
                elif choice == '__queue__':
                    cur.execute(
                        """
                        SELECT c.id, c.name, c.company, c.title, c.location, c.linkedin_url, c.match_score
                        FROM marketing_records mr
                        JOIN contacts c ON c.id = mr.contact_id
                        WHERE mr.action_type='connect' AND mr.status='pending'
                        ORDER BY mr.created_at DESC
                        LIMIT ?
                        """,
                        (limit,)
                    )
                    rows = cur.fetchall()
                    results = [dict(r) for r in rows]
                else:
                    # 视图
                    views = set(self._list_db_views())
                    if choice not in views:
                        print("❌ 视图不存在或不可用")
                        return []
                    try:
                        cur.execute(f"SELECT * FROM {choice} LIMIT ?", (limit,))
                    except Exception as e:
                        print(f"❌ 读取视图失败: {e}")
                        return []
                    rows = cur.fetchall()
                    for r in rows:
                        rd = dict(r)
                        results.append({
                            'id': rd.get('id'),
                            'name': rd.get('name') or rd.get('Name') or '',
                            'company': rd.get('company') or rd.get('Company') or '',
                            'title': rd.get('title') or rd.get('Title') or '',
                            'location': rd.get('location') or rd.get('Location') or '',
                            'linkedin_url': rd.get('linkedin_url') or rd.get('url') or '',
                            'match_score': rd.get('match_score') or rd.get('total_score')
                        })
        except Exception as e:
            self.logger.warning(f"加载联系人失败: {e}")
            return []
        return [c for c in results if c.get('linkedin_url')]

    def _insert_marketing_record_pending(self, contact_id: int, message: str) -> None:
        """写入一条 pending 的 connect 记录（若该联系人已有 pending 则跳过）"""
        try:
            if not contact_id:
                return
            db_path = self.controller.database_manager.db_path
            with sqlite3.connect(db_path) as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT 1 FROM marketing_records WHERE contact_id=? AND action_type='connect' AND status='pending' LIMIT 1",
                    (contact_id,)
                )
                exists = cur.fetchone() is not None
                if not exists:
                    cur.execute(
                        "INSERT INTO marketing_records (contact_id, action_type, status, message, created_at) VALUES (?, 'connect', 'pending', ?, CURRENT_TIMESTAMP)",
                        (contact_id, message)
                    )
                    conn.commit()
        except Exception as e:
            self.logger.warning(f"写入营销记录失败: {e}")

    def _norm_url(self, url: str) -> str:
        try:
            u = (url or '').strip()
            parts = urllib.parse.urlsplit(u)
            # 只保留 scheme/netloc/path，去掉 query/fragment，并去掉结尾斜杠
            path = parts.path[:-1] if parts.path.endswith('/') else parts.path
            return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, '', ''))
        except Exception:
            return (url or '').strip().rstrip('/')

    def _get_chrome_open_urls(self, debug_port: int) -> set:
        """读取 Chrome 调试端口的打开页面 URL 列表（需要以 --remote-debugging-port 启动）"""
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json", timeout=2) as resp:
                data = json.loads(resp.read().decode('utf-8', errors='ignore'))
            urls = []
            for item in data:
                if isinstance(item, dict) and item.get('type') == 'page':
                    u = item.get('url')
                    if u:
                        urls.append(self._norm_url(u))
            return set(urls)
        except Exception:
            return set()

    def _is_debug_endpoint_ready(self, debug_port: int) -> bool:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json", timeout=1) as resp:
                _ = resp.read(1)
            return True
        except Exception:
            return False

    def connect_assisted_flow(self, preselected_message: str = None) -> bool:
        """交互式：选择招呼语 -> 选择数据来源(视图/队列/基表) -> 每批自动打开URL并监控标签页关闭。
        不自动填写备注，不使用 MCP。Ctrl+C 可随时退出。
        """
        try:
            if not self.controller or not self.controller.is_initialized:
                print("❌ 请先初始化系统")
                return False

            # 1) 选择招呼语（优先 settings.json 的 connection_messages，其次 config/messages/connection_messages.json）
            cfg = ConfigLoader()
            settings = cfg.load_settings() if hasattr(cfg, 'load_settings') else {}
            templates = (settings.get('connection_messages') or {})
            if not templates:
                templates = cfg.load_connection_messages() or {}
            chosen_message = preselected_message
            if not chosen_message:
                keys = list(templates.keys())
                if keys:
                    print("\n📨 可用招呼语模板：")
                    width = len(str(len(keys)))
                    for i, k in enumerate(keys, 1):
                        preview = templates[k]
                        preview = (preview[:40] + '…') if len(preview) > 40 else preview
                        print(f"  {i:>{width}}. {k} | {preview}")
                    print(f"  0. 自定义输入")
                    sel = input("请选择模板编号（默认1）: ").strip()
                    idx = 1
                    if sel.isdigit():
                        idx = int(sel)
                    if idx == 0:
                        chosen_message = input("请输入自定义招呼语: ").strip()
                    else:
                        idx = max(1, min(idx, len(keys)))
                        chosen_message = templates.get(keys[idx-1], '')
                else:
                    chosen_message = input("请输入招呼语: ").strip()
            if not chosen_message:
                print("❌ 没有有效招呼语")
                return False

            # 1.5) 确保默认视图存在
            try:
                self._ensure_view_min_score('v_contacts_score_030', 0.3)
            except Exception:
                pass

            # 2) 选择数据来源（视图 / 队列 / 基表）
            views = self._list_db_views()
            if not views:
                # 尝试创建一个默认视图后再读取
                try:
                    self._ensure_view_min_score('v_contacts_score_030', 0.3)
                except Exception:
                    pass
                views = self._list_db_views()
            if not views:
                print("❌ 未找到任何数据库视图，请先创建视图（例如 v_contacts_score_030）。")
                return False

            print("\n🗂️ 选择数据库视图：")
            for i, v in enumerate(views, 1):
                print(f"  {i}. {v}")
            sel = input("请选择视图编号（默认1）: ").strip()
            try:
                idx = int(sel) if sel.isdigit() else 1
            except Exception:
                idx = 1
            idx = max(1, min(idx, len(views)))
            source_key = views[idx-1]

            min_score = 0.6  # 对视图不使用
            limit = 10**9  # 视为全部
            batch_size = 20
            # 不再询问数量上限；视图已完成筛选，默认全量
            try:
                bs = input("每批打开数量（默认20）: ").strip()
                if bs:
                    batch_size = max(1, int(bs))
            except Exception:
                pass

            candidates = self._load_contacts_from_source(source_key, min_score=min_score, limit=limit)
            if not candidates:
                print("⚠️ 未获取到任何联系人（检查视图/队列/分数条件）")
                return False

            # 3) 分批打开并监控标签页（优先使用 Chrome 调试端口 9222 / settings.browser.chrome_debug_port；若不可用则回车推进）
            print(f"\n✅ 已就绪：目标联系人 {len(candidates)} 人。将每批打开 {batch_size} 个标签页。")
            # 尝试读取调试端口
            debug_port = None
            try:
                debug_port = int(settings.get('browser', {}).get('chrome_debug_port', 9222))
            except Exception:
                debug_port = 9222

            # 分批处理
            total = len(candidates)
            i = 0
            while i < total:
                batch = candidates[i:i+batch_size]
                batch_urls = [self._norm_url(c.get('linkedin_url','')) for c in batch if c.get('linkedin_url')]
                # 打开一批
                opened = 0
                for u in batch_urls:
                    try:
                        webbrowser.open_new_tab(u)
                        opened += 1
                        time.sleep(0.12)
                    except Exception:
                        pass
                print(f"🗂️ 已为你打开 {opened}/{len(batch_urls)} 个个人页标签（第 {i+1} - {min(i+batch_size,total)} 项）")

                # 监控这一批是否都关闭
                if debug_port and self._is_debug_endpoint_ready(debug_port):
                    print("👀 正在监控当前批次标签页是否关闭（依赖 Chrome 调试端口）...")
                    try:
                        # 给浏览器注册新标签的时间
                        time.sleep(1.2)
                        # 等待本批 URL 至少有一部分被调试端口检测到，否则回退手动
                        appeared = set()
                        for _ in range(20):  # 最长 ~10s
                            open_urls = self._get_chrome_open_urls(debug_port)
                            appeared |= (set(batch_urls) & open_urls)
                            if appeared:
                                break
                            time.sleep(0.5)
                        if not appeared:
                            print("ℹ️ 未检测到调试端口中的新标签，可能默认浏览器不是调试 Chrome。将改为手动推进。")
                            input("按回车键继续打开下一批...")
                        else:
                            # 仅跟踪已实际出现的那些 URL
                            while True:
                                open_urls = self._get_chrome_open_urls(debug_port)
                                remaining = [u for u in appeared if u in open_urls]
                                if not remaining:
                                    print("✅ 当前批次标签页已全部关闭，准备打开下一批...")
                                    break
                                time.sleep(2)
                    except KeyboardInterrupt:
                        print("⏭️ 手动跳过监控，开始下一批...")
                    except Exception:
                        input("按回车键继续打开下一批...")
                else:
                    input("按回车键继续打开下一批...")

                i += batch_size

            print("🎉 全部批次已处理完成。")
            return True
        except Exception as e:
            print(f"❌ 连接辅助失败: {e}")
            return False

    def send_emails(self, subject: str, body: str, contacts: List[Dict[str, Any]] = None) -> bool:
        """发送邮件"""
        try:
            if not self.controller or not self.controller.is_initialized:
                print("❌ 请先初始化系统")
                return False
            
            # 如果没有提供联系人，使用最近的筛选结果
            if not contacts:
                print("💡 未指定联系人，将使用最近的筛选结果")
                print("❌ 请先使用 'filter' 命令筛选联系人")
                return False
            
            print(f"📧 准备发送 {len(contacts)} 封邮件...")
            print(f"📋 邮件主题: {subject}")
            print(f"📝 邮件内容: {body[:100]}..." if len(body) > 100 else f"📝 邮件内容: {body}")
            
            # 确认发送
            confirm = input("\n⚠️ 确认发送邮件? (y/N): ").strip().lower()
            if confirm != 'y':
                print("❌ 操作已取消")
                return False
            
            results = self.controller.send_emails(contacts, subject, body)
            
            if results.get('success'):
                print(f"✅ 邮件发送完成!")
                print(f"📧 成功发送: {results.get('sent', 0)}")
                print(f"❌ 发送失败: {results.get('failed', 0)}")
                print(f"⏭️ 跳过处理: {results.get('skipped', 0)}")
                return True
            else:
                print(f"❌ 发送失败: {results.get('error', '未知错误')}")
                return False
                
        except Exception as e:
            print(f"❌ 发送邮件失败: {e}")
            return False
    
    def show_status(self):
        """显示系统状态"""
        try:
            if not self.controller:
                print("❌ 系统未初始化")
                return
            
            status = self.controller.get_system_status()
            
            print("\n📊 系统状态:")
            print(f"  🔧 系统初始化: {'✅' if status.get('is_initialized') else '❌'}")
            print(f"  🌐 浏览器活跃: {'✅' if status.get('browser_active') else '❌'}")
            print(f"  📁 项目目录: {status.get('project_root')}")
            
            if status.get('database_stats'):
                db_stats = status['database_stats']
                print(f"\n💾 数据库统计:")
                print(f"  👥 总联系人: {db_stats.get('total_contacts', 0)}")
                print(f"  🏷️ 标签数量: {db_stats.get('total_tags', 0)}")
                print(f"  📤 营销记录: {db_stats.get('total_marketing_records', 0)}")
            
            if status.get('marketing_stats'):
                marketing_stats = status['marketing_stats']
                print(f"\n📈 营销统计:")
                print(f"  📤 今日连接请求: {marketing_stats.get('connections_today', 0)}")
                print(f"  📧 今日邮件: {marketing_stats.get('emails_today', 0)}")
                print(f"  📊 总成功率: {marketing_stats.get('success_rate', 0):.1f}%")
            
        except Exception as e:
            print(f"❌ 获取状态失败: {e}")
    
    def export_data(self, export_type: str = 'json'):
        """导出数据/转换工具
        - 直接传 json/csv: 走数据库导出
        - 无参数: 打开菜单，可执行：
          1) raw 合并为新 JSON（仍存 raw/）
          2) raw 下选择 JSON → 导出 CSV
          3) raw 下选择 JSON → 导出 SQL (.sql)
          4) processed 下选择 JSON → 导出 CSV
          5) processed 下选择 JSON → 导出 SQLite
          6) 从数据库导出 json
          7) 从数据库导出 csv
        """
        try:
            # 直接数据库导出需要系统已初始化；菜单型本地文件操作不强制要求
            if export_type in ['json', 'csv']:
                if not self.controller or not self.controller.is_initialized:
                    print("❌ 请先初始化系统 (数据库导出需要初始化)")
                    return
                print(f"📤 正在从数据库导出 ({export_type.upper()})...")
                filepath = self.controller.export_data(export_type)
                print(f"✅ 数据导出成功: {filepath}" if filepath else "❌ 数据导出失败")
                return

            # 无参数：打开菜单
            print("\n📤 导出/转换菜单：")
            print("  1) 合并 data/raw 下多个 JSON → 新 JSON (仍存 raw/)")
            print("  2) 将 data/raw 下 JSON 转换为 CSV")
            print("  3) 将 data/raw 下 JSON 转换为 SQL (.sql) 文件")
            print("  4) 将 data/processed 下 JSON 转换为 CSV")
            print("  5) 将 data/processed 下 JSON 转换为 SQLite DB")
            print("  6) 从数据库导出 JSON")
            print("  7) 从数据库导出 CSV")
            choice = input("请选择操作 (1-7): ").strip()

            if choice == '1':
                self._export_merge_raw_json()
            elif choice == '2':
                self._export_raw_to_csv()
            elif choice == '3':
                self._export_raw_to_sql()
            elif choice == '4':
                self._export_processed_to_csv()
            elif choice == '5':
                self._export_processed_to_sqlite()
            elif choice == '6':
                if not self.controller or not self.controller.is_initialized:
                    print("❌ 请先初始化系统 (数据库导出需要初始化)")
                else:
                    filepath = self.controller.export_data('json')
                    print(f"✅ 成功: {filepath}" if filepath else "❌ 失败")
            elif choice == '7':
                if not self.controller or not self.controller.is_initialized:
                    print("❌ 请先初始化系统 (数据库导出需要初始化)")
                else:
                    filepath = self.controller.export_data('csv')
                    print(f"✅ 成功: {filepath}" if filepath else "❌ 失败")
            else:
                print("❌ 无效选择")
                
        except Exception as e:
            print(f"❌ 导出失败: {e}")

    def _export_merge_raw_json(self):
        raw_dir = os.path.join(project_root, 'data', 'raw')
        os.makedirs(raw_dir, exist_ok=True)
        files = [f for f in os.listdir(raw_dir) if f.endswith('.json')]
        if not files:
            print("❌ raw 目录没有JSON文件")
            return
        print("\n📁 可合并的 raw JSON 文件：")
        width = len(str(len(files)))
        for i, f in enumerate(files, 1):
            print(f"  {i:>{width}}. {f}")
        sel = input("输入要合并的编号（用逗号分隔，例如 1,3,5）: ").strip()
        try:
            idx = [int(x)-1 for x in sel.split(',') if x.strip().isdigit()]
            chosen = [files[i] for i in idx if 0 <= i < len(files)]
        except Exception:
            chosen = []
        if len(chosen) < 2:
            print("❌ 至少选择两个文件")
            return
        merged = []
        for name in chosen:
            path = os.path.join(raw_dir, name)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict) and 'contacts' in data:
                        merged.extend(data['contacts'])
                    elif isinstance(data, list):
                        merged.extend(data)
            except Exception as e:
                print(f"⚠️ 读取失败 {name}: {e}")
        if not merged:
            print("❌ 合并后为空")
            return
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        out_name = f"merged_contacts_{ts}.json"
        out_path = os.path.join(raw_dir, out_name)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        print(f"✅ 已生成: {out_path} (合并 {len(chosen)} 个文件, 总计 {len(merged)} 条)")

    def _export_raw_to_csv(self):
        raw_dir = os.path.join(project_root, 'data', 'raw')
        os.makedirs(raw_dir, exist_ok=True)
        files = [f for f in os.listdir(raw_dir) if f.endswith('.json')]
        if not files:
            print("❌ raw 目录没有JSON文件")
            return
        print("\n📁 可转换的 raw JSON 文件：")
        width = len(str(len(files)))
        for i, f in enumerate(files, 1):
            print(f"  {i:>{width}}. {f}")
        choice = input("选择一个文件编号: ").strip()
        try:
            i = int(choice) - 1
            if i < 0 or i >= len(files):
                print("❌ 编号无效")
                return
        except Exception:
            print("❌ 编号无效")
            return
        path = os.path.join(raw_dir, files[i])
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        contacts = data.get('contacts') if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if not contacts:
            print("❌ 文件中无 contacts 数据（期望为列表或包含 'contacts' 字段）")
            return
        import csv
        out_name = files[i].rsplit('.', 1)[0] + '.csv'
        out_path = os.path.join(raw_dir, out_name)
        keys = sorted({k for c in contacts for k in c.keys()})
        with open(out_path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for c in contacts:
                w.writerow(c)
        print(f"✅ 已导出 CSV: {out_path} (共 {len(contacts)} 条)")

    def _export_raw_to_sql(self):
        raw_dir = os.path.join(project_root, 'data', 'raw')
        os.makedirs(raw_dir, exist_ok=True)
        files = [f for f in os.listdir(raw_dir) if f.endswith('.json')]
        if not files:
            print("❌ raw 目录没有JSON文件")
            return
        print("\n📁 可转换的 raw JSON 文件：")
        width = len(str(len(files)))
        for i, f in enumerate(files, 1):
            print(f"  {i:>{width}}. {f}")
        choice = input("选择一个文件编号: ").strip()
        try:
            i = int(choice) - 1
            if i < 0 or i >= len(files):
                print("❌ 编号无效")
                return
        except Exception:
            print("❌ 编号无效")
            return
        path = os.path.join(raw_dir, files[i])
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        contacts = data.get('contacts') if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if not contacts:
            print("❌ 文件中无 contacts 数据（期望为列表或包含 'contacts' 字段）")
            return
        # 生成 SQL（CREATE TABLE + INSERT）
        def sql_escape(value: str) -> str:
            return value.replace("'", "''")
        # 收集列
        columns = sorted({k for c in contacts for k in c.keys()})
        # 将复杂类型转为 JSON 字符串
        def normalize(v):
            if v is None:
                return None
            if isinstance(v, (str, int, float)):
                return v
            try:
                return json.dumps(v, ensure_ascii=False)
            except Exception:
                return str(v)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        out_name = files[i].rsplit('.', 1)[0] + f'_{ts}.sql'
        out_path = os.path.join(raw_dir, out_name)
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write("BEGIN TRANSACTION;\n")
            # 简单统一 TEXT 类型表结构
            cols_def = ", ".join([f'"{c}" TEXT' for c in columns])
            f.write(f"CREATE TABLE IF NOT EXISTS contacts (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols_def});\n")
            for row in contacts:
                values = []
                for c in columns:
                    val = normalize(row.get(c))
                    if val is None:
                        values.append("NULL")
                    else:
                        values.append(f"'{sql_escape(str(val))}'")
                cols_str = ", ".join([f'"{c}"' for c in columns])
                vals_str = ", ".join(values)
                f.write(f"INSERT INTO contacts ({cols_str}) VALUES ({vals_str});\n")
            f.write("COMMIT;\n")
        print(f"✅ 已导出 SQL 文件: {out_path} (共 {len(contacts)} 条)")

    def _export_processed_to_csv(self):
        proc_dir = os.path.join(project_root, 'data', 'processed')
        os.makedirs(proc_dir, exist_ok=True)
        files = [f for f in os.listdir(proc_dir) if f.endswith('.json')]
        if not files:
            print("❌ processed 目录没有JSON文件")
            return
        print("\n📁 可转换的 processed JSON 文件：")
        width = len(str(len(files)))
        for i, f in enumerate(files, 1):
            print(f"  {i:>{width}}. {f}")
        choice = input("选择一个文件编号: ").strip()
        try:
            i = int(choice) - 1
            if i < 0 or i >= len(files):
                print("❌ 编号无效")
                return
        except Exception:
            print("❌ 编号无效")
            return
        path = os.path.join(proc_dir, files[i])
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        contacts = data.get('contacts') if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if not contacts:
            print("❌ 文件中无 contacts 数据")
            return
        import csv
        out_name = files[i].rsplit('.', 1)[0] + '.csv'
        out_path = os.path.join(proc_dir, out_name)
        keys = sorted({k for c in contacts for k in c.keys()})
        with open(out_path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for c in contacts:
                w.writerow(c)
        print(f"✅ 已导出 CSV: {out_path} (共 {len(contacts)} 条)")

    def _export_processed_to_sqlite(self):
        proc_dir = os.path.join(project_root, 'data', 'processed')
        os.makedirs(proc_dir, exist_ok=True)
        files = [f for f in os.listdir(proc_dir) if f.endswith('.json')]
        if not files:
            print("❌ processed 目录没有JSON文件")
            return
        print("\n📁 可转换的 processed JSON 文件：")
        width = len(str(len(files)))
        for i, f in enumerate(files, 1):
            print(f"  {i:>{width}}. {f}")
        choice = input("选择一个文件编号: ").strip()
        try:
            i = int(choice) - 1
            if i < 0 or i >= len(files):
                print("❌ 编号无效")
                return
        except Exception:
            print("❌ 编号无效")
            return
        path = os.path.join(proc_dir, files[i])
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        contacts = data.get('contacts') if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if not contacts:
            print("❌ 文件中无 contacts 数据")
            return
        import sqlite3
        db_path = os.path.join(proc_dir, files[i].rsplit('.', 1)[0] + '.db')
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS contacts (" 
                        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                        "name TEXT, title TEXT, company TEXT, location TEXT, linkedin_url TEXT, raw TEXT)")
            for c in contacts:
                cur.execute(
                    "INSERT INTO contacts (name, title, company, location, linkedin_url, raw) VALUES (?,?,?,?,?,?)",
                    (
                        c.get('name',''), c.get('title',''), c.get('company',''),
                        c.get('location',''), c.get('linkedin_url',''), json.dumps(c, ensure_ascii=False)
                    )
                )
            conn.commit()
        print(f"✅ 已导出 SQLite: {db_path} (共 {len(contacts)} 条)")

    def trim_processed_contacts(self) -> bool:
        """精简 processed/ 下最新 llm_filtered_contacts_*.json 为所需字段，并从 raw/ 下 merged_ 源补全 linkedin_url。
        输出 processed/trimmed_contacts_YYYYMMDD_HHMMSS.json
        """
        try:
            import re
            processed_dir = os.path.join(project_root, 'data', 'processed')
            raw_dir = os.path.join(project_root, 'data', 'raw')
            os.makedirs(processed_dir, exist_ok=True)
            os.makedirs(raw_dir, exist_ok=True)

            # 定位最新筛选文件
            candidates = []
            for fn in os.listdir(processed_dir):
                if fn.startswith('llm_filtered_contacts_') and fn.endswith('.json'):
                    fp = os.path.join(processed_dir, fn)
                    candidates.append((fp, os.path.getmtime(fp)))
            if not candidates:
                print('❌ 未找到 processed/ 下的 llm_filtered_contacts_*.json')
                return False
            candidates.sort(key=lambda x: x[1], reverse=True)
            latest_path = candidates[0][0]
            print(f"📂 使用最新筛选文件: {os.path.basename(latest_path)}")

            # 读取筛选数据
            with open(latest_path, 'r', encoding='utf-8') as f:
                pdata = json.load(f)
            if isinstance(pdata, dict):
                contacts = pdata.get('contacts') or pdata.get('filtered_contacts') or []
            elif isinstance(pdata, list):
                contacts = pdata
            else:
                contacts = []
            if not contacts:
                print('❌ 筛选文件中未找到联系人列表')
                return False

            # 定位 raw/ 下最新 merged_contacts_*.json
            merged_cand = []
            for fn in os.listdir(raw_dir):
                if fn.startswith('merged_contacts_') and fn.endswith('.json'):
                    fp = os.path.join(raw_dir, fn)
                    merged_cand.append((fp, os.path.getmtime(fp)))
            merged_path = None
            if merged_cand:
                merged_cand.sort(key=lambda x: x[1], reverse=True)
                merged_path = merged_cand[0][0]
                print(f"🔗 匹配来源: {os.path.basename(merged_path)}")
            else:
                print('⚠️ raw/ 下未找到 merged_contacts_*.json，将仅做字段精简，不补 URL')

            # 构建匹配索引
            def norm(s: str) -> str:
                if not s:
                    return ''
                return re.sub(r'\s+', ' ', str(s)).strip().lower()
            index_name_company = {}
            index_name_title = {}
            index_name_only = {}
            if merged_path:
                try:
                    with open(merged_path, 'r', encoding='utf-8') as f:
                        mdata = json.load(f)
                    if isinstance(mdata, dict):
                        mcontacts = mdata.get('contacts') or mdata.get('data') or []
                    elif isinstance(mdata, list):
                        mcontacts = mdata
                    else:
                        mcontacts = []
                    for c in mcontacts:
                        n = norm(c.get('name'))
                        comp = norm(c.get('company'))
                        tit = norm(c.get('title'))
                        url = c.get('linkedin_url') or c.get('url') or ''
                        if url:
                            if n and comp:
                                index_name_company.setdefault((n, comp), url)
                            if n and tit:
                                index_name_title.setdefault((n, tit), url)
                            if n:
                                index_name_only.setdefault(n, set()).add(url)
                except Exception as e:
                    print(f"⚠️ 读取匹配来源失败：{e}，将仅做字段精简")
                    merged_path = None

            # 精简并补回 URL
            trimmed = []
            enriched = unchanged = unmatched = 0
            for c in contacts:
                name = c.get('name') or c.get('Name') or ''
                title = c.get('title') or c.get('Title') or ''
                company = c.get('company') or c.get('Company') or ''
                location = c.get('location') or c.get('Location') or ''
                url = c.get('linkedin_url') or c.get('url') or ''
                score = c.get('match_score') if isinstance(c.get('match_score'), (int, float)) else c.get('total_score')
                try:
                    score = float(score) if score is not None else None
                except Exception:
                    score = None

                if (not url) and merged_path:
                    key_nc = (norm(name), norm(company))
                    key_nt = (norm(name), norm(title))
                    guess = index_name_company.get(key_nc) or index_name_title.get(key_nt)
                    if not guess and norm(name) in index_name_only:
                        urls = list(index_name_only.get(norm(name)) or [])
                        if len(urls) == 1:
                            guess = urls[0]
                    if guess:
                        url = guess
                        enriched += 1
                    else:
                        unmatched += 1
                else:
                    unchanged += 1

                trimmed.append({
                    'name': name,
                    'title': title,
                    'company': company,
                    'location': location,
                    'linkedin_url': url,
                    'match_score': score if score is not None else 0.0,
                })

            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            out_path = os.path.join(processed_dir, f'trimmed_contacts_{ts}.json')
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(trimmed, f, ensure_ascii=False, indent=2)
            print(f"✅ 已输出精简文件: {out_path}")
            if merged_path:
                print(f"🔎 URL 补全统计：新增 {enriched}，原有 {unchanged}，未匹配 {unmatched}")
            return True
        except Exception as e:
            print(f"❌ 精简失败: {e}")
            return False
    
    def backup_system(self):
        """备份系统"""
        try:
            if not self.controller or not self.controller.is_initialized:
                print("❌ 请先初始化系统")
                return
            
            print("💾 正在备份系统数据...")
            
            if self.controller.backup_system():
                print("✅ 系统备份完成")
            else:
                print("❌ 系统备份失败")
                
        except Exception as e:
            print(f"❌ 备份失败: {e}")
    
    def import_trimmed_to_db(self) -> bool:
        """导入 processed/trimmed_contacts_*.json 到数据库 contacts 表（去重基于 linkedin_url）。"""
        try:
            if not self.controller or not self.controller.is_initialized:
                print("❌ 请先初始化系统")
                return False
            processed_dir = os.path.join(project_root, 'data', 'processed')
            if not os.path.exists(processed_dir):
                print("❌ 目录不存在: data/processed")
                return False
            # 找到最新的 trimmed_contacts_*.json
            candidates = []
            for fn in os.listdir(processed_dir):
                if fn.startswith('trimmed_contacts_') and fn.endswith('.json'):
                    fp = os.path.join(processed_dir, fn)
                    candidates.append((fp, os.path.getmtime(fp)))
            if not candidates:
                print("❌ 未找到 processed/ 下的 trimmed_contacts_*.json，请先运行 trim 命令")
                return False
            candidates.sort(key=lambda x: x[1], reverse=True)
            latest_path = candidates[0][0]
            print(f"📂 使用文件: {os.path.basename(latest_path)}")
            stats = self.controller.database_manager.import_trimmed_json(latest_path)
            print(f"✅ 导入完成: 导入 {stats.get('imported',0)}, 更新 {stats.get('updated',0)}, 跳过 {stats.get('skipped',0)}, 错误 {stats.get('errors',0)}")
            return True
        except Exception as e:
            print(f"❌ 导入失败: {e}")
            return False

    def queue_connect_requests(self) -> bool:
        """从 contacts 中按分数挑选待触达并写入 marketing_records（pending）。"""
        try:
            if not self.controller or not self.controller.is_initialized:
                print("❌ 请先初始化系统")
                return False
            # 输入阈值与数量
            min_score = 0.0
            limit = 50
            try:
                inp = input("请输入最低分数阈值（默认0.0）: ").strip()
                if inp:
                    min_score = float(inp)
            except Exception:
                pass
            try:
                inp = input("请输入排队数量（默认50）: ").strip()
                if inp:
                    limit = int(inp)
            except Exception:
                pass
            message = input("请输入连接消息（可留空，稍后可在发送器中覆盖）: ").strip()
            stats = self.controller.database_manager.enqueue_connect_requests(message=message, limit=limit, min_score=min_score)
            print(f"✅ 已排队: {stats.get('queued',0)}，跳过: {stats.get('skipped',0)}")
            return True
        except Exception as e:
            print(f"❌ 排队失败: {e}")
            return False

    def send_connect_via_mcp(self) -> bool:
        """通过 Chrome MCP 读取数据库中满足阈值的联系人，逐个发起连接请求并写回 marketing_records。"""
        try:
            if not self.controller or not self.controller.is_initialized:
                print("❌ 请先初始化系统")
                return False

            import sqlite3

            # 询问阈值与数量
            min_score = 0.6
            limit = 10
            try:
                s = input("最低分数阈值（默认0.6）: ").strip()
                if s:
                    min_score = float(s)
            except Exception:
                pass
            try:
                s = input("发送数量（默认10）: ").strip()
                if s:
                    limit = int(s)
            except Exception:
                pass

            # 从数据库获取候选人（排除已 pending/sent/accepted 的 connect 记录）
            targets = self.controller.database_manager.get_contacts_for_outreach(limit=limit, min_score=min_score)
            if not targets:
                print("⚠️ 没有可发送的联系人（可能都已排队或阈值过高）")
                return False

            # 连接消息
            default_msg = "您好 {name}，我关注您在 {company} 的经验，期待与您建立联系。"
            message = input(f"连接消息（可留空使用默认）：\n默认: {default_msg}\n> ").strip()
            print()
            stats = {"sent": 0, "failed": 0}

            # 逐个调用营销自动化（内部通过 MCP）
            for c in targets:
                msg = message or default_msg.format(
                    name=c.get('name',''), company=c.get('company','')
                )
                ok = self.controller.marketing_automation._send_single_connection_request_via_mcp(c, msg)
                # 写回 marketing_records
                with sqlite3.connect(self.controller.database_manager.db_path) as conn:
                    cur = conn.cursor()
                    if ok:
                        cur.execute(
                            "INSERT INTO marketing_records (contact_id, action_type, status, message, sent_at, created_at) VALUES (?, 'connect', 'sent', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                            (c['id'], msg),
                        )
                        stats["sent"] += 1
                    else:
                        cur.execute(
                            "INSERT INTO marketing_records (contact_id, action_type, status, message, error, created_at) VALUES (?, 'connect', 'failed', ?, ?, CURRENT_TIMESTAMP)",
                            (c['id'], msg, 'mcp send failed'),
                        )
                        stats["failed"] += 1
                    conn.commit()

            print(f"✅ 完成：发送 {stats['sent']}，失败 {stats['failed']}")
            return True
        except Exception as e:
            print(f"❌ 发送失败: {e}")
            return False

    def cleanup_data(self, days: int = 30):
        """清理旧数据"""
        try:
            if not self.controller or not self.controller.is_initialized:
                print("❌ 请先初始化系统")
                return
            
            print(f"🧹 正在清理 {days} 天前的旧数据...")
            
            cleaned_count = self.controller.cleanup_old_data(days)
            print(f"✅ 清理完成，共清理 {cleaned_count} 条记录")
                
        except Exception as e:
            print(f"❌ 清理失败: {e}")
    
    def generate_report(self) -> bool:
        """生成筛选结果分析报告"""
        try:
            from src.utils.report_generator import FilterReportGenerator
            
            # 查找最新的筛选结果文件
            processed_dir = os.path.join(project_root, 'data', 'processed')
            if not os.path.exists(processed_dir):
                print("❌ 没有找到processed目录")
                return False
            
            # 查找筛选结果文件
            filter_files = []
            for file in os.listdir(processed_dir):
                if ('filtered_contacts' in file or 'contacts' in file) and file.endswith('.json'):
                    file_path = os.path.join(processed_dir, file)
                    filter_files.append((file_path, os.path.getmtime(file_path), file))
            
            if not filter_files:
                print("❌ 没有找到筛选结果文件")
                print("💡 请先使用 'filter' 命令进行联系人筛选")
                return False
            
            # 按修改时间排序，显示可用文件
            filter_files.sort(key=lambda x: x[1], reverse=True)
            
            print("\n📋 可用的筛选结果文件:")
            for i, (file_path, mtime, filename) in enumerate(filter_files[:5]):
                mod_time = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                print(f"  {i+1}. {filename} ({mod_time})")
            
            # 让用户选择文件或使用最新的
            choice = input("\n请选择文件编号 (直接回车使用最新文件): ").strip()
            
            if choice:
                try:
                    file_index = int(choice) - 1
                    if 0 <= file_index < len(filter_files):
                        selected_file = filter_files[file_index][0]
                        selected_filename = filter_files[file_index][2]
                    else:
                        print("❌ 无效的文件编号")
                        return False
                except ValueError:
                    print("❌ 请输入有效的数字")
                    return False
            else:
                selected_file = filter_files[0][0]
                selected_filename = filter_files[0][2]
            
            print(f"\n📂 正在处理文件: {selected_filename}")
            
            # 加载筛选结果数据
            with open(selected_file, 'r', encoding='utf-8') as f:
                filter_data = json.load(f)
            
            # 提取联系人列表
            if 'filtered_contacts' in filter_data:
                contacts = filter_data['filtered_contacts']
            elif 'contacts' in filter_data:
                contacts = filter_data['contacts']
            elif isinstance(filter_data, list):
                contacts = filter_data
            else:
                print("❌ 无法识别文件格式")
                return False
            
            print(f"✅ 成功加载 {len(contacts)} 个联系人")
            
            # 生成报告
            print("🔄 正在生成分析报告...")
            
            report_generator = FilterReportGenerator()
            
            # 从文件数据中提取参数
            original_count = filter_data.get('metadata', {}).get('original_count', len(contacts))
            min_score = filter_data.get('filter_config', {}).get('min_score', 0.3)
            filter_config = filter_data.get('filter_config', {})
            processing_time = filter_data.get('metadata', {}).get('processing_time', 0)
            
            report_path = report_generator.generate_filter_report(
                filtered_contacts=contacts,
                original_count=original_count,
                min_score=min_score,
                filter_config=filter_config,
                processing_time=processing_time
            )
            
            print("\n🎉 报告生成成功!")
            print(f"📄 报告文件: {os.path.basename(report_path)}")
            print(f"📊 分析了 {len(contacts)} 个筛选后的联系人")
            
            # 显示统计信息
            if contacts:
                scores = [c.get('match_score', 0) for c in contacts]
                avg_score = sum(scores) / len(scores)
                max_score = max(scores)
                min_score_actual = min(scores)
                
                print(f"🎯 平均分数: {avg_score:.3f}")
                print(f"🏆 最高分数: {max_score:.3f}")
                print(f"📉 最低分数: {min_score_actual:.3f}")
            
            print(f"📍 报告位置: {report_path}")
            
            return True
            
        except Exception as e:
            print(f"❌ 生成报告失败: {e}")
            self.logger.error(f"Generate report error: {e}")
            return False
    
    def run_interactive(self):
        """运行交互式命令行界面"""
        self.print_banner()
        print("\n🎉 欢迎使用LinkedIn营销自动化系统!")
        print("💡 输入 'help' 查看使用指南，输入 'quit' 退出系统\n")
        
        # 存储最近的筛选结果
        last_filtered_contacts = []
        
        while True:
            try:
                # 获取用户输入
                command = input("LinkedIn营销系统 > ").strip()
                
                if not command:
                    continue
                
                # 解析命令
                parts = command.split(' ', 1)
                cmd = re.sub(r'^[^a-zA-Z0-9_-]+', '', parts[0]).lower()
                args = parts[1] if len(parts) > 1 else ''
                known_commands = [
                    'quit', 'exit', 'help', 'init', 'start', 'scrape', 'scrape-llm',
                    'scrape-sales', 'filter', 'report', 'trim', 'connect',
                    'queue-connect', 'status', 'backup', 'cleanup', 'export',
                    'import-db'
                ]
                if cmd not in known_commands:
                    for candidate in known_commands:
                        if cmd == candidate[1:]:
                            cmd = candidate
                            break
                
                # 执行命令
                if cmd in ['quit', 'exit']:
                    break
                elif cmd == 'help':
                    self.print_help()
                elif cmd == 'init':
                    self.initialize_system()
                elif cmd == 'start':
                    self.start_browser()
                elif cmd == 'scrape':
                    opts = self._parse_inline_options(args)
                    keywords_text = opts.get('keywords')
                    pages = opts.get('pages')
                    max_pages = None
                    if pages:
                        try:
                            max_pages = int(pages)
                        except Exception:
                            max_pages = None
                    self.scrape_contacts(search_input=keywords_text, max_pages=max_pages)
                elif cmd == 'scrape-llm':
                    self.scrape_llm_from_file()
                elif cmd == 'scrape-sales':
                    opts = self._parse_inline_options(args)
                    pages = opts.get('pages')
                    max_pages = None
                    if pages:
                        try:
                            max_pages = int(pages)
                        except Exception:
                            max_pages = None
                    self.scrape_sales_navigator(max_pages=max_pages)
                elif cmd == 'filter':
                    last_filtered_contacts = self.filter_contacts()
                elif cmd == 'report':
                    self.generate_report()
                elif cmd == 'trim':
                    self.trim_processed_contacts()
                elif cmd == 'connect':
                    # 新版 connect：进入交互式辅助流程（可选：通过参数预设招呼语）
                    pre_msg = args.strip('"\'') if args else None
                    self.connect_assisted_flow(pre_msg)
                elif cmd == 'email':
                    if not args:
                        print("❌ 请提供邮件主题和内容，例如: email \"合作邀请\" \"邮件内容\"")
                        continue
                    # 解析主题和内容
                    try:
                        import shlex
                        email_parts = shlex.split(args)
                        if len(email_parts) >= 2:
                            subject, body = email_parts[0], email_parts[1]
                            self.send_emails(subject, body, last_filtered_contacts)
                        else:
                            print("❌ 请提供邮件主题和内容")
                    except:
                        print("❌ 邮件参数解析失败，请检查格式")
                elif cmd == 'status':
                    self.show_status()
                elif cmd == 'export':
                    export_type = args.lower().strip() if args else ''
                    if export_type in ['json', 'csv']:
                        self.export_data(export_type)
                    else:
                        # 无参数或无效参数：进入交互式导出/转换菜单
                        self.export_data('menu')
                elif cmd == 'views-init':
                    self.init_default_views()
                elif cmd == 'backup':
                    self.backup_system()
                elif cmd == 'cleanup':
                    days = 30
                    if args and args.isdigit():
                        days = int(args)
                    self.cleanup_data(days)
                elif cmd == 'import-db':
                    self.import_trimmed_to_db()
                elif cmd == 'queue-connect':
                    self.queue_connect_requests()
                elif cmd == 'journey':
                    self._print_pipeline_guide()
                elif cmd == 'send-connect-mcp':
                    print("❌ 命令已废弃。请使用 'connect' 进入交互式流程。")
                else:
                    print(f"❌ 未知命令: {cmd}")
                    print("💡 输入 'help' 查看可用命令")
                
                print()  # 空行分隔
                
            except KeyboardInterrupt:
                print("\n\n👋 检测到中断信号，正在退出...")
                break
            except Exception as e:
                print(f"❌ 命令执行失败: {e}")
                print("💡 输入 'help' 查看使用指南\n")
        
        # 清理资源
        if self.controller:
            print("🧹 正在清理系统资源...")
            self.controller.shutdown()
        
        print("👋 感谢使用LinkedIn营销自动化系统!")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='LinkedIn营销自动化系统')
    parser.add_argument('--quick-start', action='store_true', help='快速启动系统')
    parser.add_argument('--project-root', type=str, help='项目根目录')
    
    args = parser.parse_args()
    
    # 设置项目根目录
    if args.project_root:
        global project_root
        project_root = args.project_root
    
    cli = LinkedInMarketingCLI()
    
    if args.quick_start:
        # 快速启动模式
        print("🚀 快速启动LinkedIn营销系统...")
        controller = quick_start(project_root)
        cli.controller = controller
    
    # 运行交互式界面
    cli.run_interactive()

if __name__ == '__main__':
    main()
