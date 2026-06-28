"""
طبقة قاعدة البيانات - كل التعامل مع SQLite يمر من هنا
يستخدم WAL mode للأداء الأفضل مع العمليات المتزامنة
"""
import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT UNIQUE NOT NULL,
    username TEXT,
    title TEXT,
    description TEXT,
    member_count INTEGER,
    archived_at TIMESTAMP,
    last_message_id INTEGER DEFAULT 0,
    oldest_message_id INTEGER DEFAULT 0,
    is_complete BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    date TIMESTAMP NOT NULL,
    text TEXT,
    message_link TEXT,
    has_media BOOLEAN DEFAULT 0,
    media_type TEXT,
    metadata TEXT,
    html_generated BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(channel_id, message_id)
);

CREATE TABLE IF NOT EXISTS media_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    file_id TEXT UNIQUE NOT NULL,
    file_type TEXT,
    file_name TEXT,
    file_size INTEGER,
    local_path TEXT,
    is_downloaded BOOLEAN DEFAULT 0,
    download_attempts INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_channel_date 
    ON messages(channel_id, date);
CREATE INDEX IF NOT EXISTS idx_messages_channel_id 
    ON messages(channel_id, message_id);
CREATE INDEX IF NOT EXISTS idx_media_downloaded 
    ON media_files(is_downloaded, channel_id);
