"""
ملف التشغيل الرئيسي للمشروع - الـ Entry Point
يقوم بربط الإعدادات وقاعدة البيانات ومحرك التحميل ومولد الواجهات معاً
"""
import asyncio
import logging
import sys
from pathlib import Path

from src.config import load_config
from src.database import Database
from src.downloader import TelegramArchiver
from src.generator import WebGenerator

async def main():
    # 1. إعداد السجلات (Logs) لمتابعة سير العمل وتتبع الأخطاء
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger("main")
    
    logger.info("جاري بدء تشغيل سكربت أرشيف تليجرام الاحترافي...")
    
    try:
        # 2. تحميل ملف الإعدادات لوحة التحكم
        config = load_config()
        
        # توجيه ملفات السجلات للفولدر المخصص لها أيضاً
        file_handler = logging.FileHandler(config.output.logs_dir / "archiver.log", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logging.getLogger().addHandler(file_handler)
        
        # 3. تهيئة قاعدة البيانات SQLite
        db_path = config.output.data_dir / "archive.db"
        db = Database(db_path)
        
        # 4. بدء الاتصال بتليجرام وتحميل الرسائل والوسائط
        archiver = TelegramArchiver(config, db)
        await archiver.start()
        await archiver.archive_all()
        
        # 5. توليد واجهات العرض أوفلاين (HTML) بعد انتهاء التحميل
        generator = WebGenerator(db, config.output.archive_dir)
        generator.generate_all()
        
        print("\n🎉 مبارك! تمت العملية بالكامل بنجاح وأرشيفك جاهز الآن.")
        
    except Exception as e:
        logger.exception(f"حدث خطأ فادح أدى إلى توقف البرنامج: {e}")
        print(f"\n❌ توقف البرنامج بسبب خطأ: {e}", file=sys.stderr)

if __name__ == "__main__":
    # تشغيل الدالة الأساسية في بيئة Asyncio المناسبة للموبايل والكمبيوتر
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 تم إيقاف البرنامج بواسطة المستخدم.")
