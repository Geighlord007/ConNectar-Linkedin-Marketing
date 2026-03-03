import json
import os
import re
import yaml
from typing import Dict, Any, Optional
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

class ConfigLoader:
    """配置文件加载器"""
    
    def __init__(self, config_dir: str = "config"):
        if load_dotenv is not None:
            project_root = Path(__file__).resolve().parents[2]
            candidate_paths = [
                Path.cwd() / ".env",
                project_root / ".env",
            ]
            for env_path in candidate_paths:
                if env_path.exists():
                    load_dotenv(env_path, override=False)
        self.config_dir = config_dir
        self._settings = None
        self._keywords = None
        self._email_templates = None
        self._scoring_rules = None
    
    @staticmethod
    def _resolve_env_vars(obj):
        """递归替换配置值中的 ${ENV_VAR} 为环境变量实际值"""
        if isinstance(obj, str):
            def _replace(m):
                return os.environ.get(m.group(1), m.group(0))
            return re.sub(r'\$\{(\w+)\}', _replace, obj)
        elif isinstance(obj, dict):
            return {k: ConfigLoader._resolve_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [ConfigLoader._resolve_env_vars(v) for v in obj]
        return obj

    def load_settings(self) -> Dict[str, Any]:
        """加载系统设置（自动替换 ${ENV_VAR} 占位符）"""
        if self._settings is None:
            settings_path = os.path.join(self.config_dir, "settings.json")
            with open(settings_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            self._settings = self._resolve_env_vars(raw)
        return self._settings
    
    def load_keywords(self) -> Dict[str, Any]:
        """加载关键词配置"""
        if self._keywords is None:
            keywords_path = os.path.join(self.config_dir, "keywords.json")
            with open(keywords_path, 'r', encoding='utf-8') as f:
                self._keywords = json.load(f)
        return self._keywords
    
    def load_email_templates(self) -> Dict[str, Any]:
        """加载邮件模板"""
        if self._email_templates is None:
            templates_path = os.path.join(self.config_dir, "email_templates.json")
            with open(templates_path, 'r', encoding='utf-8') as f:
                self._email_templates = json.load(f)
        return self._email_templates

    def load_connection_messages(self) -> Dict[str, Any]:
        """加载连接招呼语模板（config/messages/connection_messages.json）"""
        path = os.path.join(self.config_dir, 'messages', 'connection_messages.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def load_scoring_rules(self) -> Dict[str, Any]:
        """加载评分规则配置"""
        if self._scoring_rules is None:
            settings = self.load_settings()
            filtering = settings.get('filtering', {}) if isinstance(settings, dict) else {}
            self._scoring_rules = {
                'filtering': filtering if isinstance(filtering, dict) else {}
            }
        return self._scoring_rules
    
    def get_keywords(self) -> Dict[str, Any]:
        """获取关键词配置"""
        return self.load_keywords()
    
    def get_llm_config(self) -> Dict[str, Any]:
        """获取LLM配置"""
        settings = self.load_settings()
        return settings.get('llm', {})
    
    def get_setting(self, key_path: str, default: Any = None) -> Any:
        """获取特定设置值
        
        Args:
            key_path: 设置键路径，如 'database.path' 或 'scraping.retry_attempts'
            default: 默认值
        
        Returns:
            设置值或默认值
        """
        settings = self.load_settings()
        keys = key_path.split('.')
        
        current = settings
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        
        return current
    
    def update_setting(self, key_path: str, value: Any) -> None:
        """更新设置值
        
        Args:
            key_path: 设置键路径
            value: 新值
        """
        settings = self.load_settings()
        keys = key_path.split('.')
        
        current = settings
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
        
        # 保存到文件
        settings_path = os.path.join(self.config_dir, "settings.json")
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        
        # 清除缓存
        self._settings = None
    
    def validate_config(self) -> Dict[str, list]:
        """验证配置文件
        
        Returns:
            验证结果，包含错误和警告
        """
        errors = []
        warnings = []
        
        try:
            settings = self.load_settings()
            
            # 检查必需的配置项
            required_keys = [
                'database.path',
                'browser.chrome_debug_port',
                'scraping.request_delay_min',
                'safety_limits.max_daily_friend_requests'
            ]
            
            for key_path in required_keys:
                if self.get_setting(key_path) is None:
                    errors.append(f"缺少必需的配置项: {key_path}")
            
            # 检查数据库路径
            db_path = self.get_setting('database.path')
            if db_path:
                db_dir = os.path.dirname(db_path)
                if not os.path.exists(db_dir):
                    warnings.append(f"数据库目录不存在: {db_dir}")
            
            # 检查邮件配置
            email_username = self.get_setting('email.username')
            if not email_username:
                warnings.append("邮件用户名未配置，邮件功能将不可用")
            
        except Exception as e:
            errors.append(f"配置文件加载失败: {str(e)}")
        
        try:
            keywords = self.load_keywords()
            if not keywords.get('keywords'):
                errors.append("关键词列表为空")
        except Exception as e:
            errors.append(f"关键词配置文件加载失败: {str(e)}")
        
        try:
            self.load_email_templates()
        except Exception as e:
            warnings.append(f"邮件模板配置文件加载失败: {str(e)}")

        # 可选：加载连接招呼语文件
        try:
            self.load_connection_messages()
        except Exception as e:
            warnings.append(f"连接招呼语配置加载失败: {str(e)}")
        
        return {'errors': errors, 'warnings': warnings}
    
    def create_default_configs(self) -> None:
        """创建默认配置文件（如果不存在）"""
        os.makedirs(self.config_dir, exist_ok=True)
        
        # 这里可以添加创建默认配置文件的逻辑
        # 由于我们已经有了配置文件，这里暂时留空
        pass

# 全局配置实例
config = ConfigLoader()
