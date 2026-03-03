import time
import random
import smtplib
import sqlite3
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from ..utils.logger import get_logger
from ..utils.helpers import random_delay, validate_email
from ..utils.config_loader import ConfigLoader
from ..scraper.browser_manager import BrowserManager
from .auto_connect import AutoConnector
# 已不使用 MCP，移除相关导入

class MarketingAutomation:
    """营销自动化模块"""
    
    def __init__(self, db_path: str = None, config_loader: ConfigLoader = None, browser_manager: BrowserManager = None):
        """初始化营销自动化模块
        
        Args:
            db_path: 数据库路径
            config_loader: 配置加载器
            browser_manager: 浏览器管理器
        """
        self.logger = get_logger("marketing_automation")
        self.config_loader = config_loader or ConfigLoader()
        self.browser_manager = browser_manager
        
        if not db_path:
            import os
            db_from_config = self.config_loader.get_setting('database.path')
            if db_from_config:
                db_path = db_from_config if os.path.isabs(db_from_config) else os.path.join(os.getcwd(), db_from_config)
            else:
                db_path = os.path.join(os.getcwd(), 'database', 'contacts.db')
        
        self.db_path = db_path
        
        # 加载配置
        self.settings = self.config_loader.load_settings()
        self.email_templates = self.config_loader.load_email_templates()
        self.connection_messages = self.config_loader.load_connection_messages()
        
        # 安全限制
        safety_cfg = self.settings.get('safety_limits', {}) or self.settings.get('safety', {})
        self.daily_connection_limit = safety_cfg.get('max_daily_friend_requests', safety_cfg.get('max_daily_connections', 20))
        self.daily_email_limit = safety_cfg.get('max_daily_emails', 50)
        self.min_delay = safety_cfg.get('friend_request_delay_min', safety_cfg.get('min_action_delay', 30))
        self.max_delay = safety_cfg.get('friend_request_delay_max', safety_cfg.get('max_action_delay', 120))
        
        # 邮件配置
        self.email_config = self.settings.get('email', {})
        
        # 不使用 MCP 客户端

        self.logger.info("营销自动化模块初始化完成")
    
    def send_connection_requests(self, contacts: List[Dict[str, Any]], message: str = None) -> Dict[str, Any]:
        """批量发送LinkedIn连接请求
        
        Args:
            contacts: 联系人列表
            message: 自定义连接消息
        
        Returns:
            发送结果统计
        """
        results = {
            'total': len(contacts),
            'sent': 0,
            'failed': 0,
            'skipped': 0,
            'errors': []
        }
        
        try:
            # 检查今日连接数量限制
            today_connections = self._get_today_action_count('connect')
            if today_connections >= self.daily_connection_limit:
                self.logger.warning(f"今日连接请求已达上限: {today_connections}/{self.daily_connection_limit}")
                results['errors'].append("今日连接请求已达上限")
                return results
            
            self.logger.info(f"开始发送 {len(contacts)} 个连接请求")
            
            # 使用默认消息模板
            if not message:
                message = (
                    self.connection_messages.get('default')
                    or self.email_templates.get('connection_request', {}).get('default_message', '')
                    or "Hi [当前LinkedIn用户的名], I hope you are having a great week! I’m Jing, and I'm involved in a synthetic biology company focused on developing whey through precision fermentation. I would appreciate the opportunity to connect and learn more about your work. Thanks, Jing"
                )

            remaining_quota = max(0, self.daily_connection_limit - today_connections)
            if remaining_quota == 0:
                results['errors'].append("今日连接请求已达上限")
                return results

            candidates = []
            for contact in contacts:
                try:
                    if self._has_sent_connection_request(contact.get('id')):
                        results['skipped'] += 1
                        continue
                    if not contact.get('linkedin_url'):
                        results['skipped'] += 1
                        continue
                    candidates.append(contact)
                except Exception as e:
                    self.logger.warning(f"联系人预检查失败: {e}")
                    results['skipped'] += 1

            candidates = candidates[:remaining_quota]
            if not candidates:
                self.logger.info("无可发送连接请求的联系人")
                return results

            driver = self._ensure_linkedin_driver()
            if not driver:
                results['errors'].append("无法连接到Chrome调试会话，请先启动并登录LinkedIn")
                return results

            delay_between = max(2.0, min(float(self.min_delay), 20.0))
            connector = AutoConnector(driver, delay_between=delay_between)
            raw_results = connector.connect_with_note(candidates, message)

            by_url = { (c.get('linkedin_url') or '').rstrip('/'): c for c in candidates }
            for item in raw_results:
                item_status = item.get('status', 'failed')
                url_key = (item.get('url') or '').rstrip('/')
                contact = by_url.get(url_key, {})
                contact_id = contact.get('id')

                if item_status == 'sent':
                    results['sent'] += 1
                    self._record_marketing_action(contact_id, 'connect', 'sent', item.get('message') or message)
                elif item_status in ('already_connected', 'pending', 'skipped'):
                    results['skipped'] += 1
                    db_status = 'accepted' if item_status == 'already_connected' else ('pending' if item_status == 'pending' else 'skipped')
                    self._record_marketing_action(contact_id, 'connect', db_status, item.get('message') or message)
                else:
                    results['failed'] += 1
                    err = item.get('error') or 'unknown error'
                    name = item.get('name') or contact.get('name') or 'Unknown'
                    results['errors'].append(f"{name}: {err}")
                    self._record_marketing_action(contact_id, 'connect', 'failed', item.get('message') or message)
            
            self.logger.info(f"连接请求发送完成: 成功 {results['sent']}, 失败 {results['failed']}, 跳过 {results['skipped']}")
            return results
            
        except Exception as e:
            self.logger.error(f"批量发送连接请求失败: {e}")
            results['errors'].append(str(e))
            return results
    
    # MCP 全自动通道已移除
    def _ensure_linkedin_driver(self):
        try:
            if self.browser_manager and getattr(self.browser_manager, 'driver', None):
                return self.browser_manager.driver
        except Exception:
            pass
        try:
            debug_port = self.config_loader.get_setting('browser.chrome_debug_port', 9222)
            opts = Options()
            opts.add_experimental_option("debuggerAddress", f"localhost:{debug_port}")
            driver = webdriver.Chrome(options=opts)
            return driver
        except Exception as e:
            self.logger.error(f"连接Chrome调试会话失败: {e}")
            return None
    
    def _find_connect_button(self, driver) -> Optional[Any]:
        """查找连接按钮"""
        connect_selectors = [
            "button[aria-label*='Connect']",
            "button[aria-label*='连接']",
            "button[data-control-name='connect']",
            "button:contains('Connect')",
            "button:contains('连接')",
            ".pv-s-profile-actions button[data-control-name='connect']",
            ".pvs-profile-actions button[aria-label*='Connect']"
        ]
        
        for selector in connect_selectors:
            try:
                if ':contains(' in selector:
                    # 使用XPath处理包含文本的选择器
                    text = selector.split(':contains(')[1].rstrip(')')
                    xpath = f"//button[contains(text(), '{text}')]"
                    elements = driver.find_elements(By.XPATH, xpath)
                else:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        return element
            except Exception:
                continue
        
        return None
    
    def _handle_connection_dialog(self, driver, message: str) -> bool:
        """处理连接对话框"""
        try:
            # 等待对话框出现
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-test-modal]"))
            )
            
            # 查找添加备注按钮
            add_note_selectors = [
                "button[aria-label*='Add a note']",
                "button[aria-label*='添加备注']",
                "button:contains('Add a note')",
                "button:contains('添加备注')"
            ]
            
            add_note_button = None
            for selector in add_note_selectors:
                try:
                    if ':contains(' in selector:
                        text = selector.split(':contains(')[1].rstrip(')')
                        xpath = f"//button[contains(text(), '{text}')]"
                        elements = driver.find_elements(By.XPATH, xpath)
                    else:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    for element in elements:
                        if element.is_displayed():
                            add_note_button = element
                            break
                    
                    if add_note_button:
                        break
                except Exception:
                    continue
            
            # 如果有消息且找到添加备注按钮
            if message and add_note_button:
                add_note_button.click()
                time.sleep(1)
                
                # 查找消息输入框
                message_input = driver.find_element(By.CSS_SELECTOR, "textarea[name='message']")
                message_input.clear()
                message_input.send_keys(message)
                time.sleep(1)
            
            # 查找并点击发送按钮
            send_selectors = [
                "button[aria-label*='Send']",
                "button[aria-label*='发送']",
                "button[data-control-name='send']",
                "button:contains('Send')",
                "button:contains('发送')"
            ]
            
            for selector in send_selectors:
                try:
                    if ':contains(' in selector:
                        text = selector.split(':contains(')[1].rstrip(')')
                        xpath = f"//button[contains(text(), '{text}')]"
                        elements = driver.find_elements(By.XPATH, xpath)
                    else:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    for element in elements:
                        if element.is_displayed() and element.is_enabled():
                            element.click()
                            time.sleep(2)
                            return True
                except Exception:
                    continue
            
            return False
            
        except TimeoutException:
            self.logger.warning("连接对话框未出现")
            return False
        except Exception as e:
            self.logger.error(f"处理连接对话框失败: {e}")
            return False
    
    def send_emails(self, contacts: List[Dict[str, Any]], subject: str, body: str) -> Dict[str, Any]:
        """批量发送邮件
        
        Args:
            contacts: 联系人列表
            subject: 邮件主题
            body: 邮件内容
        
        Returns:
            发送结果统计
        """
        results = {
            'total': len(contacts),
            'sent': 0,
            'failed': 0,
            'skipped': 0,
            'errors': []
        }
        
        try:
            # 检查今日邮件数量限制
            today_emails = self._get_today_action_count('email')
            if today_emails >= self.daily_email_limit:
                self.logger.warning(f"今日邮件已达上限: {today_emails}/{self.daily_email_limit}")
                results['errors'].append("今日邮件已达上限")
                return results
            
            # 检查邮件配置
            if not self._validate_email_config():
                self.logger.error("邮件配置无效")
                results['errors'].append("邮件配置无效")
                return results
            
            self.logger.info(f"开始发送 {len(contacts)} 封邮件")
            
            # 建立SMTP连接
            smtp_server = self._create_smtp_connection()
            if not smtp_server:
                results['errors'].append("无法连接邮件服务器")
                return results
            
            try:
                for i, contact in enumerate(contacts):
                    # 检查是否超过今日限制
                    if today_emails + results['sent'] >= self.daily_email_limit:
                        self.logger.warning("达到今日邮件限制，停止发送")
                        break
                    
                    try:
                        # 获取联系人邮箱
                        email = self._extract_email_from_contact(contact)
                        if not email:
                            self.logger.warning(f"联系人 {contact.get('name')} 没有有效邮箱")
                            results['skipped'] += 1
                            continue
                        
                        # 检查是否已经发送过邮件
                        if self._has_sent_email(contact['id']):
                            self.logger.info(f"跳过已发送邮件的联系人: {contact['name']}")
                            results['skipped'] += 1
                            continue
                        
                        # 个性化邮件内容
                        personalized_subject = self._personalize_content(subject, contact)
                        personalized_body = self._personalize_content(body, contact)
                        
                        # 发送邮件
                        success = self._send_single_email(
                            smtp_server, 
                            email, 
                            personalized_subject, 
                            personalized_body
                        )
                        
                        if success:
                            results['sent'] += 1
                            self._record_marketing_action(
                                contact['id'], 
                                'email', 
                                'sent', 
                                f"Subject: {personalized_subject}\n\n{personalized_body}"
                            )
                            self.logger.info(f"成功发送邮件: {contact['name']} ({email})")
                        else:
                            results['failed'] += 1
                            self._record_marketing_action(
                                contact['id'], 
                                'email', 
                                'failed', 
                                f"Subject: {personalized_subject}"
                            )
                            self.logger.warning(f"发送邮件失败: {contact['name']} ({email})")
                        
                        # 随机延迟
                        if i < len(contacts) - 1:  # 不是最后一个
                            delay = random_delay(5, 15)  # 邮件间隔较短
                            time.sleep(delay)
                        
                    except Exception as e:
                        self.logger.error(f"处理联系人 {contact.get('name', 'Unknown')} 时出错: {e}")
                        results['failed'] += 1
                        results['errors'].append(f"{contact.get('name', 'Unknown')}: {str(e)}")
                
            finally:
                smtp_server.quit()
            
            self.logger.info(f"邮件发送完成: 成功 {results['sent']}, 失败 {results['failed']}, 跳过 {results['skipped']}")
            return results
            
        except Exception as e:
            self.logger.error(f"批量发送邮件失败: {e}")
            results['errors'].append(str(e))
            return results
    
    def _create_smtp_connection(self):
        """创建SMTP连接"""
        try:
            smtp_host = self.email_config.get('smtp_host')
            smtp_port = self.email_config.get('smtp_port', 587)
            username = self.email_config.get('username')
            password = self.email_config.get('password')
            use_tls = self.email_config.get('use_tls', True)
            
            server = smtplib.SMTP(smtp_host, smtp_port)
            if use_tls:
                server.starttls()
            server.login(username, password)
            
            return server
            
        except Exception as e:
            self.logger.error(f"创建SMTP连接失败: {e}")
            return None
    
    def _send_single_email(self, smtp_server, to_email: str, subject: str, body: str) -> bool:
        """发送单封邮件"""
        try:
            from_email = self.email_config.get('username')
            from_name = self.email_config.get('from_name', from_email)
            
            # 创建邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{from_name} <{from_email}>"
            msg['To'] = to_email
            
            # 添加文本内容
            text_part = MIMEText(body, 'plain', 'utf-8')
            msg.attach(text_part)
            
            # 如果内容包含HTML标签，也添加HTML版本
            if '<' in body and '>' in body:
                html_part = MIMEText(body, 'html', 'utf-8')
                msg.attach(html_part)
            
            # 发送邮件
            smtp_server.send_message(msg)
            return True
            
        except Exception as e:
            self.logger.error(f"发送邮件失败: {e}")
            return False
    
    def _personalize_content(self, content: str, contact: Dict[str, Any]) -> str:
        """个性化内容"""
        try:
            # 替换占位符
            placeholders = {
                '{name}': contact.get('name', ''),
                '{title}': contact.get('title', ''),
                '{company}': contact.get('company', ''),
                '{location}': contact.get('location', ''),
                '{first_name}': contact.get('name', '').split()[0] if contact.get('name') else ''
            }
            
            personalized = content
            for placeholder, value in placeholders.items():
                personalized = personalized.replace(placeholder, value)
            
            return personalized
            
        except Exception as e:
            self.logger.warning(f"个性化内容失败: {e}")
            return content
    
    def _extract_email_from_contact(self, contact: Dict[str, Any]) -> Optional[str]:
        """从联系人信息中提取邮箱"""
        # 首先检查是否有直接的邮箱字段
        email = contact.get('email')
        if email and validate_email(email):
            return email
        
        # 从描述中提取邮箱
        description = contact.get('description', '')
        if description:
            import re
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            emails = re.findall(email_pattern, description)
            if emails:
                return emails[0]
        
        # 尝试根据姓名和公司生成邮箱（这需要额外的逻辑）
        # 这里可以添加更复杂的邮箱推测逻辑
        
        return None
    
    def _check_linkedin_login(self) -> bool:
        """检查LinkedIn登录状态"""
        try:
            driver = self.browser_manager.driver
            current_url = driver.current_url
            
            # 如果不在LinkedIn页面，先导航到LinkedIn
            if 'linkedin.com' not in current_url:
                driver.get('https://www.linkedin.com/feed/')
                time.sleep(3)
            
            # 检查是否在登录页面
            if '/login' in driver.current_url or '/uas/login' in driver.current_url:
                return False
            
            # 检查是否有导航栏（登录用户才有）
            try:
                driver.find_element(By.CSS_SELECTOR, ".global-nav")
                return True
            except NoSuchElementException:
                return False
            
        except Exception as e:
            self.logger.error(f"检查LinkedIn登录状态失败: {e}")
            return False
    
    def _validate_email_config(self) -> bool:
        """验证邮件配置"""
        required_fields = ['smtp_host', 'smtp_port', 'username', 'password']
        for field in required_fields:
            if not self.email_config.get(field):
                self.logger.error(f"邮件配置缺少必需字段: {field}")
                return False
        return True
    
    def _get_today_action_count(self, action_type: str) -> int:
        """获取今日指定动作的数量"""
        try:
            today = datetime.now().date()
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM marketing_records WHERE action_type = ? AND DATE(created_at) = ? AND status = 'sent'",
                    (action_type, today.isoformat())
                )
                return cursor.fetchone()[0]
        except Exception as e:
            self.logger.error(f"获取今日动作数量失败: {e}")
            return 0
    
    def _has_sent_connection_request(self, contact_id: int) -> bool:
        """检查是否已发送连接请求"""
        if not contact_id:
            return False
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM marketing_records WHERE contact_id = ? AND action_type IN ('connection_request', 'connect') AND status IN ('sent','accepted','pending')",
                    (contact_id,)
                )
                return cursor.fetchone()[0] > 0
        except Exception:
            return False
    
    def _has_sent_email(self, contact_id: int) -> bool:
        """检查是否已发送邮件"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM marketing_records WHERE contact_id = ? AND action_type = 'email' AND status = 'sent'",
                    (contact_id,)
                )
                return cursor.fetchone()[0] > 0
        except Exception:
            return False
    
    def _record_marketing_action(self, contact_id: int, action_type: str, status: str, message_content: str = None):
        """记录营销动作"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(marketing_records)")
                cols = {r[1] for r in cursor.fetchall()}
                if {'message', 'sent_at', 'created_at'}.issubset(cols):
                    cursor.execute(
                        "INSERT INTO marketing_records (contact_id, action_type, status, message, sent_at, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                        (contact_id, action_type, status, message_content)
                    )
                else:
                    cursor.execute(
                        "INSERT INTO marketing_records (contact_id, action_type, status, message_content, executed_at) VALUES (?, ?, ?, ?, ?)",
                        (contact_id, action_type, status, message_content, datetime.now().isoformat())
                    )
                conn.commit()
        except Exception as e:
            self.logger.error(f"记录营销动作失败: {e}")
    
    def get_marketing_statistics(self) -> Dict[str, Any]:
        """获取营销统计信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                stats = {}
                
                # 今日统计
                today = datetime.now().date()
                cursor.execute(
                    "SELECT action_type, status, COUNT(*) FROM marketing_records WHERE DATE(created_at) = ? GROUP BY action_type, status",
                    (today.isoformat(),)
                )
                
                today_stats = {}
                for action_type, status, count in cursor.fetchall():
                    if action_type not in today_stats:
                        today_stats[action_type] = {}
                    today_stats[action_type][status] = count
                
                stats['today'] = today_stats
                
                # 总体统计
                cursor.execute(
                    "SELECT action_type, status, COUNT(*) FROM marketing_records GROUP BY action_type, status"
                )
                
                total_stats = {}
                for action_type, status, count in cursor.fetchall():
                    if action_type not in total_stats:
                        total_stats[action_type] = {}
                    total_stats[action_type][status] = count
                
                stats['total'] = total_stats
                
                return stats
                
        except Exception as e:
            self.logger.error(f"获取营销统计失败: {e}")
            return {}
    
    def schedule_marketing_campaign(self, contacts: List[Dict[str, Any]], campaign_config: Dict[str, Any]) -> bool:
        """安排营销活动
        
        Args:
            contacts: 联系人列表
            campaign_config: 活动配置
        
        Returns:
            是否安排成功
        """
        try:
            # 这里可以实现更复杂的营销活动安排逻辑
            # 比如分批发送、定时发送等
            
            self.logger.info(f"安排营销活动，目标联系人: {len(contacts)}")
            
            # 示例：简单的分批处理
            batch_size = campaign_config.get('batch_size', 10)
            delay_between_batches = campaign_config.get('delay_between_batches', 3600)  # 1小时
            
            for i in range(0, len(contacts), batch_size):
                batch = contacts[i:i + batch_size]
                
                # 记录计划任务
                scheduled_time = datetime.now() + timedelta(seconds=i * delay_between_batches)
                
                for contact in batch:
                    self._record_marketing_action(
                        contact['id'],
                        campaign_config.get('action_type', 'connection_request'),
                        'scheduled',
                        f"Scheduled for {scheduled_time.isoformat()}"
                    )
            
            self.logger.info("营销活动安排完成")
            return True
            
        except Exception as e:
            self.logger.error(f"安排营销活动失败: {e}")
            return False
