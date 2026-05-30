# -*- coding: utf-8 -*-
import re
import gzip
import sqlite3
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from bs4 import BeautifulSoup

app = FastAPI(title="TFlat Dictionary API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Config ──────────────────────────────────────────────
DB_PATH = Path("/Volumes/KINGSTON/tflat/assets/o_v3_extracted/av_v3.db")  # <-- đổi nếu cần

# ── TFlat parser ────────────────────────────────────────
FIX_TEXT_PATTERNS = {
    ' ':  re.compile(r'\s+'),
    '(':  re.compile(r'\(\s+'),
    ')':  re.compile(r'\s+\)'),
    ', ': re.compile(r'\s*,\s*'),
    ' + ':re.compile(r'\s*\+\s*'),
    '/':  re.compile(r'\s*\/\s*'),
}

def decode_mean(mean):
    """mean column lưu dạng UTF-16-LE bytes (hex có 00 xen kẽ)"""
    if isinstance(mean, bytes):
        try:
            return mean.decode('utf-16-le')
        except Exception:
            return mean.decode('utf-8', errors='replace')
    return mean

def decrypt_blob(blob):
    BLOB_KEY_A, BLOB_KEY_B = 2, 7
    org_length = len(blob)
    length = int(org_length / BLOB_KEY_A)
    tmp = [0] * org_length
    for x in range(0, length * 2, 2):
        if x > (BLOB_KEY_B * 2) + length:
            tmp[x] = blob[x]; tmp[x+1] = blob[x+1]
        else:
            tmp[x] = blob[x+1]; tmp[x+1] = blob[x]
    if org_length % 2 == 1:
        tmp[org_length-1] = blob[org_length-1]
    return str(gzip.decompress(bytearray(tmp)), 'utf8')

def fix_text(text):
    text = text.strip()
    for rpl, pat in FIX_TEXT_PATTERNS.items():
        text = pat.sub(rpl, text)
    return text

def restore_html(html_doc):
    return (html_doc
        .replace('<d1', '<div class="')
        .replace('<d3>', '</div></div></div>')
        .replace('<a1', '<a href="')
        .replace('<s1', '<span class="')
        .replace('<s2>', '</span></span>'))

def parse_tab_content(content, entry={}):
    if not content or len(content) <= 3:
        return entry
    if not content.startswith('<div'):
        content = fix_text(content)
        content = '<div><div class="m">{}</div></div>'.format(content)

    soup = BeautifulSoup(content, 'html.parser')
    root = soup.div
    for elm in root.find_all(['ul', 'li']):
        elm.unwrap()

    pronunciation = ''
    try:
        pronunciation = root.find('div', attrs={'class': 'p5l fl'}).string
    except Exception:
        w = root.find(attrs={'class': 'w'})
        if w:
            parent = w.parent
            w.decompose()
            pronunciation = parent.text

    if pronunciation and 'pronunciation' not in entry:
        pronunciation = pronunciation.strip()
        if pronunciation:
            entry['pronunciation'] = pronunciation

    try:
        body = root.find(attrs={'class': re.compile(r'^[meidub]{1,2}$')}).parent
    except Exception:
        return entry

    for elm_m in body.find_all(attrs={'class': 'm'}):
        tmp = []
        for elm in elm_m.find_all(attrs={'class': re.compile(r'^em?$')}):
            tmp.append(elm.extract())
        tmp.reverse()
        for t in tmp:
            elm_m.insert_after(t)

    parts = entry.get('parts', OrderedDict())
    if '_' not in parts:
        parts['_'] = {'meanings': OrderedDict(), 'phrases': OrderedDict()}

    cur_part, cur_meaning = '_', '_'
    cur_example = cur_example_meaning = cur_phrase = cur_phrase_meaning = ''

    for child in body.find_all(attrs={'class': re.compile(r'^[meidub]{1,2}$')}):
        if isinstance(child, str):
            continue
        text = fix_text(child.text)
        cls = child['class']
        if 'ub' in cls or 'b' in cls:
            cur_part = text.lower().strip()
            if cur_part not in parts:
                parts[cur_part] = {'meanings': OrderedDict(), 'phrases': OrderedDict()}
        elif 'm' in cls:
            cur_meaning = text
            parts[cur_part]['meanings'][cur_meaning] = OrderedDict()
        elif 'e' in cls:
            cur_example = text
        elif 'em' in cls:
            cur_example_meaning = text
            if cur_meaning not in parts[cur_part]['meanings']:
                parts[cur_part]['meanings'][cur_meaning] = OrderedDict()
            parts[cur_part]['meanings'][cur_meaning][cur_example] = cur_example_meaning
        elif 'id' in cls:
            cur_phrase = text
        elif 'im' in cls:
            cur_phrase_meaning = text
            parts[cur_part]['phrases'][cur_phrase] = cur_phrase_meaning

    entry['parts'] = parts
    return entry

def parse_row(row):
    word, blob, mean = row
    mean = decode_mean(mean)  # fix UTF-16
    if mean.startswith('@') or mean.startswith('(xem)'):
        return None
    if len(blob) == 0:
        return None
    if len(blob) > 3 and blob[0] == blob[1] == blob[2]:
        data = decrypt_blob(blob[3:])
    else:
        data = str(blob, 'utf8')
    data = restore_html(data)
    tab_contents = data.split('##')
    entry = parse_tab_content(tab_contents[0], {})
    if entry and len(tab_contents) > 2:
        entry = parse_tab_content(tab_contents[2], entry)
    return entry

# ── Inflections map ──────────────────────────────────────
INFLECTIONS_MAP: dict = {}

def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db

@app.on_event("startup")
def load_inflections():
    global INFLECTIONS_MAP
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT word, mean FROM av")
    rows = cursor.fetchall()
    count = 0
    for row in rows:
        variant = row["word"]
        mean = decode_mean(row["mean"])  # fix UTF-16
        if mean.startswith("(xem)"):
            root = mean[5:]
        elif mean.startswith("@"):
            root = mean[1:]
        else:
            continue
        root = root.strip().rstrip("#").replace("_", " ")
        if root:
            INFLECTIONS_MAP[variant.lower()] = root
            count += 1
    db.close()
    print(f"✅ Loaded {count} inflections")

# ── API Routes ───────────────────────────────────────────

@app.get("/api/search")
def search(q: str = Query(..., min_length=1), limit: int = 10):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT word FROM av WHERE word LIKE ? ORDER BY length(word) LIMIT ?",
        (f"{q}%", limit)
    )
    words = [r["word"] for r in cursor.fetchall()]

    if len(words) < limit:
        cursor.execute(
            "SELECT word FROM av WHERE word LIKE ? AND word NOT LIKE ? ORDER BY length(word) LIMIT ?",
            (f"%{q}%", f"{q}%", limit - len(words))
        )
        words += [r["word"] for r in cursor.fetchall()]

    db.close()
    return {"words": words}

