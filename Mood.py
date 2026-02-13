import telebot
import requests
import sqlite3
import random
import time
import os
import json
from datetime import datetime, timedelta
from telebot import types
import logging
import re
import base64
import urllib.parse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib3
from urllib3.exceptions import InsecureRequestWarning

# ==================== تنظیمات ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

print("=" * 60)
print("🤖 ربات دانلودر تیک تاک - نسخه حرفه‌ای v15.0")
print("✅ دانلود عکس + ویدیو + موزیک + سیستم عضویت اجباری")
print("=" * 60)

# 🔐 اطلاعات ربات
BOT_TOKEN = "8589470820:AAEfL_pfSXBgoC3hLn2Kz2AP1m-A8v3lM-E"
ADMIN_ID = 6906387548
SUPPORT_USERNAME = "@meAhmad_1386"

# 🔥 API های مختلف
API_USERNAME = "6906387548"
API_PASSWORD = "gJXuxMY9VDeWncL"
API_AUTH = base64.b64encode(f"{API_USERNAME}:{API_PASSWORD}".encode()).decode()

CHANNEL_USERNAME = "@ARIANA_MOOD"

# 📊 دیتابیس
DB_NAME = "tiktok_pro.db"

# غیرفعال کردن هشدارهای SSL
urllib3.disable_warnings(InsecureRequestWarning)

