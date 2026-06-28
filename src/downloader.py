"""
محرك التحميل والأرشفة - يتصل بالتليجرام عبر Telethon
ويقوم بجلب الرسائل والوسائط بطريقة آمنة وذكية لعدم حظر الحساب
"""
import asyncio
import logging
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from telethon import TelegramClient, errors
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, PeerChannel
from tqdm.asyncio import tqdm
from rich.console import Console

from .config import AppConfig
from .database import Database

logger = logging.getLogger(__name__)
console = Console()

class TelegramArchiver:
    def __init__(self, config: AppConfig, db: Database):
        self.config = config
        self.db = db
        # تحديد مسار ملف الجلسة ليكون داخل مجلد data لحمايته
        session_path = str(config.output.data_dir / config.telegram.session_name)
        self.client = TelegramClient(
            session_path,
            config.telegram.api_id,
            config.telegram.api_hash
        )
        self.download_semaphore = asyncio.Semaphore(config.settings.max_concurrent_downloads)

    async def start(self):
        """بدء تشغيل عميل تليجرام والتحقق من تسجيل الدخول"""
        await self.client.start()
        me = await self.client.get_me()
        logger.info(f"تم تسجيل الدخول بنجاح كـ: {me.first_name} (@{me.username})")
        console.print(f"[green]✓ تم الاتصال بتليجرام بنجاح كـ: {me.first_name}[/green]")

    async def archive_all(self):
        """أرشفة كل القنوات المحددة في الإعدادات"""
        for channel_username in self.config.channels:
            try:
                await self.archive_channel(channel_username)
            except Exception as e:
                logger.exception(f"خطأ غير متوقع أثناء أرشفة القناة {channel_username}: {e}")
                console.print(f"[red]❌ خطأ في القناة {channel_username}: {e}[/red]")

    async def archive_channel(self, channel_username: str):
        """أرشفة قناة واحدة (الرسائل أولاً ثم الوسائط)"""
        console.print(f"\n[bold blue]⏳ بدء معالجة القناة: {channel_username}[/bold blue]")
        
        # 1. جلب معلومات القناة من تليجرام
        try:
            entity = await self.client.get_entity(channel_username)
            if not isinstance(entity, PeerChannel) and not getattr(entity, 'broadcast', False):
                # التحقق من أنها قناة وليست جروب أو مستخدم
                pass
        except Exception as e:
            logger.error(f"لم نتمكن من الوصول للقناة {channel_username}: {e}")
            console.print(f"[red]❌ لا يمكن العثور على القناة أو الوصول إليها: {channel_username}[/red]")
            return

        full_channel = await self.client.get_input_entity(entity)
        
        # جلب تفاصيل إضافية عن القناة
        channel_info = await self.client.get_full_chat(entity)
        
        channel_data = {
            "channel_id": str(entity.id),
            "username": entity.username,
            "title": entity.title,
            "description": channel_info.full_chat.about if hasattr(channel_info, 'full_chat') else "",
            "member_count": channel_info.full_chat.participants_count if hasattr(channel_info, 'full_chat') else 0,
            "archived_at": datetime.now().isoformat()
        }
        self.db.upsert_channel(channel_data)
        
        # 2. استرجاع التقدم الحالي (للـ Resume)
        db_channel = self.db.get_channel(str(entity.id))
        last_saved_id = db_channel["last_message_id"] if db_channel else 0
        
        console.print(f"[yellow]🔄 جلب الرسائل الجديدة (بدءاً من رسالة رقم {last_saved_id})...[/yellow]")
        
        # 3. سحب الرسائل
        messages_fetched = 0
        max_id = 0
        
        async for message in self.client.iter_messages(
            entity,
            min_id=last_saved_id,
            limit=None,
            reverse=True # من الأقدم للأحدث لضمان الترتيب
        ):
            # تجهيز بيانات الرسالة
            msg_data = {
                "channel_id": str(entity.id),
                "message_id": message.id,
                "date": message.date.isoformat(),
                "text": message.text or "",
                "message_link": f"https://t.me/{entity.username}/{message.id}" if entity.username else f"https://t.me/c/{entity.id}/{message.id}",
                "has_media": 0,
                "media_type": None,
                "metadata": {}
            }
            
            # التحقق من وجود ميديا
            if message.media:
                msg_data["has_media"] = 1
                if isinstance(message.media, MessageMediaPhoto):
                    msg_data["media_type"] = "photo"
                    file_id = f"photo_{entity.id}_{message.id}"
                    # تحديد مسار الحفظ التلقائي
                    local_path = str(self.config.output.archive_dir / str(entity.id) / "photos" / f"{message.id}.jpg")
                    
                    self.db.insert_media_file({
                        "channel_id": str(entity.id),
                        "message_id": message.id,
                        "file_id": file_id,
                        "file_type": "photo",
                        "file_name": f"{message.id}.jpg",
                        "file_size": 0, # سيتم تحديثه عند التحميل
                        "local_path": local_path
                    })
                    
                elif isinstance(message.media, MessageMediaDocument):
                    msg_data["media_type"] = "document"
                    # التحقق لو كان فيديو أو صوت
                    attr = message.media.document.attributes
                    is_video = any(hasattr(a, 'video') for a in attr)
                    is_audio = any(hasattr(a, 'voice') for a in attr)
                    
                    if is_video: msg_data["media_type"] = "video"
                    elif is_audio: msg_data["media_type"] = "voice"
                    
                    orig_name = next((a.file_name for a in attr if hasattr(a, 'file_name')), f"{message.id}")
                    ext = os.path.splitext(orig_name)[1] or ".bin"
                    
                    file_id = f"doc_{entity.id}_{message.media.document.id}"
                    local_path = str(self.config.output.archive_dir / str(entity.id) / f"{msg_data['media_type']}s" / f"{message.id}{ext}")
                    
                    self.db.insert_media_file({
                        "channel_id": str(entity.id),
                        "message_id": message.id,
                        "file_id": file_id,
                        "file_type": msg_data["media_type"],
                        "file_name": f"{message.id}{ext}",
                        "file_size": message.media.document.size,
                        "local_path": local_path
                    })
            
            # حفظ الرسالة في قاعدة البيانات
            is_new = self.db.insert_message(msg_data)
            if is_new:
                messages_fetched += 1
            if message.id > max_id:
                max_id = message.id
                
            # حماية ذكية لحسابك: إيقاف بسيط كل 100 رسالة
            if messages_fetched % self.config.settings.batch_size == 0 and is_new:
                await asyncio.sleep(self.config.settings.delay_between_batches)

        if max_id > 0:
            self.db.update_channel_progress(str(entity.id), last_message_id=max_id)
            
        console.print(f"[green]✓ تم حفظ {messages_fetched} رسالة جديدة في قاعدة البيانات.[/green]")
        
        # 4. تحميل ملفات الميديا المتأخرة أو الجديدة لو الخيار مفعل
        if self.config.settings.download_media:
            await self.download_channel_media(str(entity.id))

    async def download_channel_media(self, channel_id: str):
        """تحميل كل الميديا المعلقة الخاصة بقناة معينة بالتوازي"""
        pending = self.db.get_pending_downloads(channel_id, limit=5000)
        if not pending:
            console.print("[green]✓ جميع ملفات الوسائط محملة بالكامل.[/green]")
            return
            
        console.print(f"[yellow]📥 جاري تحميل وسائط القناة ({len(pending)} ملف معلق)...[/yellow]")
        
        # شريط تقدم جميل في الشاشة لتتبع التحميل
        async def worker(file_row, pbar):
            async with self.download_semaphore:
                try:
                    # جلب الرسالة الأصلية من تليجرام لتحميل الميديا منها
                    entity = await self.client.get_entity(int(file_row["channel_id"]))
                    msg = await self.client.get_messages(entity, ids=file_row["message_id"])
                    
                    if not msg or not msg.media:
                        self.db.mark_file_failed(file_row["file_id"], "الرسالة أو الميديا لم تعد موجودة في تليجرام")
                        pbar.update(1)
                        return
                        
                    # التأكد من وجود مجلد الحفظ
                    out_path = Path(file_row["local_path"])
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # بدء التحميل الفعلي
                    await self.client.download_media(msg.media, file=str(out_path))
                    
                    # تحديث الحالة في قاعدة البيانات بنجاح
                    self.db.mark_file_downloaded(file_row["file_id"], file_row["local_path"])
                except Exception as e:
                    logger.error(f"فشل تحميل الملف {file_row['file_id']}: {e}")
                    self.db.mark_file_failed(file_row["file_id"], str(e))
                finally:
                    pbar.update(1)

        # تشغيل العمال بالتوازي لمشاهدة شريط التقدم يتناقص
        with tqdm(total=len(pending), desc="تحميل الوسائط", unit="ملف") as pbar:
            tasks = [worker(row, pbar) for row in pending]
            await asyncio.gather(*tasks, return_exceptions=True)
