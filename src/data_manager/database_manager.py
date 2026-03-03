import os
import sqlite3
import json
import csv
import pandas as pd
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta

from ..utils.logger import get_logger
from ..utils.helpers import save_json_file, load_json_file

class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_path: str = None):
        """初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径
        """
        self.logger = get_logger("database_manager")
        
        if not db_path:
            db_path = os.path.join(os.getcwd(), 'database', 'contacts.db')
        
        self.db_path = db_path
        
        # 如果历史路径存在则迁移到新位置（data/ → database/）
        self._ensure_database_location()
        
        # 确保目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # 初始化数据库
        self._init_database()
        
        self.logger.info(f"数据库管理器初始化完成: {self.db_path}")
    
    def _init_database(self):
        """初始化数据库和表结构"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 启用外键约束
                cursor.execute('PRAGMA foreign_keys = ON')
                
                # 创建联系人表（旧字段保留，新增字段以兼容新方案）
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
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        match_score REAL DEFAULT NULL,
                        source_file TEXT DEFAULT ''
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
                        FOREIGN KEY (contact_id) REFERENCES contacts (id) ON DELETE CASCADE,
                        UNIQUE(contact_id, tag_name)
                    )
                ''')
                
                # 创建营销记录表（保留旧字段，新增字段以兼容新方案）
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
                        -- 新字段
                        message TEXT,
                        sent_at TIMESTAMP,
                        error TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (contact_id) REFERENCES contacts (id) ON DELETE CASCADE
                    )
                ''')
                
                # 新增：筛选运行记录表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS filter_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file TEXT NOT NULL,
                        total INTEGER DEFAULT 0,
                        passed INTEGER DEFAULT 0,
                        min_score REAL DEFAULT 0.0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # 创建搜索历史表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS search_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword TEXT NOT NULL,
                        results_count INTEGER DEFAULT 0,
                        search_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        search_duration REAL,
                        success BOOLEAN DEFAULT 1
                    )
                ''')
                
                # 创建系统配置表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS system_config (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        description TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # 迁移/补齐缺失列
                self._migrate_schema(cursor)

                # 创建索引
                self._create_indexes(cursor)
                
                # 插入默认配置
                self._insert_default_config(cursor)
                
                conn.commit()
                self.logger.debug("数据库初始化完成")
                
        except Exception as e:
            self.logger.error(f"初始化数据库失败: {e}")
            raise
    
    def _ensure_database_location(self) -> None:
        """确保数据库存放在 database/ 目录下，并将历史 data/ 目录中的 DB 平滑迁移。
        """
        try:
            new_dir = os.path.dirname(self.db_path)
            os.makedirs(new_dir, exist_ok=True)
            old_path = os.path.join(os.getcwd(), 'data', 'contacts.db')
            if not os.path.exists(self.db_path) and os.path.exists(old_path):
                try:
                    import shutil
                    shutil.move(old_path, self.db_path)
                    self.logger.info(f"已迁移数据库文件: {old_path} → {self.db_path}")
                except Exception as move_err:
                    self.logger.warning(f"移动数据库失败，尝试复制: {move_err}")
                    try:
                        import shutil
                        shutil.copy2(old_path, self.db_path)
                        self.logger.info(f"已复制数据库文件: {old_path} → {self.db_path}")
                    except Exception as copy_err:
                        self.logger.error(f"复制数据库失败: {copy_err}")
        except Exception as e:
            self.logger.warning(f"检查数据库位置时出现问题: {e}")

    def _migrate_schema(self, cursor) -> None:
        """根据现有表结构补齐缺失列，尽量不破坏历史数据。"""
        try:
            def column_exists(table: str, col: str) -> bool:
                cursor.execute(f"PRAGMA table_info({table})")
                cols = [r[1] for r in cursor.fetchall()]
                return col in cols

            # contacts: match_score, source_file
            if not column_exists('contacts', 'match_score'):
                cursor.execute('ALTER TABLE contacts ADD COLUMN match_score REAL')
            if not column_exists('contacts', 'source_file'):
                cursor.execute("ALTER TABLE contacts ADD COLUMN source_file TEXT DEFAULT ''")

            # marketing_records: message, sent_at, error
            if not column_exists('marketing_records', 'message'):
                cursor.execute('ALTER TABLE marketing_records ADD COLUMN message TEXT')
            if not column_exists('marketing_records', 'sent_at'):
                cursor.execute('ALTER TABLE marketing_records ADD COLUMN sent_at TIMESTAMP')
            if not column_exists('marketing_records', 'error'):
                cursor.execute('ALTER TABLE marketing_records ADD COLUMN error TEXT')

            # filter_runs: 若不存在则创建（上方已 CREATE IF NOT EXISTS）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS filter_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file TEXT NOT NULL,
                    total INTEGER DEFAULT 0,
                    passed INTEGER DEFAULT 0,
                    min_score REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        except Exception as e:
            self.logger.warning(f"迁移schema时出现问题: {e}")

    def _create_indexes(self, cursor):
        """创建数据库索引"""
        indexes = [
            'CREATE INDEX IF NOT EXISTS idx_contacts_hash ON contacts(contact_hash)',
            'CREATE INDEX IF NOT EXISTS idx_contacts_linkedin ON contacts(linkedin_url)',
            'CREATE INDEX IF NOT EXISTS idx_contacts_keyword ON contacts(search_keyword)',
            'CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company)',
            'CREATE INDEX IF NOT EXISTS idx_contacts_location ON contacts(location)',
            'CREATE INDEX IF NOT EXISTS idx_contacts_created ON contacts(created_at)',
            'CREATE INDEX IF NOT EXISTS idx_tags_contact ON contact_tags(contact_id)',
            'CREATE INDEX IF NOT EXISTS idx_tags_name ON contact_tags(tag_name)',
            'CREATE INDEX IF NOT EXISTS idx_marketing_contact ON marketing_records(contact_id)',
            'CREATE INDEX IF NOT EXISTS idx_marketing_type ON marketing_records(action_type)',
            'CREATE INDEX IF NOT EXISTS idx_marketing_status ON marketing_records(status)',
            'CREATE INDEX IF NOT EXISTS idx_search_keyword ON search_history(keyword)',
            'CREATE INDEX IF NOT EXISTS idx_search_date ON search_history(search_date)'
        ]
        
        for index_sql in indexes:
            cursor.execute(index_sql)

        # 确保 linkedin_url 唯一索引（已在表定义中 UNIQUE，但再次创建以防历史库）
        try:
            cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_contacts_linkedin ON contacts(linkedin_url)')
        except Exception:
            pass
    
    def _insert_default_config(self, cursor):
        """插入默认系统配置"""
        default_configs = [
            ('db_version', '2.0', '数据库版本'),
            ('last_backup', '', '最后备份时间'),
            ('auto_cleanup_days', '30', '自动清理天数'),
            ('max_contacts_per_keyword', '1000', '每个关键词最大联系人数')
        ]
        
        for key, value, description in default_configs:
            cursor.execute(
                'INSERT OR IGNORE INTO system_config (key, value, description) VALUES (?, ?, ?)',
                (key, value, description)
            )

    # =====================
    # 数据导入（精简 JSON）
    # =====================
    def import_trimmed_json(self, json_file_path: str) -> Dict[str, int]:
        """导入 processed/trimmed_contacts_*.json 到 contacts。
        要求每条记录至少包含 name、linkedin_url，可选 match_score、title、company、location、source_file。
        linkedin_url 唯一，重复跳过。
        """
        stats = {'imported': 0, 'updated': 0, 'skipped': 0, 'errors': 0, 'total': 0}
        try:
            data = load_json_file(json_file_path)
            if isinstance(data, dict) and 'contacts' in data:
                contacts = data.get('contacts') or []
            elif isinstance(data, list):
                contacts = data
            else:
                self.logger.error("不支持的JSON格式（需为列表或包含 contacts 字段）")
                return stats

            stats['total'] = len(contacts)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for c in contacts:
                    try:
                        name = (c.get('name') or '').strip()
                        linkedin_url = (c.get('linkedin_url') or '').strip()
                        if not name or not linkedin_url:
                            stats['skipped'] += 1
                            continue

                        # 尝试插入；若已存在则进行更新（upsert-like）
                        try:
                            cursor.execute('''
                                INSERT INTO contacts (name, title, company, location, linkedin_url, match_score, source_file, created_at, updated_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                            ''', (
                                name,
                                (c.get('title') or ''),
                                (c.get('company') or ''),
                                (c.get('location') or ''),
                                linkedin_url,
                                float(c.get('match_score')) if c.get('match_score') is not None else None,
                                c.get('source_file') or os.path.basename(json_file_path)
                            ))
                            stats['imported'] += 1
                        except Exception:
                            # 可能已存在：做更新（仅在新值非空时覆盖；match_score 若为空则不变）
                            try:
                                title = (c.get('title') or '').strip()
                                company = (c.get('company') or '').strip()
                                location = (c.get('location') or '').strip()
                                score = c.get('match_score')
                                source_file = c.get('source_file') or os.path.basename(json_file_path)
                                # 仅当现有字段为空时更新文本字段；match_score 用 COALESCE 保留旧值
                                cursor.execute('''
                                    UPDATE contacts
                                    SET 
                                        title = CASE WHEN (title IS NULL OR title = '') AND ? != '' THEN ? ELSE title END,
                                        company = CASE WHEN (company IS NULL OR company = '') AND ? != '' THEN ? ELSE company END,
                                        location = CASE WHEN (location IS NULL OR location = '') AND ? != '' THEN ? ELSE location END,
                                        match_score = COALESCE(?, match_score),
                                        source_file = CASE WHEN (source_file IS NULL OR source_file = '') AND ? != '' THEN ? ELSE source_file END,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE linkedin_url = ?
                                ''', (
                                    title, title,
                                    company, company,
                                    location, location,
                                    float(score) if score is not None else None,
                                    source_file, source_file,
                                    linkedin_url
                                ))
                                # 判断是否实际更新了行：sqlite3 无法直接获取受影响行的列变更，这里按执行成功计更新
                                stats['updated'] += 1
                            except Exception:
                                stats['skipped'] += 1
                    except Exception as row_err:
                        self.logger.warning(f"导入记录失败: {row_err}")
                        stats['errors'] += 1
                conn.commit()
            self.logger.info(f"精简JSON导入完成: 导入 {stats['imported']}, 跳过 {stats['skipped']}, 错误 {stats['errors']}")
            return stats
        except Exception as e:
            self.logger.error(f"导入精简JSON失败: {e}")
            stats['errors'] = stats.get('errors', 0) + 1
            return stats

    # =====================
    # 触达排队（连接请求）
    # =====================
    def get_contacts_for_outreach(self, limit: int = 50, min_score: float = 0.0) -> List[Dict[str, Any]]:
        """按 match_score 降序获取尚未触达（无 connect 已发送/已接受记录）的联系人。"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT c.* FROM contacts c
                    LEFT JOIN (
                        SELECT DISTINCT contact_id FROM marketing_records
                        WHERE action_type = 'connect' AND status IN ('pending','sent','accepted')
                    ) mr ON mr.contact_id = c.id
                    WHERE mr.contact_id IS NULL AND (c.match_score IS NULL OR c.match_score >= ?)
                    ORDER BY COALESCE(c.match_score, 0) DESC, c.created_at DESC
                    LIMIT ?
                ''', (min_score, limit))
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            self.logger.error(f"获取待触达联系人失败: {e}")
            return []

    def enqueue_connect_requests(self, message: str, limit: int = 50, min_score: float = 0.0) -> Dict[str, int]:
        """将按分数挑选的联系人写入 marketing_records，标记为 pending。
        不实际发送，仅写入排队记录。
        """
        stats = {'queued': 0, 'skipped': 0}
        try:
            targets = self.get_contacts_for_outreach(limit=limit, min_score=min_score)
            if not targets:
                return stats
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for c in targets:
                    try:
                        cursor.execute('''
                            INSERT INTO marketing_records (contact_id, action_type, status, message, created_at)
                            VALUES (?, 'connect', 'pending', ?, CURRENT_TIMESTAMP)
                        ''', (c['id'], message))
                        stats['queued'] += 1
                    except Exception:
                        stats['skipped'] += 1
                conn.commit()
            return stats
        except Exception as e:
            self.logger.error(f"写入连接请求排队失败: {e}")
            return stats
    
    def import_from_json(self, json_file_path: str) -> Dict[str, int]:
        """从JSON文件导入数据
        
        Args:
            json_file_path: JSON文件路径
        
        Returns:
            导入统计信息
        """
        stats = {'imported': 0, 'skipped': 0, 'errors': 0}
        
        try:
            data = load_json_file(json_file_path)
            if not data:
                self.logger.error(f"无法加载JSON文件: {json_file_path}")
                return stats
            
            # 处理不同的JSON格式
            contacts = []
            if 'contacts' in data:
                contacts = data['contacts']
            elif isinstance(data, list):
                contacts = data
            else:
                self.logger.error("不支持的JSON格式")
                return stats
            
            self.logger.info(f"开始从JSON文件导入 {len(contacts)} 个联系人")
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for contact in contacts:
                    try:
                        if self._import_single_contact(cursor, contact):
                            stats['imported'] += 1
                        else:
                            stats['skipped'] += 1
                    except Exception as e:
                        self.logger.warning(f"导入联系人失败: {e}")
                        stats['errors'] += 1
                
                conn.commit()
            
            self.logger.info(f"JSON导入完成: 导入 {stats['imported']}, 跳过 {stats['skipped']}, 错误 {stats['errors']}")
            return stats
            
        except Exception as e:
            self.logger.error(f"从JSON导入数据失败: {e}")
            stats['errors'] = 1
            return stats
    
    def _import_single_contact(self, cursor, contact: Dict[str, Any]) -> bool:
        """导入单个联系人"""
        try:
            # 验证必需字段 - 只要求name字段
            if not contact.get('name'):
                return False
            
            # 检查是否已存在 - 如果有linkedin_url则用它检查，否则用name检查
            linkedin_url = contact.get('linkedin_url')
            if linkedin_url:
                cursor.execute(
                    'SELECT id FROM contacts WHERE linkedin_url = ?',
                    (linkedin_url,)
                )
            else:
                # 如果没有linkedin_url，用name和company组合检查重复
                cursor.execute(
                    'SELECT id FROM contacts WHERE name = ? AND company = ?',
                    (contact['name'], contact.get('company', ''))
                )
            
            if cursor.fetchone():
                return False  # 已存在，跳过
            
            # 插入联系人
            cursor.execute('''
                INSERT INTO contacts (
                    contact_hash, name, title, company, location, linkedin_url,
                    profile_image_url, description, connections_count, search_keyword, extracted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                contact.get('contact_hash', ''),
                contact['name'],
                contact.get('title', ''),
                contact.get('company', ''),
                contact.get('location', ''),
                contact.get('linkedin_url', ''),  # 允许为空
                contact.get('profile_image_url', ''),
                contact.get('description', ''),
                contact.get('connections_count', 0),
                contact.get('search_keyword', ''),
                contact.get('extracted_at', datetime.now().isoformat())
            ))
            
            return True
            
        except Exception as e:
            self.logger.warning(f"导入单个联系人失败: {e}")
            return False
    
    def export_to_json(self, output_path: str, filters: Dict[str, Any] = None) -> bool:
        """导出数据到JSON文件
        
        Args:
            output_path: 输出文件路径
            filters: 过滤条件
        
        Returns:
            是否导出成功
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
                    for key, value in filters.items():
                        if key == 'keyword':
                            conditions.append("search_keyword = ?")
                            params.append(value)
                        elif key == 'company':
                            conditions.append("company LIKE ?")
                            params.append(f"%{value}%")
                        elif key == 'location':
                            conditions.append("location LIKE ?")
                            params.append(f"%{value}%")
                    
                    if conditions:
                        query += " WHERE " + " AND ".join(conditions)
                
                query += " ORDER BY created_at DESC"
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                # 转换为字典列表
                contacts = [dict(row) for row in rows]
                
                # 构建导出数据
                export_data = {
                    'export_date': datetime.now().isoformat(),
                    'total_contacts': len(contacts),
                    'filters': filters or {},
                    'contacts': contacts
                }
                
                # 保存到文件
                if save_json_file(export_data, output_path):
                    self.logger.info(f"成功导出 {len(contacts)} 个联系人到: {output_path}")
                    return True
                else:
                    return False
                    
        except Exception as e:
            self.logger.error(f"导出到JSON失败: {e}")
            return False
    
    def export_to_csv(self, output_path: str, filters: Dict[str, Any] = None) -> bool:
        """导出数据到CSV文件
        
        Args:
            output_path: 输出文件路径
            filters: 过滤条件
        
        Returns:
            是否导出成功
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 构建查询
                query = "SELECT * FROM contacts"
                params = []
                
                if filters:
                    conditions = []
                    for key, value in filters.items():
                        if key == 'keyword':
                            conditions.append("search_keyword = ?")
                            params.append(value)
                        elif key == 'company':
                            conditions.append("company LIKE ?")
                            params.append(f"%{value}%")
                        elif key == 'location':
                            conditions.append("location LIKE ?")
                            params.append(f"%{value}%")
                    
                    if conditions:
                        query += " WHERE " + " AND ".join(conditions)
                
                query += " ORDER BY created_at DESC"
                
                # 使用pandas导出CSV
                df = pd.read_sql_query(query, conn, params=params)
                df.to_csv(output_path, index=False, encoding='utf-8-sig')
                
                self.logger.info(f"成功导出 {len(df)} 个联系人到CSV: {output_path}")
                return True
                
        except Exception as e:
            self.logger.error(f"导出到CSV失败: {e}")
            return False
    
    def backup_database(self, backup_path: str = None) -> bool:
        """备份数据库
        
        Args:
            backup_path: 备份文件路径
        
        Returns:
            是否备份成功
        """
        try:
            if not backup_path:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_dir = os.path.join(os.path.dirname(self.db_path), 'backups')
                os.makedirs(backup_dir, exist_ok=True)
                backup_path = os.path.join(backup_dir, f'contacts_backup_{timestamp}.db')
            
            # 创建备份
            with sqlite3.connect(self.db_path) as source:
                with sqlite3.connect(backup_path) as backup:
                    source.backup(backup)
            
            # 更新备份时间配置
            self.set_config('last_backup', datetime.now().isoformat())
            
            self.logger.info(f"数据库备份成功: {backup_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"数据库备份失败: {e}")
            return False
    
    def restore_database(self, backup_path: str) -> bool:
        """从备份恢复数据库
        
        Args:
            backup_path: 备份文件路径
        
        Returns:
            是否恢复成功
        """
        try:
            if not os.path.exists(backup_path):
                self.logger.error(f"备份文件不存在: {backup_path}")
                return False
            
            # 创建当前数据库的备份
            current_backup = f"{self.db_path}.before_restore"
            with sqlite3.connect(self.db_path) as source:
                with sqlite3.connect(current_backup) as backup:
                    source.backup(backup)
            
            # 从备份恢复
            with sqlite3.connect(backup_path) as source:
                with sqlite3.connect(self.db_path) as target:
                    source.backup(target)
            
            self.logger.info(f"数据库恢复成功，原数据库备份到: {current_backup}")
            return True
            
        except Exception as e:
            self.logger.error(f"数据库恢复失败: {e}")
            return False
    
    def cleanup_old_data(self, days: int = 30) -> int:
        """清理旧数据
        
        Args:
            days: 保留天数
        
        Returns:
            清理的记录数
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 清理旧的搜索历史
                cursor.execute(
                    "DELETE FROM search_history WHERE search_date < ?",
                    (cutoff_date.isoformat(),)
                )
                search_cleaned = cursor.rowcount
                
                # 清理旧的营销记录（已完成的）
                cursor.execute(
                    "DELETE FROM marketing_records WHERE created_at < ? AND status IN ('completed', 'failed')",
                    (cutoff_date.isoformat(),)
                )
                marketing_cleaned = cursor.rowcount
                
                conn.commit()
                
                total_cleaned = search_cleaned + marketing_cleaned
                if total_cleaned > 0:
                    self.logger.info(f"清理完成: 搜索历史 {search_cleaned} 条, 营销记录 {marketing_cleaned} 条")
                
                return total_cleaned
                
        except Exception as e:
            self.logger.error(f"清理旧数据失败: {e}")
            return 0
    
    def get_config(self, key: str) -> Optional[str]:
        """获取系统配置"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM system_config WHERE key = ?", (key,))
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            self.logger.error(f"获取配置失败: {e}")
            return None
    
    def set_config(self, key: str, value: str, description: str = None) -> bool:
        """设置系统配置"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO system_config (key, value, description, updated_at) VALUES (?, ?, ?, ?)",
                    (key, value, description, datetime.now().isoformat())
                )
                conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"设置配置失败: {e}")
            return False
    
    def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                stats = {}
                
                # 表记录数统计
                tables = ['contacts', 'contact_tags', 'marketing_records', 'search_history']
                for table in tables:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    stats[f'{table}_count'] = cursor.fetchone()[0]
                # 兼容 CLI 展示字段
                stats['total_contacts'] = stats.get('contacts_count', 0)
                stats['total_tags'] = stats.get('contact_tags_count', 0)
                stats['total_marketing_records'] = stats.get('marketing_records_count', 0)
                
                # 数据库文件大小
                stats['db_size_mb'] = os.path.getsize(self.db_path) / (1024 * 1024)
                
                # 最后更新时间
                cursor.execute("SELECT MAX(updated_at) FROM contacts")
                last_update = cursor.fetchone()[0]
                stats['last_update'] = last_update
                
                return stats
                
        except Exception as e:
            self.logger.error(f"获取数据库统计失败: {e}")
            return {}