# ==================== سیستم دیتابیس حرفه‌ای ====================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()
        logger.info("✅ پایگاه داده بارگذاری شد")
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        # کاربران
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                daily_downloads INTEGER DEFAULT 0,
                last_download_date DATE,
                total_downloads INTEGER DEFAULT 0,
                invite_code TEXT UNIQUE,
                invite_count INTEGER DEFAULT 0,
                extra_downloads INTEGER DEFAULT 0,
                is_vip INTEGER DEFAULT 0,
                vip_expiry DATE
            )
        ''')
        
        # کانال‌ها و گروه‌های اجباری
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS required_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_username TEXT UNIQUE,
                chat_link TEXT,
                chat_type TEXT DEFAULT 'channel',
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # دانلودها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                url TEXT,
                download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_type TEXT,
                success INTEGER DEFAULT 1,
                api_used TEXT,
                response_time REAL,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        self.conn.commit()
        
        # اضافه کردن ادمین به عنوان VIP
        cursor.execute("INSERT OR IGNORE INTO users (user_id, is_vip, username, first_name) VALUES (?, 1, ?, ?)", 
                      (ADMIN_ID, "Admin", "مدیر کل"))
        
        # اضافه کردن کانال اصلی
        cursor.execute("INSERT OR IGNORE INTO required_channels (chat_username, chat_link, chat_type) VALUES (?, ?, ?)", 
                      (CHANNEL_USERNAME, f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}", "channel"))
        
        self.conn.commit()
    
    def add_user(self, user_id, username, first_name, last_name):
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            
            if cursor.fetchone():
                cursor.execute('''
                    UPDATE users 
                    SET username = ?, first_name = ?, last_name = ?
                    WHERE user_id = ?
                ''', (username or "", first_name or "", last_name or "", user_id))
            else:
                invite_code = f"INV{user_id}{random.randint(1000, 9999)}"
                cursor.execute('''
                    INSERT INTO users 
                    (user_id, username, first_name, last_name, invite_code)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, username or "", first_name or "", last_name or "", invite_code))
            
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطا در افزودن کاربر: {e}")
            return False
    
    def get_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    def can_download(self, user_id):
        try:
            user = self.get_user(user_id)
            if not user:
                return True
            
            if user['is_vip']:
                return True
            
            today = datetime.now().date()
            last_date = user['last_download_date']
            
            if last_date:
                if isinstance(last_date, str):
                    try:
                        last_date = datetime.strptime(last_date, '%Y-%m-%d').date()
                    except:
                        last_date = today
            
                if last_date != today:
                    cursor = self.conn.cursor()
                    cursor.execute('''
                        UPDATE users 
                        SET daily_downloads = 0, last_download_date = ?
                        WHERE user_id = ?
                    ''', (today.strftime('%Y-%m-%d'), user_id))
                    self.conn.commit()
                    return True
            
            daily_limit = 5 + (user['extra_downloads'] or 0)
            daily_downloads = user['daily_downloads'] or 0
            
            if daily_downloads < daily_limit:
                return True
            
            return False
        except Exception as e:
            logger.error(f"خطا در بررسی امکان دانلود: {e}")
            return True
    
    def increment_download(self, user_id, url=None, file_type=None, success=True, api_used=None, response_time=0):
        try:
            cursor = self.conn.cursor()
            today = datetime.now().date()
            
            cursor.execute('''
                UPDATE users 
                SET daily_downloads = daily_downloads + 1,
                    total_downloads = total_downloads + 1,
                    last_download_date = ?
                WHERE user_id = ?
            ''', (today.strftime('%Y-%m-%d'), user_id))
            
            if url:
                cursor.execute('''
                    INSERT INTO downloads (user_id, url, file_type, success, api_used, response_time)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, url[:200], file_type, 1 if success else 0, api_used, response_time))
            
            self.conn.commit()
            
            # بررسی برای نمایش لینک دعوت
            user = self.get_user(user_id)
            daily_limit = 5 + (user['extra_downloads'] or 0)
            
            if user and user['daily_downloads'] >= daily_limit and user['invite_count'] == 0:
                return True
            
            return False
        except Exception as e:
            logger.error(f"خطا در ثبت دانلود: {e}")
            return False
    
    def get_invite_link(self, user_id):
        user = self.get_user(user_id)
        if user and user['invite_code']:
            return f"https://t.me/danloode_Mood_bot?start={user['invite_code']}"
        return f"https://t.me/danloode_Mood_bot?start=ref{user_id}"
    
    def get_stats(self):
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(total_downloads) FROM users")
        total_downloads = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_vip = 1")
        vip_users = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM downloads WHERE date(download_date) = date('now')")
        today_downloads = cursor.fetchone()[0] or 0
        
        return {
            'total_users': total_users,
            'total_downloads': total_downloads,
            'vip_users': vip_users,
            'today_downloads': today_downloads
        }
    
    def set_vip(self, user_id, is_vip=True, days=30):
        try:
            cursor = self.conn.cursor()
            expiry_date = (datetime.now() + timedelta(days=days)).date() if is_vip else None
            
            cursor.execute('''
                UPDATE users 
                SET is_vip = ?, vip_expiry = ?
                WHERE user_id = ?
            ''', (1 if is_vip else 0, expiry_date.strftime('%Y-%m-%d') if expiry_date else None, user_id))
            
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"خطا در تنظیم VIP: {e}")
            return False
    
    def add_channel(self, chat_username, chat_link, chat_type='channel'):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO required_channels (chat_username, chat_link, chat_type)
                VALUES (?, ?, ?)
            ''', (chat_username, chat_link, chat_type))
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"خطا در افزودن کانال/گروه: {e}")
            return False
    
    def remove_channel(self, chat_username):
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM required_channels WHERE chat_username = ?", (chat_username,))
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"خطا در حذف کانال/گروه: {e}")
            return False
    
    def get_required_channels(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM required_channels ORDER BY added_date DESC")
        return cursor.fetchall()
    
    def reset_user(self, username):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET daily_downloads = 0,
                    total_downloads = 0,
                    invite_count = 0,
                    extra_downloads = 0
                WHERE username = ?
            ''', (username,))
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"خطا در ریست کاربر: {e}")
            return False
    
    def get_user_by_username(self, username):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

# ایجاد دیتابیس
db = Database()
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True)

# ==================== سیستم عضویت اجباری هوشمند ====================
def check_membership(user_id):
    """بررسی هوشمند عضویت کاربر در کانال/گروه‌ها - فقط کانال‌هایی که عضو نیست را برمی‌گرداند"""
    try:
        channels = db.get_required_channels()
        missing_channels = []
        
        if not channels:
            return []
        
        for channel in channels:
            try:
                chat_member = bot.get_chat_member(channel['chat_username'], user_id)
                if chat_member.status in ['member', 'administrator', 'creator']:
                    continue
                else:
                    missing_channels.append(dict(channel))
            except Exception as e:
                logger.error(f"خطا در بررسی عضویت {channel['chat_username']}: {e}")
                missing_channels.append(dict(channel))
        
        return missing_channels
    except Exception as e:
        logger.error(f"خطا در بررسی عضویت: {e}")
        return []

def require_membership(func):
    """دکوراتور هوشمند برای بررسی عضویت"""
    def wrapper(message, *args, **kwargs):
        user_id = message.from_user.id
        
        missing_channels = check_membership(user_id)
        
        if missing_channels:
            keyboard = types.InlineKeyboardMarkup()
            for channel in missing_channels:
                keyboard.add(types.InlineKeyboardButton(
                    text=f"عضویت در {channel['chat_username']}",
                    url=channel['chat_link']
                ))
            keyboard.add(types.InlineKeyboardButton(
                text="✅ بررسی عضویت",
                callback_data=f"check_membership_{user_id}"
            ))
            
            bot.reply_to(
                message,
                f"┌─────────────────────┐\n"
                f"│  🔔 <b>عضویت اجباری</b>  │\n"
                f"└─────────────────────┘\n\n"
                f"📢 برای استفاده از ربات، باید در کانال/گروه‌های زیر عضو شوید:\n\n"
                f"👥 پس از عضویت، روی دکمه «بررسی عضویت» کلیک کنید.",
                reply_markup=keyboard,
                parse_mode='HTML'
            )
            return
        
        return func(message, *args, **kwargs)
    return wrapper

@bot.callback_query_handler(func=lambda call: call.data.startswith('check_membership_'))
def check_membership_callback(call):
    """بررسی مجدد عضویت - فقط کانال‌هایی که هنوز عضو نیست نمایش داده می‌شوند"""
    user_id = int(call.data.split('_')[2])
    
    if call.from_user.id != user_id:
        bot.answer_callback_query(call.id, "این دکمه برای شما نیست!")
        return
    
    missing_channels = check_membership(user_id)
    
    if not missing_channels:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(
            user_id,
            "✅ <b>عضویت شما تایید شد!</b>\n\nاکنون می‌توانید از ربات استفاده کنید.",
            reply_markup=create_main_menu(),
            parse_mode='HTML'
        )
    else:
        keyboard = types.InlineKeyboardMarkup()
        for channel in missing_channels:
            keyboard.add(types.InlineKeyboardButton(
                text=f"عضویت در {channel['chat_username']}",
                url=channel['chat_link']
            ))
        keyboard.add(types.InlineKeyboardButton(
            text="✅ بررسی عضویت",
            callback_data=f"check_membership_{user_id}"
        ))
        
        bot.edit_message_text(
            f"┌─────────────────────┐\n"
            f"│  🔔 <b>عضویت اجباری</b>  │\n"
            f"└─────────────────────┘\n\n"
            f"📢 برای استفاده از ربات، باید در کانال/گروه‌های زیر عضو شوید:\n\n"
            f"👥 پس از عضویت، روی دکمه «بررسی عضویت» کلیک کنید.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id, "❌ شما هنوز در همه کانال/گروه‌ها عضو نشده‌اید!")

# ==================== سیستم دانلود پیشرفته ====================
class AdvancedTikTokDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False
        self.timeout = 20
        
        self.apis = [
            self.api_fastcreat,
            self.api_tikmate,
            self.api_tikwm,
            self.api_tikdown,
            self.api_ssstik
        ]
    
    def extract_tiktok_url(self, text):
        """استخراج لینک تیک‌تاک از متن با الگوهای مختلف"""
        patterns = [
            r'(https?://(?:vt|vm)\.tiktok\.com/[^\s]+)',
            r'(https?://(?:www\.)?tiktok\.com/@[^\s/]+/video/\d+)',
            r'(https?://(?:www\.)?tiktok\.com/t/[^\s/]+/\d+)',
            r'(https?://(?:www\.)?tiktok\.com/\@[^\s/]+)',
            r'(https?://m\.tiktok\.com/v/[^\s]+)',
            r'(https?://t\.tk/[^\s]+)',
            r'(https?://vm\.tiktok\.com/[A-Za-z0-9]+)',
            r'(https?://vt\.tiktok\.com/[A-Za-z0-9]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                url = match.group(0)
                if not url.startswith('http'):
                    url = 'https://' + url
                return url
        
        return None
    
    def download_content(self, url):
        """دانلود محتوای تیک‌تاک با چندین API همزمان"""
        start_time = time.time()
        
        # اجرای همزمان تمام API ها
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(api_func, url): api_func.__name__ for api_func in self.apis}
            
            for future in as_completed(futures):
                result = future.result()
                if result and result.get('success'):
                    result['response_time'] = time.time() - start_time
                    return result
        
        return {
            'success': False,
            'error': 'تمام سرویس‌های دانلود در دسترس نیستند. لطفاً دوباره تلاش کنید.',
            'response_time': time.time() - start_time
        }
    
    def api_fastcreat(self, url):
        """API اختصاصی Fast-Creat"""
        try:
            headers = {
                'Authorization': f'Basic {API_AUTH}',
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0'
            }
            
            response = self.session.post(
                "https://api.fast-creat.ir/tiktok",
                json={'url': url},
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                return self.parse_fastcreat_response(data)
        except Exception as e:
            logger.debug(f"Fast-Creat API error: {e}")
        return None
    
    def api_tikmate(self, url):
        """API TikMate"""
        try:
            response = self.session.post(
                "https://api.tikmate.app/api/lookup",
                data={'url': url},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return {
                        'success': True,
                        'video_url': data.get('video_url'),
                        'music_url': data.get('music_url'),
                        'author': data.get('author', 'تیک‌تاک'),
                        'title': data.get('description', 'بدون عنوان'),
                        'api_name': 'TikMate'
                    }
        except:
            pass
        return None
    
    def api_tikwm(self, url):
        """API TikWM"""
        try:
            response = self.session.post(
                "https://www.tikwm.com/api/",
                json={'url': url},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    video_data = data.get('data', {})
                    return {
                        'success': True,
                        'video_url': video_data.get('play'),
                        'music_url': video_data.get('music'),
                        'images': video_data.get('images', []),
                        'author': video_data.get('author', {}).get('nickname', 'تیک‌تاک'),
                        'title': video_data.get('title', 'بدون عنوان'),
                        'api_name': 'TikWM'
                    }
        except:
            pass
        return None
    
    def api_tikdown(self, url):
        """API TikDown"""
        try:
            response = self.session.post(
                "https://www.tikdown.org/api/ajaxSearch",
                data={'q': url, 'lang': 'en'},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    html = data.get('data', '')
                    
                    # استخراج لینک‌ها از HTML
                    video_match = re.search(r'href="([^"]+\.mp4[^"]*)"', html)
                    audio_match = re.search(r'href="([^"]+\.mp3[^"]*)"', html)
                    
                    video_url = video_match.group(1) if video_match else None
                    music_url = audio_match.group(1) if audio_match else None
                    
                    if video_url or music_url:
                        return {
                            'success': True,
                            'video_url': video_url,
                            'music_url': music_url,
                            'author': 'تیک‌تاک',
                            'title': 'محتوای تیک‌تاک',
                            'api_name': 'TikDown'
                        }
        except:
            pass
        return None
    
    def api_ssstik(self, url):
        """API SSSTik"""
        try:
            response = self.session.post(
                "https://ssstik.io/abc",
                data={'id': url},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                html = response.text
                
                # استخراج اطلاعات
                title_match = re.search(r'<p[^>]*>([^<]+)</p>', html)
                author_match = re.search(r'<h2[^>]*>([^<]+)</h2>', html)
                
                # استخراج لینک ویدیو و موزیک
                video_pattern = r'<a[^>]*href="([^"]+\.mp4)"[^>]*download[^>]*>'
                audio_pattern = r'<a[^>]*href="([^"]+\.mp3)"[^>]*>'
                
                video_match = re.search(video_pattern, html)
                audio_match = re.search(audio_pattern, html)
                
                video_url = video_match.group(1) if video_match else None
                music_url = audio_match.group(1) if audio_match else None
                
                if video_url or music_url:
                    return {
                        'success': True,
                        'video_url': video_url,
                        'music_url': music_url,
                        'author': author_match.group(1) if author_match else 'تیک‌تاک',
                        'title': title_match.group(1) if title_match else 'بدون عنوان',
                        'api_name': 'SSSTik'
                    }
        except:
            pass
        return None
    
    def parse_fastcreat_response(self, data):
        """پردازش پاسخ Fast-Creat"""
        if not isinstance(data, dict):
            return None
        
        # استخراج ویدیو
        video_url = None
        if data.get('video_url'):
            video_url = data['video_url']
        elif data.get('video'):
            video_url = data['video'] if isinstance(data['video'], str) else data['video'].get('url')
        
        # استخراج عکس‌ها
        images = []
        if data.get('images'):
            if isinstance(data['images'], list):
                images = data['images']
            elif isinstance(data['images'], str):
                images = [data['images']]
        
        # استخراج موزیک
        music_url = None
        if data.get('music_url'):
            music_url = data['music_url']
        elif data.get('music'):
            music_url = data['music'] if isinstance(data['music'], str) else data['music'].get('url')
        
        if video_url or images or music_url:
            return {
                'success': True,
                'video_url': video_url,
                'images': images,
                'music_url': music_url,
                'author': data.get('author', 'تیک‌تاک'),
                'title': data.get('title', 'بدون عنوان'),
                'api_name': 'Fast-Creat'
            }
        
        return None

# ایجاد دانلودر
downloader = AdvancedTikTokDownloader()

# ==================== منوهای شیشه‌ای ====================
def create_main_menu():
    """منوی اصلی - فقط یک دکمه دانلود ساده"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    buttons = [
        "📥 دانلود تیک تاک",
        "👥 دعوت دوستان",
        "📊 آمار من",
        "🆘 پشتیبانی",
        "ℹ️ راهنما"
    ]
    
    keyboard.row(buttons[0])
    keyboard.row(buttons[1], buttons[2])
    keyboard.row(buttons[3], buttons[4])
    
    return keyboard

def create_admin_menu():
    """منوی مدیریت"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    buttons = [
        "📈 آمار کلی سیستم",
        "👥 مدیریت کاربران",
        "📢 ارسال همگانی",
        "📣 مدیریت کانال‌ها",
        "⭐ مدیریت VIP",
        "🔄 ریست کاربر",
        "🔙 منوی اصلی"
    ]
    
    keyboard.row(buttons[0], buttons[1])
    keyboard.row(buttons[2], buttons[3])
    keyboard.row(buttons[4], buttons[5])
    keyboard.row(buttons[6])
    
    return keyboard

def create_admin_users_menu():
    """منوی مدیریت کاربران"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    buttons = [
        "📋 لیست کاربران",
        "👤 اطلاعات کاربر",
        "🔙 بازگشت"
    ]
    
    keyboard.row(buttons[0], buttons[1])
    keyboard.row(buttons[2])
    
    return keyboard

def create_admin_channels_menu():
    """منوی مدیریت کانال‌ها"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    buttons = [
        "📋 لیست کانال‌ها",
        "➕ افزودن کانال",
        "➖ حذف کانال",
        "🔙 بازگشت"
    ]
    
    keyboard.row(buttons[0], buttons[1])
    keyboard.row(buttons[2], buttons[3])
    
    return keyboard

def create_admin_vip_menu():
    """منوی مدیریت VIP"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    buttons = [
        "📋 لیست VIP‌ها",
        "➕ افزودن VIP",
        "➖ حذف VIP",
        "📅 تنظیم مدت VIP",
        "🔙 بازگشت"
    ]
    
    keyboard.row(buttons[0], buttons[1])
    keyboard.row(buttons[2], buttons[3])
    keyboard.row(buttons[4])
    
    return keyboard

# ==================== سیستم مدیریت وضعیت کاربران ====================
user_states = {}

def set_user_state(user_id, state, data=None):
    """تنظیم وضعیت کاربر"""
    user_states[user_id] = {'state': state, 'data': data}

def get_user_state(user_id):
    """دریافت وضعیت کاربر"""
    return user_states.get(user_id)

def clear_user_state(user_id):
    """پاک کردن وضعیت کاربر"""
    if user_id in user_states:
        del user_states[user_id]

# ==================== ذخیره موقت URL برای Callback ====================
temp_urls = {}
temp_url_counter = 0

def store_temp_url(url):
    """ذخیره موقت URL و برگرداندن ID یکتا"""
    global temp_url_counter
    temp_url_counter += 1
    url_id = str(temp_url_counter)
    temp_urls[url_id] = url
    return url_id

# ==================== توابع دانلود با نوع مشخص ====================
def download_specific_type(url, download_type, user_id, message, processing_msg_id=None):
    """دانلود فقط نوع مشخص شده از لینک تیک‌تاک"""
    # بررسی امکان دانلود
    if not db.can_download(user_id):
        user = db.get_user(user_id)
        if user and user['invite_count'] == 0:
            invite_link = db.get_invite_link(user_id)
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton(
                "📱 اشتراک‌گذاری لینک دعوت",
                url=f"https://t.me/share/url?url={urllib.parse.quote(invite_link)}&text=🎬 ربات دانلودر تیک‌تاک!"
            ))
            bot.send_message(
                message.chat.id,
                f"┌─────────────────────┐\n"
                f"│  😔 <b>محدودیت دانلود</b>  │\n"
                f"└─────────────────────┘\n\n"
                f"📊 <b>دانلودهای امروز شما به پایان رسید!</b>\n\n"
                f"🎁 <b>با دعوت دوستان ۲۰ دانلود اضافی بگیر!</b>\n\n"
                f"🔗 <b>لینک دعوت شما:</b>\n"
                f"<code>{invite_link}</code>\n\n"
                f"✨ هر دعوت = ۲۰ دانلود اضافی!",
                reply_markup=keyboard,
                parse_mode='HTML'
            )
        else:
            bot.send_message(
                message.chat.id,
                f"┌─────────────────────┐\n"
                f"│  ⏰ <b>محدودیت زمانی</b>  │\n"
                f"└─────────────────────┘\n\n"
                f"📊 <b>دانلودهای امروز شما به پایان رسید!</b>\n\n"
                f"🕒 لطفاً فردا مجدداً تلاش کنید.\n"
                f"⏰ ساعت ۰۰:۰۰ محدودیت بازنشانی می‌شود.",
                parse_mode='HTML'
            )
        return

    # اگر processing_msg_id وجود نداشت، یک پیام جدید ایجاد کن
    if processing_msg_id is None:
        processing_msg = bot.reply_to(
            message,
            f"┌─────────────────────┐\n"
            f"│  ⚡ <b>در حال پردازش</b>  │\n"
            f"└─────────────────────┘\n\n"
            f"🔗 <b>لینک:</b>\n<code>{url[:50]}...</code>\n\n"
            f"⏳ <b>در حال اتصال به سرور...</b>\n"
            f"📡 بررسی API‌های مختلف\n"
            f"⚡ لطفاً صبر کنید...",
            parse_mode='HTML'
        )
        processing_msg_id = processing_msg.message_id
    else:
        # ویرایش پیام موجود (مثلاً از Callback)
        try:
            bot.edit_message_text(
                f"┌─────────────────────┐\n"
                f"│  ⚡ <b>در حال پردازش</b>  │\n"
                f"└─────────────────────┘\n\n"
                f"🔗 <b>لینک:</b>\n<code>{url[:50]}...</code>\n\n"
                f"⏳ <b>در حال اتصال به سرور...</b>\n"
                f"📡 بررسی API‌های مختلف\n"
                f"⚡ لطفاً صبر کنید...",
                chat_id=message.chat.id,
                message_id=processing_msg_id,
                parse_mode='HTML'
            )
        except:
            # اگر ویرایش نشد، پیام جدید بفرست
            processing_msg = bot.send_message(
                message.chat.id,
                f"┌─────────────────────┐\n"
                f"│  ⚡ <b>در حال پردازش</b>  │\n"
                f"└─────────────────────┘\n\n"
                f"🔗 <b>لینک:</b>\n<code>{url[:50]}...</code>\n\n"
                f"⏳ <b>در حال اتصال به سرور...</b>\n"
                f"📡 بررسی API‌های مختلف\n"
                f"⚡ لطفاً صبر کنید...",
                parse_mode='HTML'
            )
            processing_msg_id = processing_msg.message_id

    # دانلود محتوا
    result = downloader.download_content(url)

    if not result['success']:
        try:
            bot.edit_message_text(
                f"┌─────────────────────┐\n"
                f"│  ❌ <b>خطا در دانلود</b>  │\n"
                f"└─────────────────────┘\n\n"
                f"🔗 <b>لینک:</b> {url[:50]}...\n\n"
                f"📛 <b>خطا:</b> {result.get('error', 'خطای ناشناخته')}\n\n"
                f"⏱️ <b>زمان پردازش:</b> {result['response_time']:.1f} ثانیه\n\n"
                f"🔗 {CHANNEL_USERNAME}",
                chat_id=message.chat.id,
                message_id=processing_msg_id,
                parse_mode='HTML'
            )
        except:
            bot.send_message(
                message.chat.id,
                f"┌─────────────────────┐\n"
                f"│  ❌ <b>خطا در دانلود</b>  │\n"
                f"└─────────────────────┘\n\n"
                f"🔗 <b>لینک:</b> {url[:50]}...\n\n"
                f"📛 <b>خطا:</b> {result.get('error', 'خطای ناشناخته')}\n\n"
                f"⏱️ <b>زمان پردازش:</b> {result['response_time']:.1f} ثانیه\n\n"
                f"🔗 {CHANNEL_USERNAME}",
                parse_mode='HTML'
            )
        return

    # حذف پیام پردازش
    try:
        bot.delete_message(message.chat.id, processing_msg_id)
    except:
        pass

    files_sent = 0
    file_type = None

    # پردازش بر اساس نوع درخواستی
    if download_type == 'video':
        if result.get('video_url'):
            file_type = 'video'
            try:
                caption = f"""
┌─────────────────────┐
│  ✅ <b>ویدیو دانلود شد</b>  │
└─────────────────────┘

👤 <b>سازنده:</b> {result.get('author', 'تیک‌تاک')}
📝 <b>عنوان:</b> {result.get('title', 'بدون عنوان')}
⚡ <b>API:</b> {result.get('api_name', 'Fast-Creat')}
⏱️ <b>زمان پردازش:</b> {result['response_time']:.1f} ثانیه

✨ <b>ممنون از استفاده از ربات!</b>
🔗 {CHANNEL_USERNAME}
                """
                bot.send_video(
                    chat_id=message.chat.id,
                    video=result['video_url'],
                    caption=caption,
                    parse_mode='HTML',
                    supports_streaming=True,
                    timeout=60
                )
                files_sent += 1
            except Exception as e:
                logger.error(f"خطا در ارسال ویدیو: {e}")
                try:
                    bot.send_message(
                        message.chat.id,
                        f"✅ <b>ویدیو دانلود شد!</b>\n\n"
                        f"🔗 <b>لینک مستقیم ویدیو:</b>\n"
                        f"<code>{result['video_url'][:200]}...</code>",
                        parse_mode='HTML'
                    )
                    files_sent += 1
                except:
                    pass
        else:
            bot.send_message(
                message.chat.id,
                "❌ <b>ویدیویی برای این لینک یافت نشد!</b>\n\n"
                "لطفاً لینک دیگری امتحان کنید.",
                parse_mode='HTML'
            )

    elif download_type == 'image':
        if result.get('images') and len(result['images']) > 0:
            file_type = 'image'
            try:
                images = result['images'][:10]
                if len(images) == 1:
                    caption = f"""
┌─────────────────────┐
│  🖼️ <b>عکس دانلود شد</b>  │
└─────────────────────┘

👤 <b>سازنده:</b> {result.get('author', 'تیک‌تاک')}
⚡ <b>API:</b> {result.get('api_name', 'Fast-Creat')}
⏱️ <b>زمان پردازش:</b> {result['response_time']:.1f} ثانیه

✨ <b>ممنون از استفاده از ربات!</b>
🔗 {CHANNEL_USERNAME}
                    """
                    bot.send_photo(
                        chat_id=message.chat.id,
                        photo=images[0],
                        caption=caption,
                        parse_mode='HTML',
                        timeout=60
                    )
                    files_sent += 1
                else:
                    media_group = []
                    for i, img_url in enumerate(images):
                        if i == 0:
                            media_group.append(types.InputMediaPhoto(
                                img_url,
                                caption=f"🖼️ <b>{len(images)} عکس دانلود شد!</b>\n\n"
                                        f"👤 سازنده: {result.get('author', 'تیک‌تاک')}\n"
                                        f"⏱️ زمان پردازش: {result['response_time']:.1f} ثانیه\n"
                                        f"✨ ممنون از استفاده از ربات!\n"
                                        f"🔗 {CHANNEL_USERNAME}",
                                parse_mode='HTML'
                            ))
                        else:
                            media_group.append(types.InputMediaPhoto(img_url))
                    bot.send_media_group(
                        chat_id=message.chat.id,
                        media=media_group
                    )
                    files_sent += len(images)
            except Exception as e:
                logger.error(f"خطا در ارسال عکس: {e}")
                try:
                    bot.send_message(
                        message.chat.id,
                        f"🖼️ <b>{len(result['images'])} عکس دانلود شد!</b>",
                        parse_mode='HTML'
                    )
                    files_sent += 1
                except:
                    pass
        else:
            bot.send_message(
                message.chat.id,
                "❌ <b>عکسی برای این لینک یافت نشد!</b>\n\n"
                "این پست احتمالاً ویدیو است یا عکس ندارد.",
                parse_mode='HTML'
            )

    elif download_type == 'music':
        if result.get('music_url'):
            file_type = 'music'
            try:
                caption = f"""
┌─────────────────────┐
│  🎵 <b>موزیک دانلود شد</b>  │
└─────────────────────┘

👤 <b>سازنده:</b> {result.get('author', 'تیک‌تاک')}
🎵 <b>عنوان:</b> {result.get('title', 'بدون عنوان')}
⚡ <b>API:</b> {result.get('api_name', 'Fast-Creat')}
⏱️ <b>زمان پردازش:</b> {result['response_time']:.1f} ثانیه

✨ <b>ممنون از استفاده از ربات!</b>
🔗 {CHANNEL_USERNAME}
                """
                bot.send_audio(
                    chat_id=message.chat.id,
                    audio=result['music_url'],
                    caption=caption,
                    parse_mode='HTML',
                    title=result.get('title', 'موزیک تیک‌تاک')[:64],
                    performer=result.get('author', 'تیک‌تاک')[:64],
                    timeout=60
                )
                files_sent += 1
            except Exception as e:
                logger.error(f"خطا در ارسال موزیک: {e}")
                try:
                    bot.send_message(
                        message.chat.id,
                        f"🎵 <b>موزیک دانلود شد!</b>\n\n"
                        f"🔗 <b>لینک مستقیم موزیک:</b>\n"
                        f"<code>{result['music_url'][:200]}...</code>",
                        parse_mode='HTML'
                    )
                    files_sent += 1
                except:
                    pass
        else:
            bot.send_message(
                message.chat.id,
                "❌ <b>موزیکی برای این لینک یافت نشد!</b>\n\n"
                "لطفاً لینک دیگری امتحان کنید.",
                parse_mode='HTML'
            )

    # ثبت دانلود در صورت موفقیت
    if files_sent > 0 and file_type:
        show_invite_link = db.increment_download(
            user_id,
            url,
            file_type,
            True,
            result.get('api_name'),
            result['response_time']
        )
        
        # نمایش لینک دعوت بعد از اتمام دانلودهای روزانه
        if show_invite_link:
            user = db.get_user(user_id)
            if user and user['invite_count'] == 0:
                invite_link = db.get_invite_link(user_id)
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton(
                    "📱 اشتراک‌گذاری لینک دعوت",
                    url=f"https://t.me/share/url?url={urllib.parse.quote(invite_link)}&text=🎬 ربات دانلودر تیک‌تاک!"
                ))
                bot.send_message(
                    message.chat.id,
                    f"┌─────────────────────┐\n"
                    f"│  🎉 <b>دانلودهای امروز</b>  │\n"
                    f"└─────────────────────┘\n\n"
                    f"📊 <b>دانلودهای رایگان امروز شما به پایان رسید!</b>\n\n"
                    f"🎁 <b>حالا می‌تونی دوستانت رو دعوت کنی!</b>\n\n"
                    f"🔗 <b>لینک دعوت شما:</b>\n"
                    f"<code>{invite_link}</code>\n\n"
                    f"✨ هر دعوت = ۲۰ دانلود اضافی!",
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
    else:
        bot.send_message(
            message.chat.id,
            f"┌─────────────────────┐\n"
            f"│  ❌ <b>خطا در دانلود</b>  │\n"
            f"└─────────────────────┘\n\n"
            f"🔗 <b>لینک:</b> {url[:50]}...\n\n"
            f"📛 <b>خطا:</b> فایلی برای دانلود یافت نشد!\n\n"
            f"⏱️ <b>زمان پردازش:</b> {result['response_time']:.1f} ثانیه\n\n"
            f"🔗 {CHANNEL_USERNAME}",
            parse_mode='HTML'
        )

# ==================== دستورات اصلی ====================
@bot.message_handler(commands=['start'])
@require_membership
def start_command(message):
    user = message.from_user
    user_id = user.id
    
    db.add_user(user_id, user.username, user.first_name, user.last_name)
    
    # بررسی کد دعوت
    if len(message.text.split()) > 1:
        invite_code = message.text.split()[1]
        if invite_code.startswith("INV"):
            cursor = db.conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE invite_code = ?", (invite_code,))
            inviter = cursor.fetchone()
            
            if inviter and inviter[0] != user_id:
                try:
                    cursor.execute('''
                        UPDATE users 
                        SET invite_count = invite_count + 1, 
                            extra_downloads = extra_downloads + 20
                        WHERE user_id = ?
                    ''', (inviter[0],))
                    db.conn.commit()
                    
                    bot.send_message(
                        inviter[0],
                        f"✨ <b>دعوت جدید!</b>\n\n"
                        f"👤 کاربر: {user.first_name or 'بدون نام'}\n"
                        f"🆔 آیدی: {user_id}\n"
                        f"🎁 <b>20 دانلود اضافی دریافت کردید!</b>"
                    )
                except Exception as e:
                    logger.error(f"خطا در ثبت دعوت: {e}")
    
    welcome_text = f"""
┌─────────────────┐
│  🎉 <b>خوش آمدید</b>  │
└─────────────────┘

✨ <b>سلام {user.first_name or 'عزیز'}!</b> 👋

🎬 <b>ربات دانلودر تیک‌تاک حرفه‌ای</b>
• دانلود ویدیو با کیفیت HD
• دانلود عکس‌های تیک‌تاک  
• دانلود موزیک جداگانه
• سرعت فوق‌العاده
• سیستم دعوت دوستان

📌 <b>برای شروع:</b>
۱. از دکمه «دانلود تیک تاک» استفاده کنید
۲. یا مستقیماً لینک تیک‌تاک را ارسال کنید

🔗 کانال ما: {CHANNEL_USERNAME}
    """
    
    bot.send_message(
        user_id,
        welcome_text,
        reply_markup=create_main_menu(),
        parse_mode='HTML'
    )

@bot.message_handler(commands=['panel'])
def admin_panel_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ <b>دسترسی denied!</b>\n\nاین دستور فقط برای مدیر است.")
        return
    
    admin_text = """
┌─────────────────────┐
│  👑 <b>پنل مدیریت</b>  │
└─────────────────────┘

✨ <b>مدیریت کامل ربات</b>

📊 <b>امکانات:</b>
• آمار کامل سیستم
• مدیریت کاربران
• ارسال پیام همگانی
• مدیریت کانال‌ها
• تنظیمات VIP
• ریست کاربران

🔧 <b>برای شروع از منوی زیر استفاده کنید:</b>
    """
    
    bot.send_message(
        message.chat.id,
        admin_text,
        reply_markup=create_admin_menu(),
        parse_mode='HTML'
    )

# ==================== پردازش پیام‌ها ====================
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    try:
        # ========== بررسی وضعیت کاربر (ادمین یا عادی) ==========
        state = get_user_state(user_id)
        if state:
            # اگر کاربر در وضعیت مدیریت است (فقط برای ادمین)
            if user_id == ADMIN_ID:
                process_admin_state(message, state)
                return
        
        # ========== دستورات منوی اصلی (برای همه کاربران) ==========
        if text == "📥 دانلود تیک تاک":
            # درخواست لینک از کاربر
            clear_user_state(user_id)  # پاک کردن هر وضعیت قبلی
            bot.reply_to(
                message,
                f"┌─────────────────────┐\n"
                f"│  📥 <b>درخواست دانلود</b>  │\n"
                f"└─────────────────────┘\n\n"
                f"🔗 <b>لطفاً لینک تیک‌تاک را ارسال کنید:</b>\n\n"
                f"<i>📋 مثال:</i>\n"
                f"• https://vt.tiktok.com/xxxxx/\n"
                f"• https://vm.tiktok.com/xxxxx/\n"
                f"• https://tiktok.com/@user/video/123456789",
                parse_mode='HTML'
            )
            return
        elif text == "👥 دعوت دوستان":
            show_invite_system(message)
            return
        elif text == "📊 آمار من":
            show_user_stats(message)
            return
        elif text == "🆘 پشتیبانی":
            show_support_info(message)
            return
        elif text == "ℹ️ راهنما":
            show_help(message)
            return
        
        # ========== دستورات مخصوص ادمین ==========
        if user_id == ADMIN_ID:
            # منوی مدیریت اصلی
            if text == "📈 آمار کلی سیستم":
                show_system_stats(message)
            elif text == "👥 مدیریت کاربران":
                bot.send_message(message.chat.id, "منوی مدیریت کاربران", reply_markup=create_admin_users_menu())
            elif text == "📢 ارسال همگانی":
                set_user_state(user_id, 'BROADCAST')
                bot.send_message(message.chat.id, "📤 لطفاً پیام خود را برای ارسال همگانی ارسال کنید:", reply_markup=types.ReplyKeyboardRemove())
            elif text == "📣 مدیریت کانال‌ها":
                bot.send_message(message.chat.id, "منوی مدیریت کانال‌ها", reply_markup=create_admin_channels_menu())
            elif text == "⭐ مدیریت VIP":
                bot.send_message(message.chat.id, "منوی مدیریت VIP", reply_markup=create_admin_vip_menu())
            elif text == "🔄 ریست کاربر":
                set_user_state(user_id, 'RESET_USER')
                bot.send_message(message.chat.id, "👤 لطفاً یوزرنیم کاربر را برای ریست ارسال کنید (بدون @):", reply_markup=types.ReplyKeyboardRemove())
            elif text == "🔙 منوی اصلی":
                clear_user_state(user_id)
                bot.send_message(message.chat.id, "🔙 بازگشت به منوی اصلی", reply_markup=create_main_menu())
            
            # منوی مدیریت کاربران
            elif text == "📋 لیست کاربران":
                show_users_list(message)
            elif text == "👤 اطلاعات کاربر":
                set_user_state(user_id, 'USER_INFO')
                bot.send_message(message.chat.id, "👤 لطفاً آیدی کاربر را ارسال کنید:", reply_markup=types.ReplyKeyboardRemove())
            elif text == "🔙 بازگشت":
                bot.send_message(message.chat.id, "🔙 بازگشت به منوی مدیریت", reply_markup=create_admin_menu())
            
            # منوی مدیریت کانال‌ها
            elif text == "📋 لیست کانال‌ها":
                show_channels_list(message)
            elif text == "➕ افزودن کانال":
                set_user_state(user_id, 'ADD_CHANNEL')
                bot.send_message(message.chat.id, "📌 لطفاً یوزرنیم یا لینک کانال/گروه را ارسال کنید:", reply_markup=types.ReplyKeyboardRemove())
            elif text == "➖ حذف کانال":
                set_user_state(user_id, 'REMOVE_CHANNEL')
                bot.send_message(message.chat.id, "🗑️ لطفاً یوزرنیم کانال/گروه را برای حذف ارسال کنید:", reply_markup=types.ReplyKeyboardRemove())
            
            # منوی مدیریت VIP
            elif text == "📋 لیست VIP‌ها":
                show_vip_list(message)
            elif text == "➕ افزودن VIP":
                set_user_state(user_id, 'ADD_VIP')
                bot.send_message(message.chat.id, "⭐ لطفاً آیدی کاربر را برای افزودن VIP ارسال کنید:", reply_markup=types.ReplyKeyboardRemove())
            elif text == "➖ حذف VIP":
                set_user_state(user_id, 'REMOVE_VIP')
                bot.send_message(message.chat.id, "⭐ لطفاً آیدی کاربر را برای حذف VIP ارسال کنید:", reply_markup=types.ReplyKeyboardRemove())
            elif text == "📅 تنظیم مدت VIP":
                set_user_state(user_id, 'SET_VIP')
                bot.send_message(message.chat.id, "📅 لطفاً آیدی کاربر و تعداد روزها را با فاصله ارسال کنید (مثال: 123456789 30):", reply_markup=types.ReplyKeyboardRemove())
            else:
                # اگر هیچکدام از دستورات بالا نبود و کاربر ادمین است، بررسی عضویت و پردازش لینک
                missing_channels = check_membership(user_id)
                if missing_channels:
                    keyboard = types.InlineKeyboardMarkup()
                    for channel in missing_channels:
                        keyboard.add(types.InlineKeyboardButton(
                            text=f"عضویت در {channel['chat_username']}",
                            url=channel['chat_link']
                        ))
                    keyboard.add(types.InlineKeyboardButton(
                        text="✅ بررسی عضویت",
                        callback_data=f"check_membership_{user_id}"
                    ))
                    
                    bot.reply_to(
                        message,
                        f"┌─────────────────────┐\n"
                        f"│  🔔 <b>عضویت اجباری</b>  │\n"
                        f"└─────────────────────┘\n\n"
                        f"📢 برای استفاده از ربات، باید در کانال/گروه‌های زیر عضو شوید:",
                        reply_markup=keyboard,
                        parse_mode='HTML'
                    )
                else:
                    process_tiktok_url(message)
            return  # پایان بخش ادمین
        
        # ========== کاربران عادی - بررسی عضویت و پردازش لینک ==========
        # اگر کاربر عادی است و به این نقطه رسید یعنی دستورات منوی اصلی را ارسال نکرده
        missing_channels = check_membership(user_id)
        if missing_channels:
            keyboard = types.InlineKeyboardMarkup()
            for channel in missing_channels:
                keyboard.add(types.InlineKeyboardButton(
                    text=f"عضویت در {channel['chat_username']}",
                    url=channel['chat_link']
                ))
            keyboard.add(types.InlineKeyboardButton(
                text="✅ بررسی عضویت",
                callback_data=f"check_membership_{user_id}"
            ))
            
            bot.reply_to(
                message,
                f"┌─────────────────────┐\n"
                f"│  🔔 <b>عضویت اجباری</b>  │\n"
                f"└─────────────────────┘\n\n"
                f"📢 برای استفاده از ربات، باید در کانال/گروه‌های زیر عضو شوید:",
                reply_markup=keyboard,
                parse_mode='HTML'
            )
            return
        
        # اگر عضو بود، لینک را پردازش کن
        process_tiktok_url(message)
    
    except Exception as e:
        logger.error(f"خطا در پردازش پیام: {e}")
        bot.reply_to(
            message,
            "⚠️ <b>خطا در پردازش پیام</b>\n\nلطفاً دوباره تلاش کنید.",
            parse_mode='HTML'
        )

def process_admin_state(message, state):
    """پردازش حالت‌های مدیریت"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    try:
        if state['state'] == 'BROADCAST':
            clear_user_state(user_id)
            process_broadcast_message(message)
            bot.send_message(user_id, "✅ عملیات ارسال همگانی انجام شد.", reply_markup=create_admin_menu())
        
        elif state['state'] == 'RESET_USER':
            clear_user_state(user_id)
            if text:
                if db.reset_user(text):
                    bot.send_message(user_id, f"✅ اطلاعات کاربر @{text} با موفقیت ریست شد.", reply_markup=create_admin_menu())
                else:
                    bot.send_message(user_id, f"❌ کاربر با یوزرنیم @{text} یافت نشد.", reply_markup=create_admin_menu())
            else:
                bot.send_message(user_id, "❌ لطفاً یوزرنیم معتبر ارسال کنید.", reply_markup=create_admin_menu())
        
        elif state['state'] == 'ADD_CHANNEL':
            clear_user_state(user_id)
            if text:
                chat_username = ""
                chat_link = ""
                
                if text.startswith('@'):
                    chat_username = text
                    chat_link = f"https://t.me/{text.replace('@', '')}"
                elif text.startswith('https://t.me/'):
                    chat_link = text
                    chat_username = '@' + text.split('/')[-1]
                else:
                    chat_username = '@' + text
                    chat_link = f"https://t.me/{text}"
                
                if db.add_channel(chat_username, chat_link):
                    bot.send_message(user_id, f"✅ {chat_username} با موفقیت اضافه شد.", reply_markup=create_admin_menu())
                else:
                    bot.send_message(user_id, f"❌ خطا در اضافه کردن یا تکراری بودن.", reply_markup=create_admin_menu())
            else:
                bot.send_message(user_id, "❌ لطفاً یوزرنیم یا لینک معتبر ارسال کنید.", reply_markup=create_admin_menu())
        
        elif state['state'] == 'REMOVE_CHANNEL':
            clear_user_state(user_id)
            if text:
                channel_username = text
                if not channel_username.startswith('@'):
                    channel_username = '@' + channel_username
                
                if db.remove_channel(channel_username):
                    bot.send_message(user_id, f"✅ {channel_username} با موفقیت حذف شد.", reply_markup=create_admin_menu())
                else:
                    bot.send_message(user_id, f"❌ کانال/گروه یافت نشد.", reply_markup=create_admin_menu())
            else:
                bot.send_message(user_id, "❌ لطفاً یوزرنیم معتبر ارسال کنید.", reply_markup=create_admin_menu())
        
        elif state['state'] == 'ADD_VIP':
            clear_user_state(user_id)
            if text:
                try:
                    target_user_id = int(text)
                    user = db.get_user(target_user_id)
                    if not user:
                        db.add_user(target_user_id, "", "", "")
                    
                    if db.set_vip(target_user_id, is_vip=True, days=30):
                        bot.send_message(user_id, f"✅ کاربر {target_user_id} به VIP تبدیل شد (30 روز).", reply_markup=create_admin_menu())
                        try:
                            bot.send_message(target_user_id, "🎉 شما به کاربر VIP ربات تبدیل شدید! (30 روز)")
                        except:
                            pass
                    else:
                        bot.send_message(user_id, f"❌ خطا در تنظیم VIP کاربر.", reply_markup=create_admin_menu())
                except ValueError:
                    bot.send_message(user_id, "❌ لطفاً یک عدد معتبر (آیدی کاربر) ارسال کنید.", reply_markup=create_admin_menu())
            else:
                bot.send_message(user_id, "❌ لطفاً آیدی کاربر را ارسال کنید.", reply_markup=create_admin_menu())
        
        elif state['state'] == 'REMOVE_VIP':
            clear_user_state(user_id)
            if text:
                try:
                    target_user_id = int(text)
                    if db.set_vip(target_user_id, is_vip=False):
                        bot.send_message(user_id, f"✅ وضعیت VIP کاربر {target_user_id} حذف شد.", reply_markup=create_admin_menu())
                    else:
                        bot.send_message(user_id, f"❌ خطا در حذف VIP کاربر.", reply_markup=create_admin_menu())
                except ValueError:
                    bot.send_message(user_id, "❌ لطفاً یک عدد معتبر (آیدی کاربر) ارسال کنید.", reply_markup=create_admin_menu())
            else:
                bot.send_message(user_id, "❌ لطفاً آیدی کاربر را ارسال کنید.", reply_markup=create_admin_menu())
        
        elif state['state'] == 'SET_VIP':
            clear_user_state(user_id)
            if text:
                try:
                    parts = text.split()
                    if len(parts) >= 2:
                        target_user_id = int(parts[0])
                        days = int(parts[1])
                        
                        user = db.get_user(target_user_id)
                        if not user:
                            bot.send_message(user_id, f"❌ کاربر یافت نشد.", reply_markup=create_admin_menu())
                            return
                        
                        if db.set_vip(target_user_id, is_vip=True, days=days):
                            bot.send_message(user_id, f"✅ VIP کاربر {target_user_id} تنظیم شد (مدت: {days} روز).", reply_markup=create_admin_menu())
                        else:
                            bot.send_message(user_id, f"❌ خطا در تنظیم VIP کاربر.", reply_markup=create_admin_menu())
                    else:
                        bot.send_message(user_id, "❌ فرمت صحیح: آیدی کاربر تعداد روز", reply_markup=create_admin_menu())
                except ValueError:
                    bot.send_message(user_id, "❌ لطفاً ورودی معتبر ارسال کنید.", reply_markup=create_admin_menu())
            else:
                bot.send_message(user_id, "❌ لطفاً آیدی کاربر و تعداد روزها را ارسال کنید.", reply_markup=create_admin_menu())
        
        elif state['state'] == 'USER_INFO':
            clear_user_state(user_id)
            if text:
                try:
                    target_user_id = int(text)
                    user = db.get_user(target_user_id)
                    if user:
                        status = "⭐ VIP" if user['is_vip'] else "👤 معمولی"
                        info_text = f"""
┌─────────────────────┐
│  👤 <b>اطلاعات کاربر</b>  │
└─────────────────────┘

🆔 <b>آیدی:</b> <code>{target_user_id}</code>
👤 <b>نام:</b> {user['first_name'] or 'ندارد'}
📱 <b>یوزرنیم:</b> @{user['username'] or 'ندارد'}
📅 <b>تاریخ عضویت:</b> {user['join_date'][:10] if user['join_date'] else 'نامشخص'}
📊 <b>وضعیت:</b> {status}

📥 <b>آمار دانلود:</b>
• امروز: {user['daily_downloads'] or 0}
• مجموع: {user['total_downloads'] or 0}
• دعوت‌ها: {user['invite_count'] or 0}
• دانلودهای اضافی: {user['extra_downloads'] or 0}
                        """
                        bot.send_message(user_id, info_text, parse_mode='HTML', reply_markup=create_admin_menu())
                    else:
                        bot.send_message(user_id, f"❌ کاربر یافت نشد.", reply_markup=create_admin_menu())
                except ValueError:
                    bot.send_message(user_id, "❌ لطفاً یک عدد معتبر (آیدی کاربر) ارسال کنید.", reply_markup=create_admin_menu())
            else:
                bot.send_message(user_id, "❌ لطفاً آیدی کاربر را ارسال کنید.", reply_markup=create_admin_menu())
    
    except Exception as e:
        logger.error(f"خطا در پردازش حالت مدیریت: {e}")
        bot.send_message(user_id, "❌ خطا در پردازش عملیات.", reply_markup=create_admin_menu())

# ==================== توابع منوهای مدیریت ====================
def show_system_stats(message):
    stats = db.get_stats()
    
    stats_text = f"""
┌─────────────────────┐
│  📈 <b>آمار کلی سیستم</b>  │
└─────────────────────┘

👥 <b>آمار کاربران:</b>
• کل کاربران: <code>{stats['total_users']}</code>
• کاربران VIP: <code>{stats['vip_users']}</code>
• کاربران عادی: <code>{stats['total_users'] - stats['vip_users']}</code>

📥 <b>آمار دانلودها:</b>
• کل دانلودها: <code>{stats['total_downloads']}</code>
• دانلودهای امروز: <code>{stats['today_downloads']}</code>

🕒 <b>اطلاعات سرور:</b>
• زمان: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}
• وضعیت: <code>🟢 آنلاین</code>
    """
    
    bot.reply_to(message, stats_text, parse_mode='HTML')

def show_users_list(message):
    cursor = db.conn.cursor()
    cursor.execute("SELECT user_id, username, first_name, join_date, total_downloads, is_vip FROM users ORDER BY user_id DESC LIMIT 50")
    users = cursor.fetchall()
    
    if not users:
        bot.reply_to(message, "📭 <b>هیچ کاربری ثبت نشده است.</b>", parse_mode='HTML')
        return
    
    users_text = "👥 <b>آخرین ۵۰ کاربر</b>\n\n"
    
    for i, user in enumerate(users, 1):
        user_id = user[0]
        username = user[1] or "بدون یوزرنیم"
        first_name = user[2] or "بدون نام"
        join_date = user[3][:10] if user[3] else "نامشخص"
        total_downloads = user[4] or 0
        is_vip = "⭐" if user[5] else ""
        
        users_text += f"{i}. {first_name} {is_vip}\n"
        users_text += f"   👤 @{username}\n"
        users_text += f"   🆔 <code>{user_id}</code>\n"
        users_text += f"   📅 {join_date}\n"
        users_text += f"   📥 {total_downloads} دانلود\n\n"
    
    bot.reply_to(message, users_text, parse_mode='HTML')

def show_channels_list(message):
    channels = db.get_required_channels()
    
    channels_text = f"""
┌─────────────────────┐
│  📋 <b>لیست کانال‌ها</b>  │
└─────────────────────┘

"""
    
    if not channels:
        channels_text += "📭 <i>هیچ کانال/گروهی ثبت نشده است.</i>"
    else:
        for i, channel in enumerate(channels, 1):
            channels_text += f"\n{i}. <b>{channel['chat_username']}</b>\n"
            channels_text += f"   🔗 {channel['chat_link']}\n"
            channels_text += f"   📅 {channel['added_date'][:10]}\n"
    
    bot.reply_to(message, channels_text, parse_mode='HTML')

def show_vip_list(message):
    cursor = db.conn.cursor()
    cursor.execute("SELECT user_id, username, first_name, total_downloads FROM users WHERE is_vip = 1 ORDER BY user_id DESC")
    vip_users = cursor.fetchall()
    
    vip_text = f"""
┌─────────────────────┐
│  📋 <b>لیست VIP‌ها</b>  │
└─────────────────────┘

"""
    
    if not vip_users:
        vip_text += "📭 <i>هیچ کاربر VIPی وجود ندارد.</i>"
    else:
        for i, user in enumerate(vip_users, 1):
            username = user[1] or "بدون یوزرنیم"
            first_name = user[2] or "بدون نام"
            downloads = user[3] or 0
            
            vip_text += f"\n{i}. <b>{first_name}</b>\n"
            vip_text += f"   👤 @{username}\n"
            vip_text += f"   🆔 <code>{user[0]}</code>\n"
            vip_text += f"   📥 دانلودها: {downloads}\n"
    
    bot.reply_to(message, vip_text, parse_mode='HTML')

# ==================== توابع کاربران ====================
def show_invite_system(message):
    user_id = message.from_user.id
    user = db.get_user(user_id)
    invite_link = db.get_invite_link(user_id)
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(
        "📱 اشتراک‌گذاری لینک",
        url=f"https://t.me/share/url?url={urllib.parse.quote(invite_link)}&text=🎬 ربات دانلودر تیک‌تاک! دانلود رایگان ویدیو و موزیک از تیک‌تاک"
    ))
    
    invite_text = f"""
┌─────────────────────┐
│  👥 <b>سیستم دعوت</b>  │
└─────────────────────┘

🎁 <b>هر دعوت = ۲۰ دانلود اضافی!</b>

📊 <b>آمار شما:</b>
• دعوت‌های موفق: <code>{user['invite_count'] if user else 0}</code>
• دانلودهای اضافی: <code>{(user['invite_count'] if user else 0) * 20}</code>
• دانلودهای امروز: <code>{user['daily_downloads'] if user else 0}/{(5 + (user['extra_downloads'] if user else 0))}</code>

🔗 <b>لینک اختصاصی شما:</b>
<code>{invite_link}</code>

📋 <b>نحوه کار:</b>
۱. این لینک را برای دوستان بفرستید
۲. دوستان با لینک شما وارد ربات شوند
۳. شما <b>۲۰ دانلود اضافی</b> دریافت می‌کنید

💡 <b>توجه:</b> هر کاربر فقط یک بار قابل شمارش است.
    """
    
    bot.reply_to(message, invite_text, reply_markup=keyboard, parse_mode='HTML')

def show_user_stats(message):
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    if not user:
        db.add_user(user_id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
        user = db.get_user(user_id)
    
    status = "⭐ VIP" if user['is_vip'] else "👤 معمولی"
    
    daily_limit = 5 + (user['extra_downloads'] or 0)
    remaining = max(0, daily_limit - (user['daily_downloads'] or 0))
    
    stats_text = f"""
┌─────────────────────┐
│  📊 <b>آمار کاربری</b>  │
└─────────────────────┘

👤 <b>اطلاعات شخصی:</b>
• نام: {user['first_name'] or 'ندارد'}
• یوزرنیم: @{user['username'] or 'ندارد'}
• آیدی: <code>{user_id}</code>
• وضعیت: {status}

📥 <b>آمار دانلود:</b>
• دانلودهای امروز: {user['daily_downloads'] or 0}/{daily_limit}
• باقی‌مانده امروز: {remaining}
• مجموع دانلودها: {user['total_downloads'] or 0}

👥 <b>سیستم دعوت:</b>
• دعوت‌های موفق: {user['invite_count'] or 0}
• دانلودهای اضافی: {user['extra_downloads'] or 0}

📅 <b>تاریخ عضویت:</b>
{user['join_date'][:10] if user['join_date'] else 'نامشخص'}
    """
    
    bot.reply_to(message, stats_text, parse_mode='HTML')

def show_support_info(message):
    support_text = f"""
┌─────────────────────┐
│  🆘 <b>پشتیبانی</b>  │
└─────────────────────┘

✨ <b>برای ارتباط با ادمین در موارد زیر:</b>

• گزارش خطا در ربات
• درخواست اسپانسر شدن
• درخواست تبلیغات در ربات
• سایر موارد

👨‍💼 <b>با ادمین تماس بگیرید:</b> {SUPPORT_USERNAME}

🔗 کانال ما: {CHANNEL_USERNAME}

⏰ <b>ساعت پاسخگویی:</b> ۲۴ ساعته
    """
    
    bot.send_message(
        message.chat.id,
        support_text,
        parse_mode='HTML'
    )

def show_help(message):
    help_text = f"""
┌─────────────────────┐
│  ℹ️ <b>راهنمای ربات</b>  │
└─────────────────────┘

🎬 <b>نحوه استفاده:</b>
۱. از دکمه «دانلود تیک تاک» استفاده کنید
۲. لینک تیک‌تاک را ارسال کنید
۳. ربات نوع محتوا را از شما می‌پرسد
۴. فایل مورد نظر دانلود می‌شود

💡 <b>روش دیگر:</b>
• مستقیماً لینک را ارسال کنید
• ربات از شما می‌پرسد چه چیزی دانلود شود

🔗 <b>فرمت‌های لینک قابل قبول:</b>
• https://vt.tiktok.com/xxxxxxxx/
• https://vm.tiktok.com/xxxxxxxx/
• https://www.tiktok.com/@user/video/123456789

📊 <b>محدودیت‌ها:</b>
• کاربران عادی: ۵ دانلود رایگان روزانه
• هر دعوت موفق: ۲۰ دانلود اضافی
• کاربران VIP: دانلود نامحدود

👥 <b>سیستم دعوت:</b>
با دعوت هر دوست، ۲۰ دانلود اضافی دریافت می‌کنید!

🔗 <b>کانال پشتیبانی:</b>
{CHANNEL_USERNAME}
👨‍💼 <b>پشتیبان:</b> {SUPPORT_USERNAME}
    """
    
    bot.reply_to(message, help_text, parse_mode='HTML')

# ==================== سیستم پردازش لینک ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('choose_type_'))
def choose_type_callback(call):
    """انتخاب نوع محتوا برای لینک ارسال شده"""
    user_id = call.from_user.id
    parts = call.data.split('_')
    download_type = parts[2]
    url_id = parts[3]
    url = temp_urls.get(url_id)
    
    if not url:
        bot.answer_callback_query(call.id, "❌ لینک منقضی شده است. لطفاً دوباره ارسال کنید.")
        return
    
    # ویرایش پیام و حذف کیبورد
    try:
        bot.edit_message_text(
            f"┌─────────────────────┐\n"
            f"│  ⚡ <b>در حال پردازش</b>  │\n"
            f"└─────────────────────┘\n\n"
            f"🔗 <b>لینک:</b>\n<code>{url[:50]}...</code>\n\n"
            f"⏳ <b>در حال دانلود {download_type} ...</b>\n"
            f"⚡ لطفاً صبر کنید...",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='HTML'
        )
    except:
        # اگر ویرایش نشد، پیام جدید بفرست
        bot.send_message(
            call.message.chat.id,
            f"┌─────────────────────┐\n"
            f"│  ⚡ <b>در حال پردازش</b>  │\n"
            f"└─────────────────────┘\n\n"
            f"🔗 <b>لینک:</b>\n<code>{url[:50]}...</code>\n\n"
            f"⏳ <b>در حال دانلود {download_type} ...</b>\n"
            f"⚡ لطفاً صبر کنید...",
            parse_mode='HTML'
        )
    
    # دانلود با نوع انتخابی - از پیام ویرایش شده به عنوان processing_msg استفاده می‌کنیم
    download_specific_type(url, download_type, user_id, call.message, processing_msg_id=call.message.message_id)
    
    bot.answer_callback_query(call.id, f"⏳ در حال دانلود {download_type}...")

def process_tiktok_url(message):
    """پردازش لینک تیک‌تاک ارسال شده"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    # استخراج لینک با استفاده از دانلودر
    url = downloader.extract_tiktok_url(text)
    
    if not url:
        bot.reply_to(
            message,
            f"┌─────────────────────┐\n"
            f"│  ⚠️ <b>لینک نامعتبر</b>  │\n"
            f"└─────────────────────┘\n\n"
            f"🔗 <b>لینک ارسال شده معتبر نیست!</b>\n\n"
            f"📋 <b>لطفاً لینک معتبر تیک‌تاک ارسال کنید:</b>\n"
            f"• https://vt.tiktok.com/xxxxx/\n"
            f"• https://vm.tiktok.com/xxxxx/\n"
            f"• https://tiktok.com/@user/video/123456789\n\n"
            f"💡 <b>راهنمایی:</b>\n"
            f"۱. در اپلیکیشن تیک‌تاک روی اشتراک‌گذاری کلیک کنید\n"
            f"۲. گزینه «کپی لینک» را انتخاب کنید\n"
            f"۳. لینک را اینجا ارسال کنید",
            parse_mode='HTML'
        )
        return
    
    # اگر کاربر وضعیت انتظار لینک نداشت (همیشه true)، از او بپرسیم چه چیزی دانلود کند
    # ذخیره URL در دیکشنری موقت
    url_id = store_temp_url(url)
    
    keyboard = types.InlineKeyboardMarkup(row_width=3)
    keyboard.add(
        types.InlineKeyboardButton("🎬 ویدیو", callback_data=f"choose_type_video_{url_id}"),
        types.InlineKeyboardButton("🖼️ عکس", callback_data=f"choose_type_image_{url_id}"),
        types.InlineKeyboardButton("🎵 موزیک", callback_data=f"choose_type_music_{url_id}")
    )
    
    bot.reply_to(
        message,
        f"┌─────────────────────┐\n"
        f"│  🤔 <b>انتخاب نوع</b>  │\n"
        f"└─────────────────────┘\n\n"
        f"🔗 <b>لینک:</b>\n<code>{url[:50]}...</code>\n\n"
        f"📥 <b>کدام بخش را دانلود کنم؟</b>",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

# ==================== سیستم ارسال همگانی ====================
def process_broadcast_message(message):
    users = db.conn.cursor().execute("SELECT user_id FROM users").fetchall()
    total_users = len(users)
    
    progress_msg = bot.reply_to(message, f"⏳ <b>در حال ارسال به {total_users} کاربر...</b>\n\n📊 وضعیت: 0/{total_users}", parse_mode='HTML')
    
    success = 0
    failed = 0
    
    for index, user_row in enumerate(users, 1):
        user_id = user_row[0]
        
        try:
            # استفاده از کپی پیام برای پشتیبانی از تمام فرمت‌ها
            bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                caption=message.caption if hasattr(message, 'caption') else None,
                parse_mode='HTML' if hasattr(message, 'caption') and message.caption else None
            )
            success += 1
            
            # آپدیت پیام پیشرفت هر ۱۰ کاربر
            if index % 10 == 0 or index == total_users:
                try:
                    bot.edit_message_text(
                        f"⏳ <b>در حال ارسال به {total_users} کاربر...</b>\n\n"
                        f"📊 وضعیت: {index}/{total_users}\n"
                        f"✅ موفق: {success}\n"
                        f"❌ ناموفق: {failed}",
                        message.chat.id,
                        progress_msg.message_id,
                        parse_mode='HTML'
                    )
                except:
                    pass
            
            time.sleep(0.1)
            
        except Exception as e:
            failed += 1
            logger.error(f"خطا در ارسال به کاربر {user_id}: {e}")
    
    # نتیجه نهایی
    result_text = f"""
┌─────────────────────┐
│  ✅ <b>ارسال تکمیل شد</b>  │
└─────────────────────┘

📊 <b>نتایج ارسال همگانی:</b>
• کل کاربران: {total_users}
• ارسال موفق: {success}
• ارسال ناموفق: {failed}
• درصد موفقیت: {round(success/max(total_users, 1)*100, 2)}%

🕒 <b>زمان اتمام:</b>
{datetime.now().strftime('%Y/%m/%d %H:%M:%S')}
    """
    
    bot.edit_message_text(
        result_text,
        message.chat.id,
        progress_msg.message_id,
        parse_mode='HTML'
    )

# ==================== راه‌اندازی ====================
def start_bot():
    print("\n" + "=" * 60)
    print("🚀 در حال راه‌اندازی ربات...")
    print("=" * 60)
    
    retry_count = 0
    max_retries = 100
    
    while retry_count < max_retries:
        try:
            bot_info = bot.get_me()
            print(f"✅ ربات: @{bot_info.username}")
            print(f"🆔 آیدی: {bot_info.id}")
            print(f"👑 ادمین: {ADMIN_ID}")
            print(f"📢 کانال: {CHANNEL_USERNAME}")
            print(f"👨‍💼 پشتیبان: {SUPPORT_USERNAME}")
            
            stats = db.get_stats()
            print(f"📊 کاربران: {stats['total_users']}")
            print(f"📥 دانلودها: {stats['total_downloads']}")
            print(f"⭐ VIP‌ها: {stats['vip_users']}")
            
            print(f"⏰ زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 60)
            print("\n🤖 ربات آنلاین و آماده است!")
            print("=" * 60)
            
            bot.polling(none_stop=True, timeout=30)
            
        except Exception as e:
            retry_count += 1
            logger.error(f"❌ خطا در راه‌اندازی: {e}")
            
            if retry_count < max_retries:
                wait_time = 10
                print(f"\n🔄 تلاش مجدد در {wait_time} ثانیه... ({retry_count}/{max_retries})")
                
                # نمایش اطلاعات
                stats = db.get_stats()
                print(f"✅ ربات: @danloode_Mood_bot")
                print(f"🆔 آیدی: 8589470820")
                print(f"👑 ادمین: 6906387548")
                print(f"📢 کانال: @ARIANA_MOOD")
                print(f"📊 کاربران: {stats['total_users']}")
                print(f"📥 دانلودها: {stats['total_downloads']}")
                print(f"⭐ VIP‌ها: {stats['vip_users']}")
                print(f"⏰ زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print("=" * 60)
                
                time.sleep(wait_time)
            else:
                print(f"\n❌ حداکثر تلاش‌ها ({max_retries}) انجام شد. برنامه خاتمه می‌یابد.")
                break

# ==================== اجرای اصلی ====================
if __name__ == "__main__":
    print("🤖 شروع برنامه...")
    start_bot()
