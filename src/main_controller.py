import os
import json
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

from .utils.logger import get_logger, SessionLogger
from .utils.config_loader import ConfigLoader
from .utils.helpers import save_json_file, load_json_file
from .utils.report_generator import FilterReportGenerator
from .utils.lazy_loader import component_manager, timing_monitor

# 可选导入，避免依赖问题
try:
    from .data_manager.database_manager import DatabaseManager
except ImportError:
    DatabaseManager = None

try:
    from .filter.contact_filter import ContactFilter as SmartFilterV3
except ImportError:
    SmartFilterV3 = None

try:
    from .marketing.automation import MarketingAutomation
except ImportError:
    MarketingAutomation = None

class LinkedInMarketingController:
    """LinkedIn营销系统主控制器"""
    
    @timing_monitor("主控制器初始化")
    def __init__(self, project_root: str = None):
        """初始化主控制器（优化版 - 延迟加载）
        
        Args:
            project_root: 项目根目录
        """
        self.project_root = project_root or os.getcwd()
        
        # 初始化配置（立即加载）
        config_dir = os.path.join(self.project_root, "config")
        self.config_loader = ConfigLoader(config_dir)
        
        # 初始化日志（使用配置文件设置）
        try:
            settings = self.config_loader.load_settings()
            log_config = settings.get('logging', {})
        except Exception:
            log_config = {}
        self.logger = get_logger("main_controller", log_config)
        self.session_logger = None  # 将在需要时创建
        
        # 立即初始化的轻量级组件
        self.report_generator = FilterReportGenerator(self.project_root)
        
        # 延迟加载的重型组件（仅在需要时加载）
        self._browser_manager = None
        self._scraper = None
        self._contact_manager = None
        self._database_manager = None
        # self._smart_filter = None  # 旧版已弃用
        self._smart_filter_v3 = None
        self._marketing_automation = None
        
        # 组件加载状态
        self._components_loaded = {
            'browser_manager': False,
            'scraper': False,
            'contact_manager': False,
            'database_manager': False,
            'smart_filter_v3': False,
            'marketing_automation': False
        }
        
        # 系统状态
        self.is_initialized = False
        self.current_session = None
        
        # 注册组件到延迟加载器
        self._register_components()
        
        self.logger.info(f"LinkedIn营销系统控制器快速初始化完成，项目根目录: {self.project_root}")
    
    def _register_components(self):
        """注册组件到延迟加载管理器"""
        # 注册各个组件的加载函数
        component_manager.register_component(
            'contact_manager',
            self._load_contact_manager,
            priority=1  # 高优先级
        )
        
        component_manager.register_component(
            'smart_filter_v3',
            self._load_smart_filter_v3,
            priority=2
        )
        
        component_manager.register_component(
            'browser_manager',
            self._load_browser_manager,
            priority=3
        )
        
        component_manager.register_component(
            'scraper',
            self._load_scraper,
            priority=4
        )
        
        component_manager.register_component(
            'marketing_automation',
            self._load_marketing_automation,
            priority=5  # 低优先级
        )
    
    # 延迟加载的属性访问器
    @property
    def browser_manager(self):
        """延迟加载浏览器管理器"""
        if not self._components_loaded['browser_manager']:
            self._browser_manager = component_manager.get_component('browser_manager')
            self._components_loaded['browser_manager'] = True
        return self._browser_manager
    
    @property
    def scraper(self):
        """延迟加载LinkedIn爬虫"""
        if not self._components_loaded['scraper']:
            self._scraper = component_manager.get_component('scraper')
            self._components_loaded['scraper'] = True
        return self._scraper
    
    @property
    def contact_manager(self):
        """延迟加载联系人管理器"""
        if not self._components_loaded['contact_manager']:
            self._contact_manager = component_manager.get_component('contact_manager')
            self._components_loaded['contact_manager'] = True
        return self._contact_manager
    
    @property
    def smart_filter_v3(self):
        """延迟加载智能筛选器V3"""
        if not self._components_loaded['smart_filter_v3']:
            self._smart_filter_v3 = component_manager.get_component('smart_filter_v3')
            self._components_loaded['smart_filter_v3'] = True
        return self._smart_filter_v3
    
    @property
    def marketing_automation(self):
        """延迟加载营销自动化模块"""
        if not self._components_loaded['marketing_automation']:
            self._marketing_automation = component_manager.get_component('marketing_automation')
            self._components_loaded['marketing_automation'] = True
        return self._marketing_automation
    
    # 组件加载方法
    @timing_monitor("加载联系人管理器")
    def _load_contact_manager(self):
        """加载联系人管理器"""
        try:
            from src.data_manager.contact_manager import ContactManager
            # 优先使用 settings.json 的 database.path
            try:
                db_rel = self.config_loader.get_setting('database.path')
            except Exception:
                db_rel = None
            if db_rel:
                db_path = db_rel if os.path.isabs(db_rel) else os.path.join(self.project_root, db_rel)
            else:
                db_path = os.path.join(self.project_root, 'database', 'contacts.db')
            data_dir = os.path.join(self.project_root, 'data')
            return ContactManager(db_path=db_path, data_dir=data_dir)
        except Exception as e:
            self.logger.error(f"加载联系人管理器失败: {e}")
            return None
    
    @timing_monitor("加载智能筛选器V3")
    def _load_smart_filter_v3(self):
        """加载智能筛选器V3"""
        try:
            from src.filter.contact_filter import ContactFilter
            return ContactFilter()
        except Exception as e:
            self.logger.error(f"加载智能筛选器V3失败: {e}")
            return None
    
    @timing_monitor("加载浏览器管理器")
    def _load_browser_manager(self):
        """加载浏览器管理器"""
        try:
            from src.scraper.browser_manager import BrowserManager
            return BrowserManager()
        except Exception as e:
            self.logger.error(f"加载浏览器管理器失败: {e}")
            return None
    
    @timing_monitor("加载LinkedIn爬虫")
    def _load_scraper(self):
        """加载LinkedIn爬虫"""
        try:
            from src.scraper.linkedin_scraper import LinkedInScraper
            config_dir = os.path.join(self.project_root, 'config')
            scraper = LinkedInScraper(config_dir)
            # 初始化爬虫
            if not scraper.initialize():
                self.logger.error("LinkedIn爬虫初始化失败")
                return None
            return scraper
        except Exception as e:
            self.logger.error(f"加载LinkedIn爬虫失败: {e}")
            return None
    
    @timing_monitor("加载营销自动化模块")
    def _load_marketing_automation(self):
        """加载营销自动化模块"""
        try:
            # 修正错误的导入路径
            from src.marketing.automation import MarketingAutomation
            try:
                db_rel = self.config_loader.get_setting('database.path')
            except Exception:
                db_rel = None
            if db_rel:
                db_path = db_rel if os.path.isabs(db_rel) else os.path.join(self.project_root, db_rel)
            else:
                db_path = os.path.join(self.project_root, 'database', 'contacts.db')
            return MarketingAutomation(
                db_path=db_path,
                config_loader=self.config_loader,
                browser_manager=self.browser_manager
            )
        except Exception as e:
            self.logger.error(f"加载营销自动化模块失败: {e}")
            return None
    
    @timing_monitor("系统初始化")
    def initialize_system(self) -> bool:
        """初始化整个系统（延迟加载优化版）
        
        Returns:
            是否初始化成功
        """
        try:
            self.logger.info("开始快速初始化LinkedIn营销系统...")
            
            # 检查项目结构
            if not self._check_project_structure():
                self.logger.error("项目结构检查失败")
                return False
            
            # 初始化数据库管理器（立即加载，轻量级）
            if DatabaseManager is not None:
                try:
                    db_rel = self.config_loader.get_setting('database.path')
                except Exception:
                    db_rel = None
                if db_rel:
                    db_path = db_rel if os.path.isabs(db_rel) else os.path.join(self.project_root, db_rel)
                else:
                    db_path = os.path.join(self.project_root, 'database', 'contacts.db')
                self._database_manager = DatabaseManager(db_path)
                self.logger.info("数据库管理器初始化成功")
            else:
                self.logger.warning("DatabaseManager不可用，跳过数据库初始化")
                self._database_manager = None
            
            # 初始化会话日志记录器（立即加载，轻量级）
            self.session_logger = self.logger.create_session_log("main_session")
            
            # 预热核心组件（可选，用于提前检查依赖）
            self._preload_critical_components()
            
            self.is_initialized = True
            self.logger.info("LinkedIn营销系统快速初始化完成（组件将按需加载）")
            return True
            
        except Exception as e:
            self.logger.error(f"系统初始化失败: {e}")
            return False
    
    def _preload_critical_components(self):
        """预加载关键组件以检查依赖性"""
        try:
            # 检查智能筛选器V3是否可用（不实际加载）
            if SmartFilterV3 is None:
                self.logger.warning("SmartFilterV3不可用，某些功能可能受限")
            
            # 检查其他关键依赖
            critical_paths = [
                os.path.join(self.project_root, 'config', 'settings.json'),
                os.path.join(self.project_root, 'data')
            ]
            
            for path in critical_paths:
                if not os.path.exists(path):
                    self.logger.warning(f"关键路径不存在: {path}")
            
            self.logger.info("关键组件依赖检查完成")
            
        except Exception as e:
            self.logger.warning(f"预加载检查时出现警告: {e}")
    
    @property
    def database_manager(self):
        """获取数据库管理器"""
        return self._database_manager
    
    def start_browser_session(self) -> bool:
        """启动浏览器会话
        
        Returns:
            是否启动成功
        """
        try:
            if not self.is_initialized:
                self.logger.error("系统未初始化")
                return False
            
            self.logger.info("启动浏览器会话...")
            
            # 启动浏览器
            if not self.browser_manager.setup_driver():
                self.logger.error("浏览器启动失败")
                return False
            
            # 导航到LinkedIn
            if not self.browser_manager.navigate_to_linkedin():
                self.logger.error("导航到LinkedIn失败")
                return False
            
            # 记录会话信息
            self.session_logger.info("浏览器会话启动成功")
            
            self.logger.info("浏览器会话启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"启动浏览器会话失败: {e}")
            return False
    
    def scrape_keywords(self, keywords: List[str] = None, max_results_per_keyword: int = None,
                        max_pages: int = 1, enrich_profiles: bool = True) -> Dict[str, Any]:
        """爬取关键词数据
        
        Args:
            keywords: 关键词列表，如果为None则使用配置文件中的关键词
            max_results_per_keyword: 每个关键词的最大结果数
            max_pages: 爬取页数
            enrich_profiles: 是否访问个人主页补全缺失的公司信息
        
        Returns:
            爬取结果统计
        """
        try:
            if not self.is_initialized or not self.browser_manager.driver:
                self.logger.error("系统未初始化或浏览器未启动")
                return {'success': False, 'error': '系统未初始化或浏览器未启动'}
            
            # 使用配置文件中的关键词（如果未提供）
            if not keywords:
                keyword_config = self.config_loader.get_keywords()
                keywords = keyword_config.get('keywords', [])
            
            if not keywords:
                self.logger.error("没有可用的搜索关键词")
                return {'success': False, 'error': '没有可用的搜索关键词'}
            
            self.logger.info(f"开始爬取关键词: {keywords}")
            
            # 记录爬取开始
            self.session_logger.info(f"开始爬取会话，关键词: {keywords}，每个关键词最大结果数: {max_results_per_keyword}，页数: {max_pages}")
            
            # 执行爬取（统一走 search_manager）
            results = {}
            for keyword in keywords:
                keyword_results = self.scraper.search_manager.search_people(
                    keyword,
                    max_results=max_results_per_keyword or (10 * max_pages),
                    max_pages=max_pages,
                    enrich_profiles=enrich_profiles,
                )
                results[keyword] = keyword_results
            
            # 将结果导入数据库
            import_stats = {'total_imported': 0, 'total_skipped': 0}
            
            for keyword, contacts in results.items():
                if contacts:
                    # 保存到单独的JSON文件
                    keyword_file = os.path.join(self.project_root, 'data', 'raw', f'{keyword}_contacts.json')
                    save_json_file(contacts, keyword_file)
                    
                    # 导入到数据库
                    if self.contact_manager is not None:
                        prepared = []
                        for contact in contacts:
                            # 兜底回补 linkedin_url：若缺失，尝试从文本推断或跳过
                            url = contact.get('linkedin_url') or ''
                            if not url:
                                # 尝试从 name 或 card 文本无法稳定推断，这里保守跳过入库
                                self.logger.debug(f"跳过入库（缺少linkedin_url）: {contact.get('name','')}")
                                import_stats['total_skipped'] += 1
                                continue
                            contact['search_keyword'] = keyword
                            prepared.append(contact)
                        if prepared:
                            batch_stats = self.contact_manager.add_contacts(prepared)
                            import_stats['total_imported'] += batch_stats.get('added', 0) + batch_stats.get('updated', 0)
                            import_stats['total_skipped'] += batch_stats.get('skipped', 0)
                    else:
                        self.logger.warning("ContactManager未初始化，跳过数据库导入")
            
            #（移除）自动生成 processed/all_contacts.json
            # 合并请使用 CLI 的 export → 合并功能
            
            # 记录爬取结果（按关键词统计总数）
            total_contacts = sum(len(v) for v in results.values())
            self.session_logger.info(f"爬取会话结束，总联系人数: {total_contacts}，导入统计: {import_stats}")
            
            final_results = {
                'success': True,
                'keywords_processed': len(results),
                'total_contacts': total_contacts,
                'import_stats': import_stats,
                'results_by_keyword': {k: len(v) for k, v in results.items()}
            }
            
            self.logger.info(f"爬取完成: {final_results}")
            return final_results
            
        except Exception as e:
            self.logger.error(f"爬取关键词失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def filter_contacts(self, description: str = None, contacts: List[Dict] = None, 
                          min_score: float = 0.3, limit: int = None) -> List[Dict[str, Any]]:
        """使用V3引擎筛选联系人
        
        Args:
            description: 筛选描述（已弃用，V3使用配置文件中的规则）
            contacts: 联系人列表（如果为None，则从数据库获取）
            min_score: 最低匹配分数阈值
            limit: 结果数量限制
        
        Returns:
            筛选后的联系人列表
        """
        try:
            if not self.is_initialized:
                self.logger.error("系统未初始化")
                return []
            
            if self.smart_filter_v3 is None:
                self.logger.error("智能筛选器V3不可用")
                return []
            
            # 获取联系人数据
            if contacts is None:
                if self.contact_manager is not None:
                    contacts = self.contact_manager.get_all_contacts()
                    self.logger.info(f"从数据库获取到 {len(contacts)} 个联系人")
                else:
                    self.logger.error("联系人管理器不可用，无法获取联系人数据")
                    return []
            
            self.logger.info(f"开始V3智能筛选，联系人数: {len(contacts)}，最低分数: {min_score}")
            
            # 记录筛选开始
            self.session_logger.info(f"开始V3筛选会话，联系人数: {len(contacts)}，最低分数: {min_score}")
            
            # 执行V3筛选
            filtered_contacts, _ = self.smart_filter_v3.filter_contacts(
                contacts=contacts,
                requirements_input=description or "",
                min_score=min_score,
                require_llm=bool(description)
            )
            
            # 应用数量限制
            if limit and len(filtered_contacts) > limit:
                filtered_contacts = filtered_contacts[:limit]
            
            # 记录筛选结果
            self.session_logger.info(f"V3筛选会话结束，筛选出联系人数: {len(filtered_contacts)}")
            
            # 生成筛选分析报告
            try:
                report_path = self.report_generator.generate_filter_report(
                    filtered_contacts=filtered_contacts,
                    original_count=len(contacts),
                    min_score=min_score
                )
                self.logger.info(f"筛选分析报告已生成: {report_path}")
                self.session_logger.info(f"筛选分析报告已生成: {report_path}")
            except Exception as e:
                self.logger.warning(f"生成筛选分析报告失败: {e}")
            
            self.logger.info(f"V3筛选完成，找到 {len(filtered_contacts)} 个匹配的联系人")
            return filtered_contacts
            
        except Exception as e:
            self.logger.error(f"V3筛选联系人失败: {e}")
            return []

    def filter_contacts_from_data(self, contacts: List[Dict], min_score: float = 0.3, limit: int = None) -> List[Dict[str, Any]]:
        """从提供的联系人数据中筛选联系人
        
        Args:
            contacts: 联系人列表
            min_score: 最低匹配分数阈值
            limit: 结果数量限制
        
        Returns:
            筛选后的联系人列表
        """
        try:
            if not self.is_initialized:
                self.logger.error("系统未初始化")
                return []
            
            if self.smart_filter_v3 is None:
                self.logger.error("智能筛选器V3不可用")
                return []
            
            if not contacts:
                self.logger.warning("没有提供联系人数据")
                return []
            
            self.logger.info(f"开始V3智能筛选，联系人数: {len(contacts)}，最低分数: {min_score}")
            
            # 记录筛选开始
            if self.session_logger:
                self.session_logger.info(f"开始V3筛选会话，联系人数: {len(contacts)}，最低分数: {min_score}")
            
            # 执行V3筛选
            filtered_contacts, stats = self.smart_filter_v3.filter_contacts(
                contacts=contacts,
                requirements_input="",
                min_score=min_score,
                require_llm=False
            )
            
            # 应用数量限制
            if limit and len(filtered_contacts) > limit:
                filtered_contacts = filtered_contacts[:limit]
            
            # 记录筛选结果
            if self.session_logger:
                self.session_logger.info(f"V3筛选会话结束，筛选出联系人数: {len(filtered_contacts)}")
            
            # 生成筛选报告
            if self.report_generator:
                try:
                    report_path = self.report_generator.generate_filter_report(
                        filtered_contacts=filtered_contacts,
                        original_count=len(contacts),
                        min_score=min_score,
                        stats=stats
                    )
                    self.logger.info(f"筛选报告已生成: {report_path}")
                except Exception as e:
                    self.logger.warning(f"生成筛选报告失败: {e}")
            
            self.logger.info(f"V3筛选完成，找到 {len(filtered_contacts)} 个匹配的联系人")
            return filtered_contacts
            
        except Exception as e:
            self.logger.error(f"V3筛选联系人失败: {e}")
            return []

    def analyze_contact(self, contact_name: str) -> Dict:
        """使用V3引擎分析单个联系人
        
        Args:
            contact_name: 联系人姓名
            
        Returns:
            详细的分析结果
        """
        try:
            if not self.is_initialized:
                self.logger.error("系统未初始化")
                return {'error': '系统未初始化'}
            
            if self.smart_filter_v3 is None:
                self.logger.error("智能筛选器V3不可用")
                return {'error': '智能筛选器V3不可用'}
            
            # 从数据库查找联系人
            if self.contact_manager is None:
                self.logger.error("联系人管理器不可用")
                return {'error': '联系人管理器不可用'}
            
            contacts = self.contact_manager.get_all_contacts()
            contact = None
            
            # 查找匹配的联系人
            for c in contacts:
                if c.get('name', '').lower() == contact_name.lower():
                    contact = c
                    break
            
            if contact is None:
                self.logger.warning(f"未找到联系人: {contact_name}")
                return {'error': f'未找到联系人: {contact_name}'}
            
            self.logger.info(f"开始V3分析联系人: {contact.get('name', 'Unknown')}")
            
            # 执行分析
            analysis = self.smart_filter_v3.analyze_contact(contact)
            
            self.logger.info(f"V3分析完成，匹配分数: {analysis.get('final_scores', {}).get('match_score', 0)}")
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"V3分析联系人失败: {e}")
            return {'error': str(e)}
    
    def send_connection_requests(self, contacts: List[Dict[str, Any]], message: str = None) -> Dict[str, Any]:
        """发送LinkedIn连接请求
        
        Args:
            contacts: 联系人列表
            message: 连接消息
        
        Returns:
            发送结果统计
        """
        try:
            if not self.is_initialized or not self.browser_manager.driver:
                self.logger.error("系统未初始化或浏览器未启动")
                return {'success': False, 'error': '系统未初始化或浏览器未启动'}
            
            self.logger.info(f"开始发送 {len(contacts)} 个连接请求")
            
            # 记录营销开始
            self.session_logger.info(f"开始连接请求会话，联系人数: {len(contacts)}，消息预览: {message[:100] if message else None}")
            
            # 执行发送
            results = self.marketing_automation.send_connection_requests(contacts, message)
            
            # 记录营销结果
            self.session_logger.info(f"连接请求会话结束，结果: {results}")
            
            results['success'] = True
            self.logger.info(f"连接请求发送完成: {results}")
            return results
            
        except Exception as e:
            self.logger.error(f"发送连接请求失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def send_emails(self, contacts: List[Dict[str, Any]], subject: str, body: str) -> Dict[str, Any]:
        """发送邮件
        
        Args:
            contacts: 联系人列表
            subject: 邮件主题
            body: 邮件内容
        
        Returns:
            发送结果统计
        """
        try:
            if not self.is_initialized:
                self.logger.error("系统未初始化")
                return {'success': False, 'error': '系统未初始化'}
            
            self.logger.info(f"开始发送 {len(contacts)} 封邮件")
            
            # 记录邮件开始
            self.session_logger.info(f"开始邮件会话，联系人数: {len(contacts)}，主题: {subject}")
            
            # 执行发送
            results = self.marketing_automation.send_emails(contacts, subject, body)
            
            # 记录邮件结果
            self.session_logger.info(f"邮件会话结束，结果: {results}")
            
            results['success'] = True
            self.logger.info(f"邮件发送完成: {results}")
            return results
            
        except Exception as e:
            self.logger.error(f"发送邮件失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态
        
        Returns:
            系统状态信息
        """
        try:
            status = {
                'is_initialized': self.is_initialized,
                'browser_active': self.browser_manager and self.browser_manager.driver is not None,
                'current_session': self.current_session,
                'project_root': self.project_root
            }
            
            if self.is_initialized:
                # 数据库统计
                if self.database_manager:
                    status['database_stats'] = self.database_manager.get_database_stats()
                
                # 营销统计
                if self.marketing_automation:
                    status['marketing_stats'] = self.marketing_automation.get_marketing_statistics()
                
                # 筛选统计
                if self.smart_filter_v3:
                    status['filter_stats'] = {'filter_version': 'V3', 'available': True}
            
            return status
            
        except Exception as e:
            self.logger.error(f"获取系统状态失败: {e}")
            return {'error': str(e)}
    
    def export_data(self, export_type: str = 'json', filters: Dict[str, Any] = None) -> str:
        """导出数据
        
        Args:
            export_type: 导出类型 ('json' 或 'csv')
            filters: 过滤条件
        
        Returns:
            导出文件路径
        """
        try:
            if not self.is_initialized:
                self.logger.error("系统未初始化")
                return None
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            export_dir = os.path.join(self.project_root, 'data', 'exports')
            os.makedirs(export_dir, exist_ok=True)
            
            if export_type.lower() == 'csv':
                filename = f'contacts_export_{timestamp}.csv'
                filepath = os.path.join(export_dir, filename)
                success = self.database_manager.export_to_csv(filepath, filters)
            else:
                filename = f'contacts_export_{timestamp}.json'
                filepath = os.path.join(export_dir, filename)
                success = self.database_manager.export_to_json(filepath, filters)
            
            if success:
                self.logger.info(f"数据导出成功: {filepath}")
                return filepath
            else:
                self.logger.error("数据导出失败")
                return None
                
        except Exception as e:
            self.logger.error(f"导出数据失败: {e}")
            return None
    
    def backup_system(self) -> bool:
        """备份系统数据
        
        Returns:
            是否备份成功
        """
        try:
            if not self.is_initialized:
                self.logger.error("系统未初始化")
                return False
            
            self.logger.info("开始系统备份...")
            
            # 备份数据库
            db_backup_success = self.database_manager.backup_database()
            
            # 备份配置文件
            config_backup_success = self._backup_config_files()
            
            success = db_backup_success and config_backup_success
            
            if success:
                self.logger.info("系统备份完成")
            else:
                self.logger.error("系统备份失败")
            
            return success
            
        except Exception as e:
            self.logger.error(f"系统备份失败: {e}")
            return False
    
    def cleanup_old_data(self, days: int = 30) -> int:
        """清理旧数据
        
        Args:
            days: 保留天数
        
        Returns:
            清理的记录数
        """
        try:
            if not self.is_initialized:
                self.logger.error("系统未初始化")
                return 0
            
            self.logger.info(f"开始清理 {days} 天前的旧数据...")
            
            cleaned_count = self.database_manager.cleanup_old_data(days)
            
            self.logger.info(f"清理完成，共清理 {cleaned_count} 条记录")
            return cleaned_count
            
        except Exception as e:
            self.logger.error(f"清理旧数据失败: {e}")
            return 0
    
    def shutdown(self):
        """关闭系统"""
        try:
            self.logger.info("开始关闭LinkedIn营销系统...")
            
            # 记录系统关闭
            if self.session_logger:
                self.session_logger.info("系统正在关闭")
            
            # 关闭浏览器
            if self.browser_manager:
                self.browser_manager.cleanup()
            
            self.is_initialized = False
            self.logger.info("LinkedIn营销系统已关闭")
            
        except Exception as e:
            self.logger.error(f"关闭系统失败: {e}")
    
    def _check_project_structure(self) -> bool:
        """检查项目结构"""
        required_dirs = [
            'config',
            'data',
            'data/raw',
            'data/processed',
            'data/exports',
            'database',
            'src'
        ]
        
        for dir_path in required_dirs:
            full_path = os.path.join(self.project_root, dir_path)
            if not os.path.exists(full_path):
                self.logger.warning(f"创建缺失的目录: {full_path}")
                os.makedirs(full_path, exist_ok=True)
        
        return True
    
    def _backup_config_files(self) -> bool:
        """备份配置文件"""
        try:
            import shutil
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir = os.path.join(self.project_root, 'data', 'backups', f'config_{timestamp}')
            os.makedirs(backup_dir, exist_ok=True)
            
            config_dir = os.path.join(self.project_root, 'config')
            
            for filename in os.listdir(config_dir):
                if filename.endswith('.json'):
                    src = os.path.join(config_dir, filename)
                    dst = os.path.join(backup_dir, filename)
                    shutil.copy2(src, dst)
            
            self.logger.info(f"配置文件备份完成: {backup_dir}")
            return True
            
        except Exception as e:
            self.logger.error(f"备份配置文件失败: {e}")
            return False

# 便捷函数
def create_marketing_system(project_root: str = None) -> LinkedInMarketingController:
    """创建LinkedIn营销系统实例
    
    Args:
        project_root: 项目根目录
    
    Returns:
        营销系统控制器实例
    """
    return LinkedInMarketingController(project_root)

def quick_start(project_root: str = None) -> LinkedInMarketingController:
    """快速启动LinkedIn营销系统
    
    Args:
        project_root: 项目根目录
    
    Returns:
        已初始化的营销系统控制器实例
    """
    controller = LinkedInMarketingController(project_root)
    
    if controller.initialize_system():
        print("✅ LinkedIn营销系统初始化成功")
        if controller.start_browser_session():
            print("✅ 浏览器会话启动成功")
            print("🚀 系统已就绪，可以开始使用")
        else:
            print("⚠️ 浏览器会话启动失败，请检查Chrome调试模式")
    else:
        print("❌ 系统初始化失败")
    
    return controller
