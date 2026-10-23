# =====================================================
#  🚀 FREEBOTHOSTING SERVER - RENDER ULTRA LIGHT
# =====================================================
import telebot
import subprocess
import os
import sys
import time
import re
import threading
import logging
import sqlite3
from datetime import datetime
from telebot import types

# ================== AYARLAR (RENDER ENV) ==================
TOKEN = os.environ.get('BOT_TOKEN', '')
OWNER_ID = int(os.environ.get('OWNER_ID', '0'))
ADMIN_ID = int(os.environ.get('ADMIN_ID', '0'))
UPDATE_CHANNEL = os.environ.get('UPDATE_CHANNEL', 'https://t.me/generalotp')
SUPPORT_USERNAME = os.environ.get('SUPPORT_USERNAME', '@ibenler')

if not TOKEN:
    raise SystemExit("❌ BOT_TOKEN eksik! Render Environment'a ekle.")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
BOTS_DIR = os.path.join(BASE_DIR, 'bots')
DB_PATH = os.path.join(BASE_DIR, 'host.db')
os.makedirs(BOTS_DIR, exist_ok=True)

ADMIN_IDS = {x for x in [OWNER_ID, ADMIN_ID] if x > 0}
FREE_LIMIT = 6

logging.basicConfig(level=logging.WARNING,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(TOKEN, parse_mode='Markdown')

# ================== BELLEK ==================
running = {}
pending = {}
pid_counter = [0]
pending_lock = threading.Lock()

# ================== DB ==================
db_lock = threading.Lock()
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.execute('CREATE TABLE IF NOT EXISTS files (uid INTEGER, name TEXT, PRIMARY KEY(uid,name))')
db.execute('CREATE TABLE IF NOT EXISTS approved (uid INTEGER, name TEXT, PRIMARY KEY(uid,name))')
db.commit()

def db_exec(sql, params=()):
    with db_lock:
        cur = db.execute(sql, params)
        db.commit()
        return cur

def user_file_count(uid):
    with db_lock:
        return db.execute('SELECT COUNT(*) FROM files WHERE uid=?', (uid,)).fetchone()[0]

def add_file(uid, name):
    db_exec('INSERT OR IGNORE INTO files VALUES (?,?)', (uid, name))

def remove_file(uid, name):
    db_exec('DELETE FROM files WHERE uid=? AND name=?', (uid, name))
    db_exec('DELETE FROM approved WHERE uid=? AND name=?', (uid, name))

def is_approved(uid, name):
    with db_lock:
        return db.execute('SELECT 1 FROM approved WHERE uid=? AND name=?', (uid, name)).fetchone() is not None

def mark_approved(uid, name):
    db_exec('INSERT OR IGNORE INTO approved VALUES (?,?)', (uid, name))

def get_files(uid):
    with db_lock:
        return db.execute('SELECT name FROM files WHERE uid=?', (uid,)).fetchall()

# ================== YARDIMCI ==================
def user_dir(uid):
    d = os.path.join(BOTS_DIR, str(uid))
    os.makedirs(d, exist_ok=True)
    return d

def skey(uid, name):
    return f"{uid}_{name}"

def is_running(uid, name):
    sk = skey(uid, name)
    info = running.get(sk)
    if not info:
        return False
    p = info['proc']
    if p.poll() is not None:
        try:
            if info['log'] and not info['log'].closed:
                info['log'].close()
        except:
            pass
        running.pop(sk, None)
        return False
    return True

def kill_bot(uid, name):
    sk = skey(uid, name)
    info = running.pop(sk, None)
    if not info:
        return
    try:
        info['proc'].terminate()
        info['proc'].wait(timeout=3)
    except:
        try: info['proc'].kill()
        except: pass
    try:
        if info['log'] and not info['log'].closed:
            info['log'].close()
    except: pass

# ================== TOKEN REBRAND ==================
def find_tokens(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            txt = f.read()
        return list(set(re.findall(r'\b(\d{8,12}:[A-Za-z0-9_-]{35})\b', txt)))
    except:
        return []

def rebrand(token):
    try:
        import requests
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=8).json()
        if not r.get('ok'):
            return
        u = r['result'].get('username', 'Bot')
        requests.post(f"https://api.telegram.org/bot{token}/setMyName",
                     data={'name': f"{u} | FreeBotHosting"[:64]}, timeout=8)
        requests.post(f"https://api.telegram.org/bot{token}/setMyDescription",
                     data={'description': f"🚀 {UPDATE_CHANNEL} | {SUPPORT_USERNAME}"[:512]}, timeout=8)
    except:
        pass

# ================== PAKET KURULUMU ==================
_install_lock = threading.Lock()

def ensure_module(mod_name):
    pkg = {
        'telebot': 'pyTelegramBotAPI', 'telegram': 'python-telegram-bot',
        'aiogram': 'aiogram', 'pyrogram': 'pyrogram', 'telethon': 'telethon',
        'bs4': 'beautifulsoup4', 'cv2': 'opencv-python', 'PIL': 'Pillow',
        'yaml': 'PyYAML', 'dotenv': 'python-dotenv', 'dateutil': 'python-dateutil',
        'sklearn': 'scikit-learn', 'mysql': 'mysql-connector-python',
    }.get(mod_name.lower(), mod_name)
    with _install_lock:
        try:
            subprocess.run([sys.executable, '-c', f'import {mod_name}'],
                          capture_output=True, timeout=8, check=True)
            return True
        except:
            pass
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', pkg,
                          '--quiet', '--no-cache-dir', '--disable-pip-version-check',
                          '--no-warn-script-location'],
                          capture_output=True, timeout=180, check=True)
            return True
        except:
            return False

