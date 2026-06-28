import os
import sqlite3

class WebGenerator:
    def __init__(self, config):
        self.config = config
        self.archive_dir = config['output']['archive_dir']
        self.data_dir = config['output']['data_dir']
        self.db_path = os.path.join(self.data_dir, 'archive.db')
        
    def generate_all(self):
        if not os.path.exists(self.db_path):
            print("❌ قاعدة البيانات غير موجودة")
            return
            
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM channels")
            channels = cursor.fetchall()
        except Exception:
            print("❌ فشل في قراءة جدول القنوات")
            return
            
        if not channels:
            print("⚠️ لا توجد قنوات مسجلة")
            return
            
        os.makedirs(self.archive_dir, exist_ok=True)
        
        for channel in channels:
            ch_id = channel[0] if isinstance(channel, tuple) else channel['channel_id']
            ch_user = channel[1] if isinstance(channel, tuple) else channel['username']
            ch_title = channel[2] if isinstance(channel, tuple) else channel['title']
            
            # جلب كل الرسائل الخاصة بهذه القناة مباشرة لتفادي تعقيدات التواريخ
            cursor.execute("SELECT * FROM messages WHERE channel_id = ?", (ch_id,))
            messages = cursor.fetchall()
            
            if not messages:
                continue
                
            content_html = ""
            for msg in messages:
                # قراءة النص بأمان تام مهما كان اسم العمود
                msg_text = ""
                for col in msg.keys():
                    if col in ['text', 'message', 'body', 'content'] and msg[col]:
                        msg_text = str(msg[col])
                        break
                
                # قراءة التاريخ بأمان
                msg_date = ""
                for col in msg.keys():
                    if col in ['date', 'timestamp', 'time'] and msg[col]:
                        msg_date = str(msg[col])
                        break

                if msg_text:
                    content_html += f"""
                    <div style="background:#f9f9f9; padding:12px; margin-bottom:12px; border-radius:8px; border-right:4px solid #0088cc; text-align:right; dir:rtl;">
                        <div style="font-size:16px; color:#333;">{msg_text}</div>
                        <div style="font-size:11px; color:#999; margin-top:5px;">{msg_date}</div>
                    </div>
                    """
            
            ch_dir = os.path.join(self.archive_dir, str(ch_user))
            os.makedirs(ch_dir, exist_ok=True)
            
            page_html = f"""
            <!DOCTYPE html>
            <html lang="ar" dir="rtl">
            <head><meta charset="UTF-8"><title>{ch_title}</title></head>
            <body style="font-family:Arial; background:#eef2f3; padding:20px;">
                <div style="max-width:800px; margin:0 auto; background:#fff; padding:20px; border-radius:12px;">
                    <h2>{ch_title} (@{ch_user})</h2>
                    <hr>
                    {content_html}
                </div>
            </body>
            </html>
            """
            with open(os.path.join(ch_dir, "index.html"), "w", encoding="utf-8") as f:
                f.write(page_html)
                
        # توليد الفهرس الرئيسي للوصول السهل
        index_links = ""
        for channel in channels:
            ch_user = channel[1] if isinstance(channel, tuple) else channel['username']
            ch_title = channel[2] if isinstance(channel, tuple) else channel['title']
            index_links += f'<h3><a href="{ch_user}/index.html">{ch_title} (@{ch_user})</a></h3>'
            
        index_html = f"""
        <!DOCTYPE html>
        <html lang="ar" dir="rtl">
        <head><meta charset="UTF-8"><title>خزنتي المحلية</title></head>
        <body style="font-family:Arial; padding:40px; background:#f4f7f6;">
            <h1>🗄️ الأرشيف المحلي لقنوات التليجرام الخاص بك</h1>
            <hr>
            {index_links}
        </body>
        </html>
        """
        with open(os.path.join(self.archive_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(index_html)
            
        conn.close()
        print("✓ مبروك! تم تحديث وتوليد صفحات الـ HTML بنجاح تـام وبدون أي أخطاء!")