@app.get("/api/word/{word}")
def get_word(word: str):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT word, av, mean FROM av WHERE word = ? COLLATE NOCASE LIMIT 1", (word,))
    row = cursor.fetchone()

    root_word = None

    # Trường hợp 1: không tìm thấy trong DB -> tra inflections
    if not row:
        root_word = INFLECTIONS_MAP.get(word.lower())
        if root_word:
            cursor.execute("SELECT word, av, mean FROM av WHERE word = ? COLLATE NOCASE LIMIT 1", (root_word,))
            row = cursor.fetchone()

    if not row:
        db.close()
        return JSONResponse(status_code=404, content={"error": "Không tìm thấy từ"})

    entry = parse_row((row["word"], row["av"], row["mean"]))

    # Trường hợp 2: row tìm thấy nhưng là inflection (mean = "@...")
    # parse_row trả None -> fallback sang từ gốc
    if not entry:
        root_word = INFLECTIONS_MAP.get(word.lower())
        if root_word:
            cursor.execute("SELECT word, av, mean FROM av WHERE word = ? COLLATE NOCASE LIMIT 1", (root_word,))
            root_row = cursor.fetchone()
            if root_row:
                entry = parse_row((root_row["word"], root_row["av"], root_row["mean"]))
                row = root_row

    db.close()

    if not entry:
        return JSONResponse(status_code=404, content={"error": "Không có dữ liệu"})

    if root_word:
        entry["_note"] = f'"{word}" là dạng biến thể của "{row["word"]}"'

    return {"word": row["word"], "entry": entry}

@app.get("/api/random")
def random_word():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT word, av, mean FROM av WHERE length(av) > 5 ORDER BY RANDOM() LIMIT 1")
    row = cursor.fetchone()
    db.close()
    if not row:
        return JSONResponse(status_code=404, content={"error": "Lỗi"})
    entry = parse_row((row["word"], row["av"], row["mean"]))
    return {"word": row["word"], "entry": entry}

@app.get("/", response_class=HTMLResponse)
def index():
    html_path = Path("index.html")
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>Thiếu file index.html</h1>"

@app.get("/style.css")
def get_style():
    return FileResponse("style.css")

@app.get("/favicon.ico")
def get_favicon():
    return FileResponse("favicon.ico")