def preflight_and_install(script_path, msg):
    try:
        p = subprocess.Popen([sys.executable, script_path],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE,
                            text=True, encoding='utf-8', errors='ignore')
        try:
            _, err = p.communicate(timeout=4)
        except subprocess.TimeoutExpired:
            p.terminate()
            try: p.wait(timeout=1)
            except: p.kill()
            return True
        if p.returncode == 0:
            return True
        m = re.search(r"ModuleNotFoundError: No module named '([^']+)'", err or "")
        if m:
            mod = m.group(1).split('.')[0]
            bot.reply_to(msg, f"📦 `{mod}` kuruluyor...")
            if ensure_module(mod):
                bot.reply_to(msg, f"✅ `{mod}` kuruldu, tekrar deneniyor...")
                return preflight_and_install(script_path, msg)
            else:
                bot.reply_to(msg, f"❌ `{mod}` kurulamadı.")
                return False
        if err:
            bot.reply_to(msg, f"❌ Hata:\n```\n{err[-400:]}\n```")
        return False
    except Exception as e:
        logger.error(f"preflight: {e}")
        return False

# ================== BOT BAŞLAT ==================
def start_bot(uid, name, chat_id=None):
    fp = os.path.join(user_dir(uid), name)
    if not os.path.exists(fp):
        if chat_id:
            bot.send_message(chat_id, f"❌ `{name}` bulunamadı.")
        return False
    if is_running(uid, name):
        if chat_id:
            bot.send_message(chat_id, "⚠️ Zaten çalışıyor.")
        return False

    class _M:
        def __init__(self, cid):
            self.chat = types.Chat(id=cid, type='private')
    m = _M(chat_id or uid)

    if not preflight_and_install(fp, m):
        return False

    log_path = os.path.join(user_dir(uid), f"{os.path.splitext(name)[0]}.log")
    try:
        log = open(log_path, 'w', encoding='utf-8', errors='ignore')
    except Exception as e:
        if chat_id:
            bot.send_message(chat_id, f"❌ Log açılamadı: {e}")
        return False

    try:
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        si = None
        if os.name == 'nt':
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE

        proc = subprocess.Popen(
            [sys.executable, fp],
            cwd=user_dir(uid),
            stdout=log, stderr=log, stdin=subprocess.DEVNULL,
            env=env, startupinfo=si,
            encoding='utf-8', errors='ignore'
        )
        running[skey(uid, name)] = {'proc': proc, 'log': log, 'start': datetime.now()}

        for tk in find_tokens(fp):
            threading.Thread(target=rebrand, args=(tk,), daemon=True).start()

        if chat_id:
            bot.send_message(chat_id, f"✅ `{name}` başlatıldı (PID: `{proc.pid}`)")
        return True
    except Exception as e:
        logger.error(f"start: {e}")
        try: log.close()
        except: pass
        if chat_id:
            bot.send_message(chat_id, f"❌ Başlatılamadı: {e}")
        return False

