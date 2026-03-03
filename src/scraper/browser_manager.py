import os
import time
import subprocess
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException
from typing import Optional, List

from ..utils.logger import get_logger
from ..utils.config_loader import config

class BrowserManager:
    """浏览器管理器"""
    
    def __init__(self):
        self.logger = get_logger("browser_manager")
        self.driver: Optional[webdriver.Chrome] = None
        self.debug_port = config.get_setting('browser.chrome_debug_port', 9222)
        # 使用用户主目录下的绝对路径，避免权限问题
        default_user_data = str(Path.home() / "chrome_debug_linkedin")
        self.user_data_dir = config.get_setting('browser.user_data_dir', default_user_data)
        
    def find_chrome_executable(self) -> Optional[str]:
        """查找Chrome可执行文件路径"""
        possible_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Users\{}\AppData\Local\Google\Chrome\Application\chrome.exe".format(os.getenv('USERNAME')),
            r"C:\Program Files\Google\Chrome Beta\Application\chrome.exe",
            r"C:\Program Files\Google\Chrome Dev\Application\chrome.exe"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                self.logger.info(f"找到Chrome可执行文件: {path}")
                return path
        
        self.logger.error("未找到Chrome可执行文件")
        return None
    
    def is_chrome_debug_running(self) -> bool:
        """检查Chrome调试模式是否正在运行"""
        try:
            # 使用tasklist命令检查Chrome进程
            result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq chrome.exe'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and 'chrome.exe' in result.stdout:
                self.logger.info("发现Chrome进程正在运行")
                return True
        except Exception as e:
            self.logger.error(f"检查Chrome调试进程时出错: {e}")
        
        return False
    
    def _check_debug_port_available(self) -> bool:
        """检查调试端口是否可用"""
        try:
            import socket
            import requests
            
            # 首先检查端口连接
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)  # 增加超时时间
            result = sock.connect_ex(('localhost', self.debug_port))
            sock.close()
            
            if result != 0:
                return False
            
            # 然后检查Chrome调试API是否响应
            try:
                response = requests.get(f'http://localhost:{self.debug_port}/json/version', timeout=3)
                return response.status_code == 200
            except:
                # 如果API检查失败，但端口可连接，仍然认为可用（可能还在初始化）
                return True
                
        except Exception:
            return False
    
    def kill_chrome_processes(self) -> None:
        """终止所有Chrome进程"""
        try:
            # 使用taskkill命令终止Chrome进程
            result = subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe'], 
                                  capture_output=True, text=True,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                self.logger.info("已终止Chrome进程")
            else:
                self.logger.debug("没有找到需要终止的Chrome进程")
            
            # 等待进程完全终止，并验证
            for i in range(10):
                time.sleep(0.5)
                check_result = subprocess.run(
                    ['tasklist', '/FI', 'IMAGENAME eq chrome.exe'],
                    capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                if 'chrome.exe' not in check_result.stdout:
                    self.logger.info("Chrome进程已完全终止")
                    break
                if i == 9:
                    self.logger.warning("Chrome进程可能未完全终止")
            
        except Exception as e:
            self.logger.error(f"终止Chrome进程时出错: {e}")
    
    def start_chrome_debug_mode(self) -> bool:
        """启动Chrome调试模式"""
        if self.is_chrome_debug_running():
            self.logger.info("Chrome调试模式已在运行")
            return True
        
        chrome_path = self.find_chrome_executable()
        if not chrome_path:
            return False
        
        try:
            # 先关闭所有Chrome进程
            self.kill_chrome_processes()
            time.sleep(2)
            
            # 创建用户数据目录
            os.makedirs(self.user_data_dir, exist_ok=True)
            
            # 启动Chrome调试模式（使用简化参数）
            cmd = [
                chrome_path,
                f"--remote-debugging-port={self.debug_port}",
                f"--user-data-dir={self.user_data_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "https://www.linkedin.com/feed/",  # 直接打开LinkedIn页面
            ]
            
            self.logger.info(f"启动Chrome调试模式: 端口 {self.debug_port}")
            self.logger.debug(f"启动命令: {' '.join(cmd)}")
            # 暂时不隐藏错误输出以便调试
            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            self.logger.debug(f"Chrome进程PID: {process.pid}")
            
            # 等待Chrome启动并检查调试端口
            for i in range(30):  # 增加等待时间到30秒
                time.sleep(1)
                if self._check_debug_port_available():
                    self.logger.info("Chrome调试模式启动成功")
                    # 额外等待1秒确保完全就绪
                    time.sleep(1)
                    return True
                if i % 3 == 0:  # 每3秒输出一次进度
                    self.logger.info(f"等待Chrome启动... ({i+1}/30)")
            
            self.logger.error("Chrome调试模式启动超时")
            return False
            
        except Exception as e:
            self.logger.error(f"启动Chrome调试模式失败: {e}")
            return False
    
    def setup_driver(self) -> bool:
        """设置WebDriver连接到现有Chrome实例"""
        try:
            chrome_options = Options()
            chrome_options.add_experimental_option("debuggerAddress", f"localhost:{self.debug_port}")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            
            # 查找chromedriver
            chromedriver_path = self._find_chromedriver()
            if not chromedriver_path:
                self.logger.error("未找到chromedriver")
                return False
            
            service = Service(chromedriver_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # 设置超时
            timeout = config.get_setting('browser.page_load_timeout', 30)
            self.driver.set_page_load_timeout(timeout)
            
            self.logger.info("WebDriver设置成功")
            
            # 立即查找或创建LinkedIn标签页，避免连接到错误的窗口
            if not self.find_or_create_linkedin_tab():
                self.logger.warning("无法找到或创建LinkedIn标签页，将在navigate_to_linkedin时处理")
            
            return True
            
        except Exception as e:
            self.logger.error(f"设置WebDriver失败: {e}")
            
            # 如果连接失败，尝试自动启动Chrome调试模式
            if "cannot connect to chrome" in str(e).lower() or "chrome not reachable" in str(e).lower():
                self.logger.info("检测到Chrome调试模式未启动，正在自动启动...")
                if self.start_chrome_debug_mode():
                    self.logger.info("Chrome调试模式启动成功，重试连接...")
                    # 等待Chrome完全启动
                    time.sleep(3)
                    
                    # 重试连接
                    try:
                        service = Service(chromedriver_path)
                        self.driver = webdriver.Chrome(service=service, options=chrome_options)
                        
                        # 设置超时
                        timeout = config.get_setting('browser.page_load_timeout', 30)
                        self.driver.set_page_load_timeout(timeout)
                        
                        self.logger.info("WebDriver重试连接成功")
                        
                        # 立即查找或创建LinkedIn标签页
                        if not self.find_or_create_linkedin_tab():
                            self.logger.warning("无法找到或创建LinkedIn标签页，将在navigate_to_linkedin时处理")
                        
                        return True
                        
                    except Exception as retry_e:
                        self.logger.error(f"重试连接WebDriver失败: {retry_e}")
                        return False
                else:
                    self.logger.error("自动启动Chrome调试模式失败")
                    return False
            
            return False
    
    def _find_chromedriver(self) -> Optional[str]:
        """查找chromedriver路径"""
        possible_paths = [
            "chromedriver.exe",
            "chromedriver-win64/chromedriver.exe",
            os.path.join(os.getcwd(), "chromedriver.exe"),
            os.path.join(os.getcwd(), "chromedriver-win64", "chromedriver.exe")
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def find_or_create_linkedin_tab(self) -> bool:
        """查找或创建LinkedIn标签页"""
        if not self.driver:
            self.logger.error("WebDriver未初始化")
            return False
        
        try:
            # 获取所有窗口句柄
            all_handles = self.driver.window_handles
            linkedin_handle = None
            
            # 查找有效的LinkedIn标签页
            for handle in all_handles:
                try:
                    self.driver.switch_to.window(handle)
                    current_url = self.driver.current_url
                    
                    # 检查是否是有效的LinkedIn页面（排除错误页面如data/LinkedIn）
                    if ("linkedin.com" in current_url.lower() and 
                        "data/LinkedIn" not in current_url and
                        "chrome-error://" not in current_url):
                        linkedin_handle = handle
                        self.logger.info(f"找到现有LinkedIn标签页: {current_url}")
                        break
                except Exception as e:
                    self.logger.debug(f"检查窗口 {handle} 时出错: {e}")
                    continue
            
            # 如果没有找到有效的LinkedIn标签页，创建新的
            if not linkedin_handle:
                self.logger.info("创建新的LinkedIn标签页")
                try:
                    self.driver.execute_script("window.open('https://www.linkedin.com/feed/', '_blank');")
                    time.sleep(2)  # 等待新标签页加载
                    
                    # 切换到新标签页
                    new_handles = self.driver.window_handles
                    for handle in new_handles:
                        if handle not in all_handles:
                            self.driver.switch_to.window(handle)
                            linkedin_handle = handle
                            break
                except Exception as e:
                    self.logger.error(f"创建新标签页失败: {e}")
                    return False
            
            if linkedin_handle:
                self.driver.switch_to.window(linkedin_handle)
                self.logger.info("成功切换到LinkedIn标签页")
                return True
            else:
                self.logger.error("无法创建或切换到LinkedIn标签页")
                return False
                
        except Exception as e:
            self.logger.error(f"查找或创建LinkedIn标签页失败: {e}")
            return False
    
    def wait_for_page_load(self, timeout: int = 10) -> bool:
        """等待页面加载完成"""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            return True
        except TimeoutException:
            self.logger.warning(f"页面加载超时 ({timeout}秒)")
            return False
    
    def check_login_status(self) -> bool:
        """检查LinkedIn登录状态"""
        if not self.driver:
            return False
        
        try:
            # 检查是否在LinkedIn页面
            if "linkedin.com" not in self.driver.current_url.lower():
                self.driver.get("https://www.linkedin.com")
                self.wait_for_page_load()
            
            # 检查登录状态的多个指标
            login_indicators = [
                "//a[contains(@href, '/me')]",  # 个人资料链接
                "//button[contains(@class, 'global-nav__primary-link-me')]",  # 导航栏中的"我"按钮
                "//div[contains(@class, 'feed-identity-module')]",  # 动态页面的身份模块
                "//input[@placeholder='搜索' or @placeholder='Search']",  # 搜索框
            ]
            
            for indicator in login_indicators:
                try:
                    element = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((By.XPATH, indicator))
                    )
                    if element:
                        self.logger.info("用户已登录LinkedIn")
                        return True
                except TimeoutException:
                    continue
            
            self.logger.warning("用户未登录LinkedIn")
            return False
            
        except Exception as e:
            self.logger.error(f"检查登录状态失败: {e}")
            return False
    
    def navigate_to_linkedin(self) -> bool:
        """导航到LinkedIn主页"""
        if not self.driver:
            return False
        
        try:
            self.logger.info("导航到LinkedIn主页")
            
            # 首先确保我们在正确的LinkedIn标签页
            if not self.find_or_create_linkedin_tab():
                self.logger.error("无法找到或创建LinkedIn标签页")
                return False
            
            # 检查当前URL，如果不是LinkedIn或者是错误的页面，则导航到正确页面
            current_url = self.driver.current_url
            if "linkedin.com" not in current_url.lower() or "data/LinkedIn" in current_url:
                self.logger.info(f"当前URL不正确: {current_url}，导航到LinkedIn主页")
                self.driver.get("https://www.linkedin.com/feed/")
            
            return self.wait_for_page_load()
        except Exception as e:
            self.logger.error(f"导航到LinkedIn失败: {e}")
            return False
    
    def close(self) -> None:
        """关闭浏览器管理器"""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("WebDriver已关闭")
            except Exception as e:
                self.logger.error(f"关闭WebDriver失败: {e}")
            finally:
                self.driver = None
    
    def cleanup(self) -> None:
        """清理浏览器资源（与close方法相同）"""
        self.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()