"""

class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """تهيئة قاعدة البيانات وإنشاء الجداول"""
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            # WAL mode للأداء الأفضل
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=10000")
        logger.info(f"قاعدة البيانات جاهزة: {self.db_path}")
    
    @contextmanager
    def _conn(self):
        """Connection manager مع auto-commit/rollback"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    # ─── عمليات القنوات ───────────────────────────────
    
    def upsert_channel(self, channel_data: Dict) -> None:
        """إضافة أو تحديث معلومات قناة"""
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO channels 
                    (channel_id, username, title, description, member_count, archived_at)
                VALUES (:channel_id, :username, :title, :description, :member_count, :archived_at)
                ON CONFLICT(channel_id) DO UPDATE SET
                    title = excluded.title,
                    member_count = excluded.member_count,
                    archived_at = excluded.archived_at
            """, channel_data)
    
    def get_channel(self, channel_id: str) -> Optional[Dict]:
        """استرجاع معلومات قناة"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_all_channels(self) -> List[Dict]:
        """استرجاع كل القنوات المؤرشفة"""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM channels").fetchall()
            return [dict(r) for r in rows]
    
    def update_channel_progress(
        self, channel_id: str, 
        last_message_id: int = None,
        oldest_message_id: int = None,
        is_complete: bool = None
    ) -> None:
        """تحديث تقدم أرشفة القناة - للـ Resume"""
        updates = []
        params = []
        if last_message_id is not None:
            updates.append("last_message_id = ?")
            params.append(last_message_id)
        if oldest_message_id is not None:
            updates.append("oldest_message_id = ?")
            params.append(oldest_message_id)
        if is_complete is not None:
            updates.append("is_complete = ?")
            params.append(int(is_complete))
        
        if updates:
            params.append(channel_id)
            with self._conn() as conn:
                conn.execute(
                    f"UPDATE channels SET {', '.join(updates)} WHERE channel_id = ?",
                    params
                )
    
    # ─── عمليات الرسائل ───────────────────────────────
    
    def insert_message(self, msg_data: Dict) -> bool:
        """إدراج رسالة - يُرجع True إذا كانت جديدة"""
        with self._conn() as conn:
            cursor = conn.execute("""
                INSERT OR IGNORE INTO messages
                    (channel_id, message_id, date, text, message_link,
                     has_media, media_type, metadata)
                VALUES
                    (:channel_id, :message_id, :date, :text, :message_link,
                     :has_media, :media_type, :metadata)
            """, {**msg_data, "metadata": json.dumps(msg_data.get("metadata", {}), ensure_ascii=False)})
            return cursor.rowcount > 0
    
    def get_messages_for_month(
        self, channel_id: str, year: int, month: int
    ) -> List[Dict]:
        """استرجاع رسائل شهر معين مرتبة زمنياً"""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT m.*, mf.local_path, mf.file_type, mf.file_name, mf.is_downloaded
                FROM messages m
                LEFT JOIN media_files mf ON 
                    m.channel_id = mf.channel_id AND m.message_id = mf.message_id
                WHERE m.channel_id = ?
                  AND strftime('%Y', m.date) = ?
                  AND strftime('%m', m.date) = ?
                ORDER BY m.date ASC
            """, (channel_id, str(year), f"{month:02d}")).fetchall()
            return [dict(r) for r in rows]
    
    def get_channel_months(self, channel_id: str) -> List[Dict]:
        """الشهور التي تحتوي على رسائل في هذه القناة"""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT 
                    strftime('%Y', date) as year,
                    strftime('%m', date) as month,
                    COUNT(*) as message_count,
                    SUM(has_media) as media_count
                FROM messages
                WHERE channel_id = ?
                GROUP BY year, month
                ORDER BY year, month
            """, (channel_id,)).fetchall()
            return [dict(r) for r in rows]
    
    def get_message_count(self, channel_id: str) -> int:
        with self._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM messages WHERE channel_id = ?", (channel_id,)
            ).fetchone()[0]
    
    # ─── عمليات الملفات ───────────────────────────────
    
    def insert_media_file(self, file_data: Dict) -> bool:
        """إدراج ملف وسائط - يتجاهل إذا كان موجوداً لمنع التكرار"""
        with self._conn() as conn:
            cursor = conn.execute("""
                INSERT OR IGNORE INTO media_files
                    (channel_id, message_id, file_id, file_type, 
                     file_name, file_size, local_path)
                VALUES
                    (:channel_id, :message_id, :file_id, :file_type,
                     :file_name, :file_size, :local_path)
            """, file_data)
            return cursor.rowcount > 0
    
    def get_pending_downloads(self, channel_id: str = None, limit: int = 50) -> List[Dict]:
        """قائمة الملفات التي لم تُحمَّل بعد"""
        query = """
            SELECT * FROM media_files 
            WHERE is_downloaded = 0 AND download_attempts < 3
        """
        params = []
        if channel_id:
            query += " AND channel_id = ?"
            params.append(channel_id)
        query += f" LIMIT {limit}"
        
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(query, params).fetchall()]
    
    def mark_file_downloaded(self, file_id: str, local_path: str) -> None:
        with self._conn() as conn:
            conn.execute("""
                UPDATE media_files 
                SET is_downloaded = 1, local_path = ?
                WHERE file_id = ?
            """, (local_path, file_id))
    
    def mark_file_failed(self, file_id: str, error: str) -> None:
        with self._conn() as conn:
            conn.execute("""
                UPDATE media_files 
                SET download_attempts = download_attempts + 1, error_message = ?
                WHERE file_id = ?
            """, (error, file_id))
    
    def get_stats(self, channel_id: str) -> Dict:
        """إحصائيات قناة كاملة"""
        with self._conn() as conn:
            stats = conn.execute("""
                SELECT
                    COUNT(*) as total_messages,
                    SUM(CASE WHEN media_type = 'photo' THEN 1 ELSE 0 END) as photos,
                    SUM(CASE WHEN media_type = 'video' THEN 1 ELSE 0 END) as videos,
                    SUM(CASE WHEN media_type = 'audio' THEN 1 ELSE 0 END) as audio,
                    SUM(CASE WHEN media_type = 'voice' THEN 1 ELSE 0 END) as voice,
                    SUM(CASE WHEN media_type = 'document' THEN 1 ELSE 0 END) as documents,
                    MIN(date) as first_message,
                    MAX(date) as last_message
                FROM messages WHERE channel_id = ?
            """, (channel_id,)).fetchone()
            return dict(stats)