# ================== ONAY ==================
def new_approval(uid, name, file_path, msg):
    with pending_lock:
        pid_counter[0] += 1
        aid = pid_counter[0]
        pending[aid] = {
            'uid': uid, 'name': name, 'path': file_path,
            'chat': msg.chat.id, 'time': time.time()
        }
    u = msg.from_user
    text = (
        f"🔔 <b>YENİ DOSYA ONAYI</b>\n\n"
        f"👤 <b>{u.first_name}</b>\n"
        f"🆔 <code>{uid}</code>\n"
        f"📛 @{u.username or 'yok'}\n"
        f"📄 <code>{name}</code>\n"
        f"🆔 Onay: <b>#{aid}</b>"
    )
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(
        types.InlineKeyboardButton(f"✅ Onayla #{aid}", callback_data=f"ap_{aid}"),
        types.InlineKeyboardButton(f"❌ Reddet #{aid}", callback_data=f"rj_{aid}")
    )
    for adm in ADMIN_IDS:
        try:
            with open(file_path, 'rb') as f:
                bot.send_document(adm, f, caption=text, reply_markup=kb, parse_mode='HTML')
        except:
            try:
                bot.send_message(adm, text, reply_markup=kb, parse_mode='HTML')
            except:
                pass
    bot.reply_to(msg, "⏳ Admin onayına gönderildi. Onaylanınca otomatik başlar.")

def approve(aid):
    with pending_lock:
        info = pending.pop(aid, None)
    if not info:
        return None, "Onay bulunamadı."
    uid, name = info['uid'], info['name']
    fp = info['path']
    if not os.path.exists(fp):
        return info, "Dosya artık yok."
    mark_approved(uid, name)
    add_file(uid, name)
    start_bot(uid, name, chat_id=info['chat'])
    return info, "✅ Onaylandı ve başlatıldı."

def reject(aid):
    with pending_lock:
        info = pending.pop(aid, None)
    if not info:
        return None, "Onay bulunamadı."
    try:
        if os.path.exists(info['path']):
            os.remove(info['path'])
    except: pass
    remove_file(info['uid'], info['name'])
    try:
        bot.send_message(info['chat'], f"❌ `{info['name']}` reddedildi.")
    except: pass
    return info, "❌ Reddedildi."

# ================== MENÜ ==================
def main_menu(uid):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(
        types.InlineKeyboardButton("📢 Kanal", url=UPDATE_CHANNEL),
        types.InlineKeyboardButton("📞 Destek", url=f"https://t.me/{SUPPORT_USERNAME.replace('@','')}")
    )
    kb.row(types.InlineKeyboardButton("📤 Dosya Yükle", callback_data="upload"))
    kb.row(types.InlineKeyboardButton("📂 Dosyalarım", callback_data="files"))
    return kb

def file_menu(uid, name, rid):
    running_now = is_running(uid, name)
    kb = types.InlineKeyboardMarkup(row_width=2)
    if running_now:
        kb.row(
            types.InlineKeyboardButton("🔴 Durdur", callback_data=f"st_{uid}_{name}"),
            types.InlineKeyboardButton("🔄 Yeniden", callback_data=f"rs_{uid}_{name}")
        )
    else:
        kb.row(
            types.InlineKeyboardButton("🟢 Başlat", callback_data=f"go_{uid}_{name}"),
            types.InlineKeyboardButton("🔄 Yeniden", callback_data=f"rs_{uid}_{name}")
        )
    kb.row(
        types.InlineKeyboardButton("📜 Log", callback_data=f"lg_{uid}_{name}"),
        types.InlineKeyboardButton("🗑 Sil", callback_data=f"dl_{uid}_{name}")
    )
    kb.row(types.InlineKeyboardButton("🔙 Geri", callback_data="files"))
    return kb

# ================== HANDLER ==================
@bot.message_handler(commands=['start'])
def cmd_start(m):
    uid = m.from_user.id
    cnt = user_file_count(uid)
    txt = (
        f"🌟 **FREEBOTHOSTING SERVER** 🌟\n\n"
        f"Merhaba **{m.from_user.first_name}**!\n\n"
        f"👤 ID: `{uid}`\n"
        f"📁 Dosya: `{cnt}/{FREE_LIMIT}`\n\n"
        f"📌 Sadece `.py` dosyası kabul edilir.\n"
        f"📌 Her dosya admin onayı sonrası çalışır.\n\n"
        f"📢 {UPDATE_CHANNEL}\n"
        f"💬 {SUPPORT_USERNAME}"
    )
    bot.send_message(m.chat.id, txt, reply_markup=main_menu(uid))

