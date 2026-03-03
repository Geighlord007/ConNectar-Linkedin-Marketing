import re
import time
import random
import hashlib
from typing import List, Dict, Any, Optional, Union
from urllib.parse import urlparse, parse_qs
import json
from datetime import datetime, timedelta

def validate_linkedin_url(url: str) -> bool:
    """验证LinkedIn URL格式
    
    Args:
        url: LinkedIn URL
    
    Returns:
        是否为有效的LinkedIn URL
    """
    if not url:
        return False
    
    # LinkedIn URL模式
    patterns = [
        r'^https?://(?:www\.)?linkedin\.com/in/[\w\-]+/?$',
        r'^https?://(?:www\.)?linkedin\.com/pub/[\w\-]+/[\w\-]+/[\w\-]+/[\w\-]+/?$'
    ]
    
    return any(re.match(pattern, url) for pattern in patterns)

def extract_linkedin_id(url: str) -> Optional[str]:
    """从LinkedIn URL中提取用户ID
    
    Args:
        url: LinkedIn URL
    
    Returns:
        用户ID或None
    """
    if not validate_linkedin_url(url):
        return None
    
    # 提取 /in/ 后面的部分
    match = re.search(r'/in/([\w\-]+)', url)
    if match:
        return match.group(1)
    
    return None

def clean_text(text: str) -> str:
    """清理文本内容
    
    Args:
        text: 原始文本
    
    Returns:
        清理后的文本
    """
    if not text:
        return ""
    
    # 移除多余的空白字符
    text = re.sub(r'\s+', ' ', text.strip())
    
    # 移除特殊字符（保留基本标点）
    text = re.sub(r'[^\w\s\-.,!?()\u4e00-\u9fff]', '', text)
    
    return text

def generate_contact_hash(name: str, company: str = "", linkedin_url: str = "") -> str:
    """生成联系人唯一哈希值
    
    Args:
        name: 姓名
        company: 公司
        linkedin_url: LinkedIn URL
    
    Returns:
        哈希值
    """
    # 使用姓名+公司或LinkedIn URL生成哈希
    if linkedin_url:
        unique_string = linkedin_url.lower()
    else:
        unique_string = f"{name.lower()}_{company.lower()}"
    
    return hashlib.md5(unique_string.encode('utf-8')).hexdigest()[:16]

def random_delay(min_seconds: float, max_seconds: float) -> None:
    """随机延迟
    
    Args:
        min_seconds: 最小延迟秒数
        max_seconds: 最大延迟秒数
    """
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)

def format_number(num: Union[int, str]) -> int:
    """格式化数字字符串
    
    Args:
        num: 数字或数字字符串（如 "500+", "1K", "2.5K"）
    
    Returns:
        整数值
    """
    if isinstance(num, int):
        return num
    
    if not isinstance(num, str):
        return 0
    
    # 移除非数字字符（除了小数点和K/M）
    num_str = re.sub(r'[^\d.KM]', '', num.upper())
    
    if not num_str:
        return 0
    
    try:
        if 'K' in num_str:
            return int(float(num_str.replace('K', '')) * 1000)
        elif 'M' in num_str:
            return int(float(num_str.replace('M', '')) * 1000000)
        else:
            return int(float(num_str))
    except ValueError:
        return 0

def extract_keywords_from_text(text: str, min_length: int = 2) -> List[str]:
    """从文本中提取关键词
    
    Args:
        text: 输入文本
        min_length: 最小关键词长度
    
    Returns:
        关键词列表
    """
    if not text:
        return []
    
    # 分词（简单的基于空格和标点的分词）
    words = re.findall(r'\b\w+\b', text.lower())
    
    # 过滤停用词和短词
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should'}
    
    keywords = [word for word in words if len(word) >= min_length and word not in stop_words]
    
    return list(set(keywords))  # 去重

def calculate_similarity(text1: str, text2: str) -> float:
    """计算两个文本的相似度
    
    Args:
        text1: 文本1
        text2: 文本2
    
    Returns:
        相似度分数 (0-1)
    """
    if not text1 or not text2:
        return 0.0
    
    # 提取关键词
    keywords1 = set(extract_keywords_from_text(text1))
    keywords2 = set(extract_keywords_from_text(text2))
    
    if not keywords1 or not keywords2:
        return 0.0
    
    # 计算Jaccard相似度
    intersection = len(keywords1.intersection(keywords2))
    union = len(keywords1.union(keywords2))
    
    return intersection / union if union > 0 else 0.0

def validate_email(email: str) -> bool:
    """验证邮箱格式
    
    Args:
        email: 邮箱地址
    
    Returns:
        是否为有效邮箱
    """
    if not email:
        return False
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def safe_get_nested_value(data: Dict[str, Any], key_path: str, default: Any = None) -> Any:
    """安全获取嵌套字典值
    
    Args:
        data: 字典数据
        key_path: 键路径，如 'user.profile.name'
        default: 默认值
    
    Returns:
        值或默认值
    """
    keys = key_path.split('.')
    current = data
    
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    
    return current

def format_duration(seconds: float) -> str:
    """格式化时间持续时间
    
    Args:
        seconds: 秒数
    
    Returns:
        格式化的时间字符串
    """
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}分钟"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}小时"

def create_backup_filename(original_path: str) -> str:
    """创建备份文件名
    
    Args:
        original_path: 原始文件路径
    
    Returns:
        备份文件路径
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name, ext = os.path.splitext(original_path)
    return f"{name}_backup_{timestamp}{ext}"

def is_business_hours(timezone_offset: int = 8) -> bool:
    """检查是否为工作时间
    
    Args:
        timezone_offset: 时区偏移（默认为北京时间+8）
    
    Returns:
        是否为工作时间
    """
    now = datetime.now() + timedelta(hours=timezone_offset)
    hour = now.hour
    weekday = now.weekday()  # 0=Monday, 6=Sunday
    
    # 工作日的9-18点
    return weekday < 5 and 9 <= hour < 18

def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """将列表分块
    
    Args:
        lst: 原始列表
        chunk_size: 块大小
    
    Returns:
        分块后的列表
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

def save_json_file(data: Any, file_path: str, indent: int = 2) -> bool:
    """保存JSON文件
    
    Args:
        data: 要保存的数据
        file_path: 文件路径
        indent: 缩进
    
    Returns:
        是否保存成功
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        return True
    except Exception:
        return False

def load_json_file(file_path: str, default: Any = None) -> Any:
    """加载JSON文件
    
    Args:
        file_path: 文件路径
        default: 默认值
    
    Returns:
        加载的数据或默认值
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default

import os  # 添加缺失的导入