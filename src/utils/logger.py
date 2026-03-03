import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional

class SystemLogger:
    """系统日志管理器"""
    
    def __init__(self, name: str = "linkedin_marketing", config: Optional[dict] = None):
        self.name = name
        self.config = config or {
            'level': 'WARNING',
            'file_path': 'logs/system.log',
            'max_file_size_mb': 10,
            'backup_count': 5,
            'console_output': False,
            'console_level': 'ERROR'
        }
        
        # 设置控制台编码为UTF-8（Windows系统）
        if sys.platform.startswith('win'):
            try:
                import subprocess
                subprocess.run(['chcp', '65001'], shell=True, capture_output=True)
            except Exception:
                pass  # 忽略编码设置失败
        
        self.logger = self._setup_logger()
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger(self.name)
        
        # 避免重复添加处理器
        if logger.handlers:
            return logger
        
        # 设置日志级别
        level = getattr(logging, self.config['level'].upper(), logging.INFO)
        logger.setLevel(level)
        
        # 创建格式器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 文件处理器
        if self.config.get('file_path'):
            log_dir = os.path.dirname(self.config['file_path'])
            os.makedirs(log_dir, exist_ok=True)
            
            file_handler = RotatingFileHandler(
                self.config['file_path'],
                maxBytes=self.config['max_file_size_mb'] * 1024 * 1024,
                backupCount=self.config['backup_count'],
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        
        # 控制台处理器（优化版 - 支持独立级别控制）
        if self.config.get('console_output', False):
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            # 设置控制台独立的日志级别
            console_level = getattr(logging, self.config.get('console_level', 'ERROR').upper(), logging.ERROR)
            console_handler.setLevel(console_level)
            
            # 确保控制台输出使用UTF-8编码
            if hasattr(sys.stdout, 'reconfigure'):
                try:
                    sys.stdout.reconfigure(encoding='utf-8')
                except Exception:
                    pass
            
            logger.addHandler(console_handler)
        
        return logger
    
    def info(self, message: str, **kwargs):
        """记录信息日志"""
        self.logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """记录警告日志"""
        self.logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """记录错误日志"""
        self.logger.error(message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        """记录调试日志"""
        self.logger.debug(message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """记录严重错误日志"""
        self.logger.critical(message, **kwargs)
    
    def log_scraping_progress(self, keyword: str, current: int, total: int, contacts_found: int):
        """记录爬取进度"""
        progress = (current / total) * 100 if total > 0 else 0
        self.info(f"爬取进度 - 关键词: {keyword}, 进度: {current}/{total} ({progress:.1f}%), 已找到联系人: {contacts_found}")
    
    def log_filtering_results(self, total_contacts: int, filtered_contacts: int, filter_description: str):
        """记录筛选结果"""
        filter_rate = (filtered_contacts / total_contacts) * 100 if total_contacts > 0 else 0
        self.info(f"筛选完成 - 总联系人: {total_contacts}, 筛选后: {filtered_contacts} ({filter_rate:.1f}%), 筛选条件: {filter_description}")
    
    def log_marketing_action(self, action_type: str, contact_name: str, status: str, details: str = ""):
        """记录营销行为"""
        message = f"营销行为 - 类型: {action_type}, 联系人: {contact_name}, 状态: {status}"
        if details:
            message += f", 详情: {details}"
        self.info(message)
    
    def log_error_with_context(self, error: Exception, context: str, **kwargs):
        """记录带上下文的错误"""
        error_msg = f"错误发生在 {context}: {str(error)}"
        if kwargs:
            error_msg += f", 上下文信息: {kwargs}"
        self.error(error_msg, exc_info=True)
    
    def log_system_event(self, event_type: str, description: str, **kwargs):
        """记录系统事件"""
        message = f"系统事件 - {event_type}: {description}"
        if kwargs:
            message += f", 详情: {kwargs}"
        self.info(message)
    
    def log_performance_metric(self, metric_name: str, value: float, unit: str = ""):
        """记录性能指标"""
        message = f"性能指标 - {metric_name}: {value}"
        if unit:
            message += f" {unit}"
        self.info(message)
    
    def create_session_log(self, session_id: str) -> 'SessionLogger':
        """创建会话日志记录器"""
        return SessionLogger(self, session_id)

class SessionLogger:
    """会话日志记录器"""
    
    def __init__(self, system_logger: SystemLogger, session_id: str):
        self.system_logger = system_logger
        self.session_id = session_id
        self.start_time = datetime.now()
        
        self.system_logger.info(f"会话开始 - ID: {session_id}")
    
    def log(self, level: str, message: str, **kwargs):
        """记录会话日志"""
        session_message = f"[会话 {self.session_id}] {message}"
        getattr(self.system_logger, level.lower())(session_message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self.log('INFO', message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self.log('WARNING', message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self.log('ERROR', message, **kwargs)
    
    def end_session(self, status: str = "completed"):
        """结束会话"""
        duration = datetime.now() - self.start_time
        self.system_logger.info(f"会话结束 - ID: {self.session_id}, 状态: {status}, 持续时间: {duration}")

# 创建全局日志实例
def get_logger(name: str = "linkedin_marketing", config: Optional[dict] = None) -> SystemLogger:
    """获取日志记录器实例"""
    return SystemLogger(name, config)

# 默认日志实例
logger = get_logger()