@bot.message_handler(commands=['pending'])
def cmd_pending(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    with pending_lock:
        items = list(pending.items())
    if not items:
        bot.reply_to(m, "Bekleyen yok.")
        return
    for aid, info in items:
        kb = types.InlineKeyboardMarkup()
        kb.row(
            types.InlineKeyboardButton(f"✅ #{aid}", callback_data=f"ap_{aid}"),
            types.InlineKeyboardButton(f"❌ #{aid}", callback_data=f"rj_{aid}")
        )
        bot.send_message(m.chat.id,
            f"#{aid} - `{info['name']}` (uid `{info['uid']}`)",
            reply_markup=kb)

@bot.message_handler(content_types=['document'])
def on_document(m):
    uid = m.from_user.id
    doc = m.document
    name = doc.file_name or ''
    if not name.lower().endswith('.py'):
        bot.reply_to(m, "❌ Sadece `.py` dosyası kabul edilir.")
        return
    if user_file_count(uid) >= FREE_LIMIT and uid not in ADMIN_IDS:
        bot.reply_to(m, f"❌ Limit dolu ({FREE_LIMIT}). Önce dosya sil.")
        return
    if doc.file_size > 5 * 1024 * 1024:
        bot.reply_to(m, "❌ Maks 5MB.")
        return
    try:
        wm = bot.reply_to(m, f"📥 `{name}` indiriliyor...")
        fi = bot.get_file(doc.file_id)
        content = bot.download_file(fi.file_path)
        old = os.path.join(user_dir(uid), name)
        if os.path.exists(old):
            kill_bot(uid, name)
            os.remove(old)
        fp = os.path.join(user_dir(uid), name)
        with open(fp, 'wb') as f:
            f.write(content)
        try: bot.delete_message(m.chat.id, wm.message_id)
        except: pass
        new_approval(uid, name, fp, m)
    except Exception as e:
        logger.error(f"download: {e}")
        bot.reply_to(m, f"❌ İndirme hatası: {e}")

# ================== CALLBACK ==================
@bot.callback_query_handler(func=lambda c: True)
def on_cb(c):
    uid = c.from_user.id
    d = c.data

    if d.startswith('ap_') or d.startswith('rj_'):
        if uid not in ADMIN_IDS:
            bot.answer_callback_query(c.id, "Yetkin yok.", show_alert=True)
            return
        try: aid = int(d.split('_', 1)[1])
        except:
            bot.answer_callback_query(c.id, "Geçersiz.")
            return
        if d.startswith('ap_'):
            info, result = approve(aid)
        else:
            info, result = reject(aid)
        bot.answer_callback_query(c.id, result, show_alert=True)
        try:
            bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
            if info and c.message.caption:
                bot.edit_message_caption(f"{c.message.caption}\n\n{result}"[:1024],
                                         c.message.chat.id, c.message.message_id)
        except: pass
        return

    if d == 'upload':
        bot.answer_callback_query(c.id)
        cnt = user_file_count(uid)
        bot.send_message(c.message.chat.id, f"📤 `.py` gönder.\n\n📁 `{cnt}/{FREE_LIMIT}`")

    elif d == 'files':
        bot.answer_callback_query(c.id)
        files = get_files(uid)
        if not files:
            bot.send_message(c.message.chat.id, "📂 Henüz dosya yok.")
            return
        kb = types.InlineKeyboardMarkup(row_width=1)
        for (name,) in files:
            icon = "🟢" if is_running(uid, name) else "🔴"
            kb.add(types.InlineKeyboardButton(f"{icon} {name}", callback_data=f"fi_{uid}_{name}"))
        kb.add(types.InlineKeyboardButton("🔙 Ana Menü", callback_data="back"))
        try:
            bot.edit_message_text("📂 **Dosyaların:**", c.message.chat.id,
                                 c.message.message_id, reply_markup=kb)
        except:
            bot.send_message(c.message.chat.id, "📂 **Dosyaların:**", reply_markup=kb)

    elif d.startswith('fi_'):
        try:
            _, oid, name = d.split('_', 2)
            oid = int(oid)
            if oid != uid and uid not in ADMIN_IDS:
                bot.answer_callback_query(c.id, "Yetkin yok.", show_alert=True); return
            bot.answer_callback_query(c.id)
            status = "🟢 Çalışıyor" if is_running(oid, name) else "🔴 Durdu"
            txt = f"📄 **{name}**\n👤 `{oid}`\n📊 {status}"
            try:
                bot.edit_message_text(txt, c.message.chat.id, c.message.message_id,
                                     reply_markup=file_menu(oid, name, uid))
            except: pass
        except Exception as e: logger.error(f"fi_: {e}")

    elif d.startswith('go_'):
        try:
            _, oid, name = d.split('_', 2)
            oid = int(oid)
            if oid != uid and uid not in ADMIN_IDS:
                bot.answer_callback_query(c.id, "Yetkin yok.", show_alert=True); return
            if not is_approved(oid, name):
                bot.answer_callback_query(c.id, "Onaysız çalıştırılamaz.", show_alert=True); return
            bot.answer_callback_query(c.id, "Başlatılıyor...")
            threading.Thread(target=start_bot, args=(oid, name, c.message.chat.id), daemon=True).start()
            time.sleep(1)
            try:
                bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id,
                                             reply_markup=file_menu(oid, name, uid))
            except: pass
        except Exception as e: logger.error(f"go_: {e}")

    elif d.startswith('st_'):
        try:
            _, oid, name = d.split('_', 2)
            oid = int(oid)
            if oid != uid and uid not in ADMIN_IDS:
                bot.answer_callback_query(c.id, "Yetkin yok.", show_alert=True); return
            kill_bot(oid, name)
            bot.answer_callback_query(c.id, "Durduruldu.")
            try:
                bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id,
                                             reply_markup=file_menu(oid, name, uid))
            except: pass
        except Exception as e: logger.error(f"st_: {e}")

    elif d.startswith('rs_'):
        try:
            _, oid, name = d.split('_', 2)
            oid = int(oid)
            if oid != uid and uid not in ADMIN_IDS:
                bot.answer_callback_query(c.id, "Yetkin yok.", show_alert=True); return
            if not is_approved(oid, name):
                bot.answer_callback_query(c.id, "Onaysız çalıştırılamaz.", show_alert=True); return
            bot.answer_callback_query(c.id, "Yeniden...")
            kill_bot(oid, name)
            time.sleep(0.5)
            threading.Thread(target=start_bot, args=(oid, name, c.message.chat.id), daemon=True).start()
            time.sleep(1)
            try:
                bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id,
                                             reply_markup=file_menu(oid, name, uid))
            except: pass
        except Exception as e: logger.error(f"rs_: {e}")

    elif d.startswith('lg_'):
        try:
            _, oid, name = d.split('_', 2)
            oid = int(oid)
            if oid != uid and uid not in ADMIN_IDS:
                bot.answer_callback_query(c.id, "Yetkin yok.", show_alert=True); return
            lp = os.path.join(user_dir(oid), f"{os.path.splitext(name)[0]}.log")
            if not os.path.exists(lp):
                bot.answer_callback_query(c.id, "Log yok.", show_alert=True); return
            bot.answer_callback_query(c.id)
            with open(lp, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            if not content.strip(): content = "(log boş)"
            if len(content) > 3500: content = "..." + content[-3500:]
            bot.send_message(c.message.chat.id, f"📜 `{name}`\n```\n{content}\n```")
        except Exception as e: logger.error(f"lg_: {e}")

    elif d.startswith('dl_'):
        try:
            _, oid, name = d.split('_', 2)
            oid = int(oid)
            if oid != uid and uid not in ADMIN_IDS:
                bot.answer_callback_query(c.id, "Yetkin yok.", show_alert=True); return
            kill_bot(oid, name)
            fp = os.path.join(user_dir(oid), name)
            lp = os.path.join(user_dir(oid), f"{os.path.splitext(name)[0]}.log")
            for p in [fp, lp]:
                if os.path.exists(p):
                    try: os.remove(p)
                    except: pass
            remove_file(oid, name)
            bot.answer_callback_query(c.id, "Silindi.")
            bot.edit_message_text(f"✅ `{name}` silindi.", c.message.chat.id, c.message.message_id)
        except Exception as e: logger.error(f"dl_: {e}")

    elif d == 'back':
        bot.answer_callback_query(c.id)
        cnt = user_file_count(uid)
        txt = f"🌟 **FREEBOTHOSTING** 🌟\n\n👤 `{uid}`\n📁 `{cnt}/{FREE_LIMIT}`"
        try:
            bot.edit_message_text(txt, c.message.chat.id, c.message.message_id,
                                 reply_markup=main_menu(uid))
        except: pass
    else:
        bot.answer_callback_query(c.id)

# ================== CLEANUP ==================
def cleanup():
    for sk in list(running.keys()):
        try:
            info = running.pop(sk, None)
            if info:
                info['proc'].terminate()
        except: pass

import atexit
atexit.register(cleanup)

if __name__ == '__main__':
    logger.warning("🚀 FreeBotHosting başladı")
    logger.warning(f"👑 Owner: {OWNER_ID}")
    logger.warning(f"🛡 Admin: {ADMIN_ID}")
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=60,
                                long_polling_timeout=30, logger_level=logging.ERROR)
        except Exception as e:
            logger.error(f"Polling: {e}")
            time.sleep(10)
