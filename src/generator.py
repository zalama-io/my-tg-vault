"""
مُولد الواجهات - يقوم بتحويل البيانات من قاعدة البيانات إلى صفحات HTML/PWA
تفاعلية وتعمل بالكامل بدون إنترنت (Offline) بتصميم عصري وأنيق
"""
import os
import logging
from pathlib import Path
from datetime import datetime
from jinja2 import Template
from rich.console import Console

from .database import Database

logger = logging.getLogger(__name__)
console = Console()

# ─── قوالب التصميم المدمجة للسهولة والأمان ────────────────
BASE_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <style>
        :root {
            --bg-color: #0e1621;
            --text-color: #f5f5f5;
            --primary-color: #2481cc;
            --surface-color: #17212b;
            --message-bg: #182533;
            --time-color: #7f91a4;
        }
        body {
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 0;
        }
        header {
            background-color: var(--surface-color);
            padding: 15px 20px;
            position: sticky;
            top: 0;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
            z-index: 100;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        h1, h2, h3 { margin: 0; }
        .back-btn {
            color: var(--primary-color);
            text-decoration: none;
            font-weight: bold;
        }
        .container { max-width: 800px; margin: 20px auto; padding: 0 10px; }
        
        /* تصميم كروت القنوات في الصفحة الرئيسية */
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }
        .card {
            background-color: var(--surface-color);
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }
        .card:hover { transform: translateY(-3px); }
        .card a { color: var(--primary-color); text-decoration: none; font-size: 1.2rem; font-weight: bold; }
        .stats { margin-top: 15px; font-size: 0.9rem; color: var(--time-color); }
        
        /* تصميم جدول الشهور */
        .month-list { list-style: none; padding: 0; }
        .month-item {
            background-color: var(--surface-color);
            margin-bottom: 10px;
            border-radius: 8px;
        }
        .month-item a {
            display: flex;
            justify-content: space-between;
            padding: 15px 20px;
            color: var(--text-color);
            text-decoration: none;
        }
        .month-item a:hover { background-color: var(--message-bg); border-radius: 8px; }

        /* تصميم شات التليجرام */
        .chat-container { display: flex; flex-direction: column; gap: 10px; padding: 10px 0; }
        .message {
            background-color: var(--message-bg);
            border-radius: 12px;
            padding: 10px 15px;
            max-width: 85%;
            align-self: flex-start;
            position: relative;
            box-shadow: 0 1px 2px rgba(0,0,0,0.2);
            word-wrap: break-word;
        }
        .message-text { white-space: pre-wrap; margin-bottom: 5px; line-height: 1.5; }
        .message-media { margin-top: 8px; margin-bottom: 5px; border-radius: 6px; overflow: hidden; max-width: 100%; }
        .message-media img, .message-media video { max-width: 100%; max-height: 400px; display: block; border-radius: 6px; }
        .message-time {
            font-size: 0.75rem;
            color: var(--time-color);
            text-align: left;
            margin-top: 4px;
        }
        .doc-link {
            display: flex;
            align-items: center;
            gap: 10px;
            background: rgba(255,255,255,0.05);
            padding: 10px;
            border-radius: 6px;
            color: var(--primary-color);
            text-decoration: none;
        }
    </style>
</head>
<body>
    <header>
        {% if back_url %}
            <a href="{{ back_url }}" class="back-btn">← عودة</a>
        {% else %}
            <div></div>
        {% endif %}
        <h3>{{ header_title }}</h3>
        <div style="width: 50px;"></div>
    </header>
    <div class="container">
        {{ content }}
    </div>
