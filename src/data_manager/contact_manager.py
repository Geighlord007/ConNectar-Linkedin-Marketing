import os
import sqlite3
import json
import time
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta

from ..utils.logger import get_logger
from ..utils.helpers import generate_contact_hash, save_json_file, load_json_file

class ContactManager:
    """联系人数据管理器"""
    
    def __init__(self, db_path: str = None, data_dir: str = None):
        """初始化联系人管理器
        
        Args:
            db_path: 数据库文件路径
            data_dir: 数据目录路径
        """
        self.logger = get_logger("contact_manager")
        
        # 设置路径
        if not db_path:
            db_path = os.path.join(os.getcwd(), 'database', 'contacts.db')
        if not data_dir:
            data_dir = os.path.join(os.getcwd(), 'data')
        
        self.db_path = db_path
        self.data_dir = data_dir
        
        # 确保目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        
        # 初始化数据库
        self._init_database()
        
        self.logger.info(f"联系人管理器初始化完成，数据库: {self.db_path}")
    
    def _init_database(self):
        """初始化数据库表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 创建联系人表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS contacts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        contact_hash TEXT UNIQUE NOT NULL,
                        name TEXT NOT NULL,
                        title TEXT,
                        company TEXT,
                        location TEXT,
                        linkedin_url TEXT UNIQUE NOT NULL,
                        profile_image_url TEXT,
                        description TEXT,
                        connections_count INTEGER DEFAULT 0,
                        search_keyword TEXT,
                        extracted_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # 创建标签表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS contact_tags (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        contact_id INTEGER,
                        tag_name TEXT NOT NULL,
                        tag_value TEXT,
                        confidence_score REAL DEFAULT 0.0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (contact_id) REFERENCES contacts (id),
                        UNIQUE(contact_id, tag_name)
                    )
                ''')
                
                # 创建营销记录表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS marketing_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        contact_id INTEGER,
                        action_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        message_content TEXT,
                        response_content TEXT,
                        scheduled_at TIMESTAMP,
                        executed_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (contact_id) REFERENCES contacts (id)
                    )
                ''')
                
                # 创建索引
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_contacts_hash ON contacts(contact_hash)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_contacts_linkedin ON contacts(linkedin_url)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_contacts_keyword ON contacts(search_keyword)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_contact ON contact_tags(contact_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_marketing_contact ON marketing_records(contact_id)')
                
                conn.commit()
                self.logger.debug("数据库表初始化完成")
                
        except Exception as e:
            self.logger.error(f"初始化数据库失败: {e}")
            raise
    
    def add_contact(self, contact: Dict[str, Any]) -> bool:
        """添加单个联系人
        
        Args:
            contact: 联系人数据
        
        Returns:
            是否添加成功
        """
        try:
            result = self.add_contacts([contact])
            return result['added'] > 0 or result['updated'] > 0
        except Exception as e:
            self.logger.error(f"添加联系人失败: {e}")
            return False
    
    def add_contacts(self, contacts: List[Dict[str, Any]], batch_size: int = 100) -> Dict[str, int]:
        """批量添加联系人
        
        Args:
            contacts: 联系人列表
            batch_size: 批处理大小
        
        Returns:
            添加结果统计
        """
        stats = {
            'total': len(contacts),
            'added': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0
        }
        
        try:
            self.logger.info(f"开始批量添加 {len(contacts)} 个联系人")
            
            # 分批处理
            for i in range(0, len(contacts), batch_size):
                batch = contacts[i:i + batch_size]
                batch_stats = self._add_contacts_batch(batch)
                
                # 累计统计
                for key in stats:
                    if key != 'total':
                        stats[key] += batch_stats.get(key, 0)
                
                self.logger.debug(f"处理批次 {i//batch_size + 1}: {len(batch)} 个联系人")
            
            self.logger.info(f"批量添加完成: 新增 {stats['added']}, 更新 {stats['updated']}, 跳过 {stats['skipped']}, 错误 {stats['errors']}")
            return stats
            
        except Exception as e:
            self.logger.error(f"批量添加联系人失败: {e}")
            stats['errors'] = stats['total']
            return stats
    
    def _add_contacts_batch(self, contacts: List[Dict[str, Any]]) -> Dict[str, int]:
        """添加一批联系人（以 linkedin_url 为主键去重）"""
        stats = {'added': 0, 'updated': 0, 'skipped': 0, 'errors': 0}

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                for contact in contacts:
                    try:
                        if not self._validate_contact(contact):
                            stats['skipped'] += 1
                            continue

                        url = contact['linkedin_url']
                        contact_hash = contact.get('contact_hash') or generate_contact_hash(
                            contact['name'], contact.get('company', ''), url
                        )

                        # 优先按 linkedin_url 查找（唯一索引），再回退 hash
                        cursor.execute(
                            'SELECT id FROM contacts WHERE linkedin_url = ?', (url,)
                        )
                        existing = cursor.fetchone()
                        if not existing:
                            cursor.execute(
                                'SELECT id FROM contacts WHERE contact_hash = ?',
                                (contact_hash,),
                            )
                            existing = cursor.fetchone()

                        if existing:
                            if self._update_contact(cursor, existing[0], contact):
                                stats['updated'] += 1
                            else:
                                stats['skipped'] += 1
                        else:
                            if self._insert_contact(cursor, contact, contact_hash):
                                stats['added'] += 1
                            else:
                                stats['errors'] += 1

                    except Exception as e:
                        self.logger.warning(f"处理联系人失败: {e}")
                        stats['errors'] += 1
                        continue

                conn.commit()

        except Exception as e:
            self.logger.error(f"批量处理联系人失败: {e}")
            stats['errors'] = len(contacts)

        return stats
    
    def _validate_contact(self, contact: Dict[str, Any]) -> bool:
        """验证联系人数据"""
        required_fields = ['name', 'linkedin_url']
        
        for field in required_fields:
            if not contact.get(field):
                self.logger.debug(f"联系人缺少必需字段: {field}")
                return False
        
        # 验证LinkedIn URL格式
        linkedin_url = contact['linkedin_url']
        if not linkedin_url.startswith('https://www.linkedin.com/in/'):
            self.logger.debug(f"无效的LinkedIn URL: {linkedin_url}")
            return False
        
        return True
    
    def _insert_contact(self, cursor, contact: Dict[str, Any], contact_hash: str) -> bool:
        """插入新联系人"""
        try:
            cursor.execute('''
                INSERT INTO contacts (
                    contact_hash, name, title, company, location, linkedin_url,
                    search_keyword, extracted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                contact_hash,
                contact['name'],
                contact.get('title', ''),
                contact.get('company', ''),
                contact.get('location', ''),
                contact['linkedin_url'],
                contact.get('search_keyword', ''),
                contact.get('extracted_at', datetime.now().isoformat())
            ))
            return True
        except Exception as e:
            self.logger.warning(f"插入联系人失败: {e}")
            return False

    def _update_contact(self, cursor, contact_id: int, contact: Dict[str, Any]) -> bool:
        """更新现有联系人（仅用非空新值覆盖）"""
        try:
            cursor.execute('''
                UPDATE contacts SET
                    name = COALESCE(NULLIF(?, ''), name),
                    title = COALESCE(NULLIF(?, ''), title),
                    company = COALESCE(NULLIF(?, ''), company),
                    location = COALESCE(NULLIF(?, ''), location),
                    search_keyword = COALESCE(NULLIF(?, ''), search_keyword),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (
                contact.get('name', ''),
                contact.get('title', ''),
                contact.get('company', ''),
                contact.get('location', ''),
                contact.get('search_keyword', ''),
                contact_id
            ))
            return True
        except Exception as e:
            self.logger.warning(f"更新联系人失败: {e}")
            return False
    
    def get_contacts(self, filters: Dict[str, Any] = None, limit: int = None) -> List[Dict[str, Any]]:
        """获取联系人列表
        
        Args:
            filters: 过滤条件
            limit: 限制数量
        
        Returns:
            联系人列表
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # 构建查询
                query = "SELECT * FROM contacts"
                params = []
                
                if filters:
                    conditions = []
                    
                    if 'keyword' in filters:
                        conditions.append("search_keyword = ?")
                        params.append(filters['keyword'])
                    
                    if 'company' in filters:
                        conditions.append("company LIKE ?")
                        params.append(f"%{filters['company']}%")
                    
                    if 'location' in filters:
                        conditions.append("location LIKE ?")
                        params.append(f"%{filters['location']}%")
                    
                    if 'min_connections' in filters:
                        conditions.append("connections_count >= ?")
                        params.append(filters['min_connections'])
                    
                    if conditions:
                        query += " WHERE " + " AND ".join(conditions)
                
                query += " ORDER BY created_at DESC"
                
                if limit:
                    query += " LIMIT ?"
                    params.append(limit)
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                # 转换为字典列表
                contacts = [dict(row) for row in rows]
                
                self.logger.debug(f"获取到 {len(contacts)} 个联系人")
                return contacts
                
        except Exception as e:
            self.logger.error(f"获取联系人失败: {e}")
            return []
    
    def get_contact_by_id(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取联系人"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,))
                row = cursor.fetchone()
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            self.logger.error(f"获取联系人失败: {e}")
            return None
    
    def get_contacts_by_keyword(self, keyword: str) -> List[Dict[str, Any]]:
        """根据搜索关键词获取联系人"""
        return self.get_contacts({'keyword': keyword})
    
    def remove_duplicates(self) -> int:
        """移除重复的联系人
        
        Returns:
            移除的重复联系人数量
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 查找重复的联系人（基于LinkedIn URL）
                cursor.execute('''
                    SELECT linkedin_url, COUNT(*) as count, MIN(id) as keep_id
                    FROM contacts
                    GROUP BY linkedin_url
                    HAVING COUNT(*) > 1
                ''')
                
                duplicates = cursor.fetchall()
                removed_count = 0
                
                for linkedin_url, count, keep_id in duplicates:
                    # 删除除了最早的记录之外的所有重复记录
                    cursor.execute(
                        "DELETE FROM contacts WHERE linkedin_url = ? AND id != ?",
                        (linkedin_url, keep_id)
                    )
                    removed_count += count - 1
                
                conn.commit()
                
                if removed_count > 0:
                    self.logger.info(f"移除了 {removed_count} 个重复联系人")
                
                return removed_count
                
        except Exception as e:
            self.logger.error(f"移除重复联系人失败: {e}")
            return 0
    
    def export_contacts(self, output_path: str, filters: Dict[str, Any] = None) -> bool:
        """导出联系人到JSON文件
        
        Args:
            output_path: 输出文件路径
            filters: 过滤条件
        
        Returns:
            是否导出成功
        """
        try:
            contacts = self.get_contacts(filters)
            
            export_data = {
                'export_date': datetime.now().isoformat(),
                'total_contacts': len(contacts),
                'filters': filters or {},
                'contacts': contacts
            }
            
            if save_json_file(export_data, output_path):
                self.logger.info(f"成功导出 {len(contacts)} 个联系人到: {output_path}")
                return True
            else:
                self.logger.error(f"导出联系人失败: {output_path}")
                return False
                
        except Exception as e:
            self.logger.error(f"导出联系人时发生错误: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取联系人统计信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 总数统计
                cursor.execute("SELECT COUNT(*) FROM contacts")
                total_contacts = cursor.fetchone()[0]
                
                # 按关键词统计
                cursor.execute("""
                    SELECT search_keyword, COUNT(*) as count
                    FROM contacts
                    WHERE search_keyword != ''
                    GROUP BY search_keyword
                    ORDER BY count DESC
                """)
                keyword_stats = dict(cursor.fetchall())
                
                # 按公司统计
                cursor.execute("""
                    SELECT company, COUNT(*) as count
                    FROM contacts
                    WHERE company != ''
                    GROUP BY company
                    ORDER BY count DESC
                    LIMIT 10
                """)
                company_stats = dict(cursor.fetchall())
                
                # 按地区统计
                cursor.execute("""
                    SELECT location, COUNT(*) as count
                    FROM contacts
                    WHERE location != ''
                    GROUP BY location
                    ORDER BY count DESC
                    LIMIT 10
                """)
                location_stats = dict(cursor.fetchall())
                
                # 最近添加的联系人
                cursor.execute("""
                    SELECT DATE(created_at) as date, COUNT(*) as count
                    FROM contacts
                    WHERE created_at >= date('now', '-7 days')
                    GROUP BY DATE(created_at)
                    ORDER BY date DESC
                """)
                recent_stats = dict(cursor.fetchall())
                
                return {
                    'total_contacts': total_contacts,
                    'by_keyword': keyword_stats,
                    'by_company': company_stats,
                    'by_location': location_stats,
                    'recent_additions': recent_stats
                }
                
        except Exception as e:
            self.logger.error(f"获取统计信息失败: {e}")
            return {}