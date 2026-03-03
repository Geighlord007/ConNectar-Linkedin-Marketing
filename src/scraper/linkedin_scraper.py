import os
import time
from typing import Dict, List, Optional, Any

from ..utils.config_loader import ConfigLoader
from ..utils.logger import get_logger, SessionLogger
from ..utils.helpers import save_json_file
from .browser_manager import BrowserManager
from .linkedin_search_manager import FinalSearchManager

class LinkedInScraper:
    """LinkedIn爬虫主控制器"""
    
    def __init__(self, config_dir: str = None):
        """初始化LinkedIn爬虫
        
        Args:
            config_dir: 配置文件目录路径
        """
        # 加载配置
        self.config_loader = ConfigLoader(config_dir)
        self.config = self.config_loader.load_settings()
        self.keywords_config = self.config_loader.load_keywords()
        
        # 初始化日志
        self.logger = get_logger("linkedin_scraper")
        self.session_logger = None  # 将在需要时创建
        
        # 初始化组件
        self.browser_manager = None
        self.search_manager = None
        self.driver = None
        
        # 运行状态
        self.is_initialized = False
        self.session_id = None
        
        self.logger.info("LinkedIn爬虫初始化完成")
    
    def initialize(self) -> bool:
        """初始化爬虫组件
        
        Returns:
            是否初始化成功
        """
        try:
            self.logger.info("开始初始化LinkedIn爬虫组件")
            
            # 初始化会话日志记录器
            if self.session_logger is None:
                # 使用SystemLogger的create_session_log方法创建SessionLogger
                self.session_logger = self.logger.create_session_log("linkedin_scraping")
                self.session_id = "linkedin_scraping"
                
                # 检查session_logger是否创建成功
                if self.session_logger is None:
                    self.logger.error("会话日志记录器创建失败")
                    return False
            
            # 初始化浏览器管理器
            self.browser_manager = BrowserManager()
            
            # 设置WebDriver
            if not self.browser_manager.setup_driver():
                self.logger.error("WebDriver设置失败")
                return False
            
            # 获取WebDriver实例
            self.driver = self.browser_manager.driver
            if not self.driver:
                self.logger.error("无法获取WebDriver实例")
                return False
            
            # 导航到LinkedIn并检查登录状态
            if not self.browser_manager.navigate_to_linkedin():
                self.logger.error("无法导航到LinkedIn")
                return False
            
            if not self.browser_manager.check_login_status():
                self.logger.error("LinkedIn登录状态检查失败")
                return False
            
            # 初始化搜索管理器
            self.search_manager = FinalSearchManager()
            self.search_manager.driver = self.driver
            
            # 验证搜索环境（简化版本，直接检查是否在LinkedIn）
            current_url = self.driver.current_url
            if "linkedin.com" not in current_url:
                self.logger.error("搜索环境验证失败：不在LinkedIn页面")
                return False
            
            self.is_initialized = True
            self.logger.info("LinkedIn爬虫组件初始化成功")
            
            # 记录会话开始
            keyword_count = len(self.keywords_config.get('keywords', []))
            self.session_logger.info(f"开始爬取会话，关键词数量: {keyword_count}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"初始化失败: {e}")
            return False
    
    def scrape_all_keywords(self) -> Dict[str, List[Dict[str, Any]]]:
        """爬取所有配置的关键词
        
        Returns:
            按关键词分组的爬取结果
        """
        if not self.is_initialized:
            if not self.initialize():
                self.logger.error("爬虫未初始化，无法开始爬取")
                return {}
        
        try:
            keywords = self.keywords_config.get('keywords', [])
            if not keywords:
                self.logger.warning("没有配置搜索关键词")
                return {}
            
            self.logger.info(f"开始爬取 {len(keywords)} 个关键词")
            
            # 执行搜索
            max_results_per_keyword = self.config.get('max_results_per_keyword', 100)
            results = self.search_manager.search_multiple_keywords(keywords, max_results_per_keyword)
            
            # 记录爬取结果
            total_contacts = sum(len(contacts) for contacts in results.values())
            self.session_logger.info(f"爬取进度: 处理了 {len(keywords)} 个关键词，获得 {total_contacts} 个联系人")
            
            # 获取统计信息
            stats = self.search_manager.get_search_statistics(results)
            self.logger.info(f"爬取完成: 总共 {stats['total_contacts']} 个联系人")
            
            return results
            
        except Exception as e:
            self.logger.error(f"爬取过程中发生错误: {e}")
            return {}
    
    def scrape_keywords(self, keywords: List[str], max_results_per_keyword: int = None) -> Dict[str, List[Dict[str, Any]]]:
        """爬取指定的关键词列表
        
        Args:
            keywords: 要搜索的关键词列表
            max_results_per_keyword: 每个关键词的最大结果数
        
        Returns:
            按关键词分组的爬取结果
        """
        if not self.is_initialized:
            if not self.initialize():
                self.logger.error("爬虫未初始化，无法开始爬取")
                return {}
        
        try:
            if not keywords:
                self.logger.warning("关键词列表为空")
                return {}
            
            self.logger.info(f"开始爬取指定的 {len(keywords)} 个关键词")
            
            # 执行搜索
            results = self.search_manager.search_multiple_keywords(keywords)
            
            # 记录爬取结果
            total_contacts = sum(len(contacts) for contacts in results.values())
            self.session_logger.info(f"爬取进度: 处理了 {len(keywords)} 个关键词，获得 {total_contacts} 个联系人")
            
            # 获取统计信息
            stats = self.search_manager.get_search_statistics(results)
            self.logger.info(f"指定关键词爬取完成: 总共 {stats['total_contacts']} 个联系人")
            
            return results
            
        except Exception as e:
            self.logger.error(f"爬取指定关键词时发生错误: {e}")
            return {}
    
    def save_results(self, results: Dict[str, List[Dict[str, Any]]], output_dir: str = None) -> Dict[str, str]:
        """保存爬取结果
        
        Args:
            results: 爬取结果
            output_dir: 输出目录
        
        Returns:
            保存的文件路径字典
        """
        try:
            if not output_dir:
                output_dir = os.path.join(os.getcwd(), 'data', 'raw')
            
            os.makedirs(output_dir, exist_ok=True)
            
            saved_files = {}
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            
            # 保存每个关键词的结果
            for keyword, contacts in results.items():
                if contacts:  # 只保存有结果的关键词
                    filename = f"{keyword}_{timestamp}.json"
                    filepath = os.path.join(output_dir, filename)
                    
                    # 添加元数据
                    data_to_save = {
                        'keyword': keyword,
                        'search_date': time.strftime('%Y-%m-%d %H:%M:%S'),
                        'total_contacts': len(contacts),
                        'contacts': contacts
                    }
                    
                    if save_json_file(data_to_save, filepath):
                        saved_files[keyword] = filepath
                        self.logger.info(f"关键词 '{keyword}' 的 {len(contacts)} 个联系人已保存到: {filepath}")
                    else:
                        self.logger.error(f"保存关键词 '{keyword}' 的结果失败")
            
            # 保存合并的结果
            if results:
                all_contacts = []
                for contacts in results.values():
                    all_contacts.extend(contacts)
                
                if all_contacts:
                    merged_filename = f"all_contacts_{timestamp}.json"
                    merged_filepath = os.path.join(output_dir, merged_filename)
                    
                    merged_data = {
                        'search_date': time.strftime('%Y-%m-%d %H:%M:%S'),
                        'total_keywords': len(results),
                        'total_contacts': len(all_contacts),
                        'keywords': list(results.keys()),
                        'contacts': all_contacts
                    }
                    
                    if save_json_file(merged_data, merged_filepath):
                        saved_files['merged'] = merged_filepath
                        self.logger.info(f"合并的 {len(all_contacts)} 个联系人已保存到: {merged_filepath}")
            
            return saved_files
            
        except Exception as e:
            self.logger.error(f"保存结果时发生错误: {e}")
            return {}
    
    def get_session_stats(self) -> Dict[str, Any]:
        """获取当前会话统计信息"""
        if self.session_logger and self.session_id:
            return {
                'session_id': self.session_id,
                'start_time': self.session_logger.start_time.isoformat(),
                'is_initialized': self.is_initialized
            }
        return {}
    
    def cleanup(self):
        """清理资源"""
        try:
            if self.session_logger and self.session_id:
                self.session_logger.end_session("completed")
            
            if self.browser_manager:
                self.browser_manager.cleanup()
            
            self.logger.info("LinkedIn爬虫资源清理完成")
            
        except Exception as e:
            self.logger.error(f"清理资源时发生错误: {e}")
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.cleanup()

# 便捷函数
def scrape_linkedin_keywords(keywords: List[str], config_dir: str = None, output_dir: str = None) -> Dict[str, str]:
    """便捷函数：爬取LinkedIn关键词
    
    Args:
        keywords: 关键词列表
        config_dir: 配置目录
        output_dir: 输出目录
    
    Returns:
        保存的文件路径字典
    """
    with LinkedInScraper(config_dir) as scraper:
        results = scraper.scrape_keywords(keywords)
        if results:
            return scraper.save_results(results, output_dir)
        return {}

def scrape_linkedin_all(config_dir: str = None, output_dir: str = None) -> Dict[str, str]:
    """便捷函数：爬取所有配置的关键词
    
    Args:
        config_dir: 配置目录
        output_dir: 输出目录
    
    Returns:
        保存的文件路径字典
    """
    with LinkedInScraper(config_dir) as scraper:
        results = scraper.scrape_all_keywords()
        if results:
            return scraper.save_results(results, output_dir)
        return {}