</body>
</html>
"""

class WebGenerator:
    def __init__(self, db: Database, archive_dir: Path):
        self.db = db
        self.archive_dir = archive_dir
        self.template = Template(BASE_HTML_TEMPLATE)

    def generate_all(self):
        """توليد الموقع بالكامل (الرئيسية -> القنوات -> الشهور)"""
        console.print("[yellow]🎨 جاري توليد واجهات العرض الأوفلاين (HTML)...[/yellow]")
        channels = self.db.get_all_channels()
        
        if not channels:
            logger.warning("لا توجد قنوات في قاعدة البيانات لتوليد واجهات لها.")
            self._generate_index_page([])
            return

        # 1. توليد صفحات الشهور لكل قناة
        for channel in channels:
            channel_id = channel["channel_id"]
            months = self.db.get_channel_months(channel_id)
            
            # توليد صفحة كل شهر منفصلة
            for m in months:
                self._generate_month_page(channel, int(m["year"]), int(m["month"]))
                
            # توليد الصفحة الخاصة بالقناة (التي تعرض قائمة الشهور المتاحة)
            self._generate_channel_page(channel, months)
            
        # 2. توليد الصفحة الرئيسية (الفهرس)
        self._generate_index_page(channels)
        console.print("[green]✓ تم تحديث وتوليد صفحات الـ HTML بنجاح! يمكنك الآن فتح ملف index.html[/green]")

    def _generate_index_page(self, channels: list):
        """توليد الصفحة الرئيسية index.html"""
        content_html = "<h2 style='margin-bottom:20px;'>الأرشيف الخاص بك</h2><div class='grid'>"
        
        for ch in channels:
            stats = self.db.get_stats(ch["channel_id"])
            content_html += f"""
            <div class="card">
                <a href="{ch['channel_id']}/index.html">{ch['title'] or ch['username']}</a>
                <p style="margin: 5px 0; color: #a0a0a0; font-size:0.9rem;">@{ch['username'] or 'قناة خاصة'}</p>
                <div class="stats">
                    <div>💬 إجمالي الرسائل: {stats['total_messages'] or 0}</div>
                    <div>🖼️ صور: {stats['photos'] or 0} | 🎥 فيديوهات: {stats['videos'] or 0}</div>
                </div>
            </div>
            """
        content_html += "</div>"
        
        full_html = self.template.render(
            title="خزنتي - أرشيف التليجرام",
            header_title="خزنتي على جوجل",
            back_url=None,
            content=content_html
        )
        
        with open(self.archive_dir / "index.html", "w", encoding="utf-8") as f:
            f.write(full_html)

    def _generate_channel_page(self, channel: dict, months: list):
        """توليد صفحة قائمة الشهور لقناة معينة"""
        ch_dir = self.archive_dir / channel["channel_id"]
        ch_dir.mkdir(parents=True, exist_ok=True)
        
        months_names = {
            "01": "يناير", "02": "فبراير", "03": "مارس", "04": "أبريل",
            "05": "مايو", "06": "يونيو", "07": "يوليو", "08": "أغسطس",
            "09": "سبتمبر", "10": "أكتوبر", "11": "نوفمبر", "12": "ديسمبر"
        }
        
        content_html = f"""
        <div style="margin-bottom: 20px;">
            <h2>{channel['title']}</h2>
            <p style="color:#a0a0a0;">{channel['description'] or ''}</p>
        </div>
        <h3>الشهور المؤرشفة</h3>
        <ul class="month-list">
        """
        
        for m in months:
            m_name = months_names.get(m["month"], m["month"])
            content_html += f"""
            <li class="month-item">
                <a href="{m['year']}_{m['month']}.html">
                    <span>📅 {m_name} {m['year']}</span>
                    <span style="color: var(--time-color); font-size:0.9rem;">{m['message_count']} رسالة</span>
                </a>
            </li>
            """
        content_html += "</ul>"
        
        full_html = self.template.render(
            title=channel["title"],
            header_title="استعراض القناة",
            back_url="../index.html",
            content=content_html
        )
        
        with open(ch_dir / "index.html", "w", encoding="utf-8") as f:
            f.write(full_html)

    def _generate_month_page(self, channel: dict, year: int, month: int):
        """توليد صفحة الرسائل لشهر محدد في قناة معينة"""
        messages = self.db.get_messages_for_month(channel["channel_id"], year, month)
        
        content_html = "<div class='chat-container'>"
        
        for msg in messages:
            # تنسيق الوقت
            try:
                dt = datetime.fromisoformat(msg["date"])
                time_str = dt.strftime("%I:%M %p")
            except:
                time_str = ""
                
            media_html = ""
            if msg["has_media"] and msg["is_downloaded"] and msg["local_path"]:
                # تحويل المسار المطلق لمسار نسبي ليعمل الأوفلاين بشكل صحيح
                # المجلد الحالي هو archive/channel_id/ والملفات في archive/channel_id/photos/ إلخ
                rel_path = ""
                if msg["file_type"] == "photo":
                    rel_path = f"photos/{msg['file_name']}"
                    media_html = f'<div class="message-media"><img src="{rel_path}" loading="lazy" /></div>'
                elif msg["file_type"] == "video":
                    rel_path = f"videos/{msg['file_name']}"
                    media_html = f'<div class="message-media"><video src="{rel_path}" controls preload="metadata"></video></div>'
                else:
                    # ملفات وصوتيات عادية
                    f_type = msg["file_type"]
                    rel_path = f"{f_type}s/{msg['file_name']}"
                    media_html = f'<a class="doc-link" href="{rel_path}" target="_blank">📁 ملف: {msg["file_name"] or "تحميل"}</a>'
                    
            content_html += f"""
            <div class="message" id="msg_{msg['message_id']}">
                {% if msg['text'] %}
                    <div class="message-text">{msg['text']}</div>
                {% endif %}
                {media_html}
                <div class="message-time">{time_str}</div>
            </div>
            """
        content_html += "</div>"
        
        # استبدال الجينجا يدوياً للنصوص لعدم التضارب
        content_template = Template(content_html)
        rendered_content = content_template.render()
        
        full_html = self.template.render(
            title=f"{channel['title']} - {month}/{year}",
            header_title=f"{month} / {year}",
            back_url="index.html",
            content=rendered_content
        )
        
        with open(self.archive_dir / channel["channel_id"] / f"{year}_{month:02d}.html", "w", encoding="utf-8") as f:
            f.write(full_html)
