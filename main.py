import yaml
import sqlite3
import os
from pathlib import Path
from src.generator import WebGenerator

class ConfigObject:
    def __init__(self, dictionary):
        for key, value in dictionary.items():
            if isinstance(value, dict):
                setattr(self, key, ConfigObject(value))
            elif isinstance(value, str) and ('dir' in key or 'path' in key or 'name' in key):
                setattr(self, key, Path(value))
            else:
                setattr(self, key, value)
                
    def __getitem__(self, item):
        val = getattr(self, item)
        if isinstance(val, ConfigObject):
            return val.__dict__
        elif isinstance(val, Path):
            return str(val)
        return val

def load_config():
    with open('config.yaml', 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
        return ConfigObject(data)

def main():
    config = load_config()
    
    print("⏳ جاري قراءة قاعدة البيانات وتوليد صفحات الأرشيف المحلي HTML...")
    
    # تشغيل المولد مباشرة بناءً على البيانات المحفوظة سابقاً
    generator = WebGenerator(config)
    generator.generate_all()

if __name__ == "__main__":
    main()
