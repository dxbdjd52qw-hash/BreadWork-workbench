# -*- coding: utf-8 -*-
"""
麺包的工作台 · 后端服务 (FastAPI + SQLite + DeepSeek AI)
接口契约：需求规格大纲 v2 第四章 / 交接文档 4.3 节
运行：uvicorn main:app --host 0.0.0.0 --port 8000
"""
import json
import os
import sqlite3
import time
import uuid
import hashlib
import hmac
from contextlib import contextmanager
from typing import Any, Optional

import httpx
import jwt  # PyJWT
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

load_dotenv()

# ---------------- 配置（全部来自 .env，绝不硬编码密钥） ----------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-chat")
API_KEY = os.getenv("API_KEY", "")          # 前端「配置接口」里填的共享密钥
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-.env")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
DB_PATH = os.getenv("DB_PATH", "ytwb.db")
ACCESS_TTL = 7 * 24 * 3600
REFRESH_TTL = 30 * 24 * 3600

ALLOWED_COLLECTIONS = {
    "todos", "courses", "wordBooks", "wordLogs", "progress",
    "mistakes", "notes", "ddls", "chatSessions", "meta",
}

# ---------------- 数据库 ----------------

def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS records(
            collection TEXT NOT NULL,
            id TEXT NOT NULL,
            data TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY(collection, id)
        );
        CREATE TABLE IF NOT EXISTS books(
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS words(
            id TEXT PRIMARY KEY,
            book_id TEXT NOT NULL,
            word TEXT NOT NULL,
            meaning TEXT DEFAULT '',
            data TEXT DEFAULT '{}',
            status INTEGER DEFAULT 0,
            review_count INTEGER DEFAULT 0,
            updated_at REAL NOT NULL,
            UNIQUE(book_id, word)
        );
        """)

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

# ---------------- 鉴权 ----------------

def _hash_password(pwd: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt.encode(), 100_000).hex()

def make_token(ttl: int, kind: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": ADMIN_USER, "kind": kind, "iat": now, "exp": now + ttl},
        JWT_SECRET, algorithm="HS256",
    )

def check_auth(authorization: Optional[str]):
    """支持两种凭证：Bearer <API_KEY>（前端配置接口的 apiKey）或 Bearer <JWT>。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.split(None, 1)[1].strip()
    if API_KEY and hmac.compare_digest(token, API_KEY):
        return {"user": ADMIN_USER}
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return {"user": payload.get("sub", ADMIN_USER)}
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid token")

def auth(authorization: Optional[str] = Header(None)):
    return check_auth(authorization)

# ---------------- 应用 ----------------
app = FastAPI(title="麺包的工作台 API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)

@app.on_event("startup")
def _startup():
    init_db()

# ---------------- 系统 ----------------
@app.get("/api/health")
def health():
    return {"status": "ok", "time": time.time()}

@app.get("/api/config")
def config():
    return {
        "aiEnabled": bool(DEEPSEEK_API_KEY),
        "modelName": MODEL_NAME,
        "syncMode": "custom",
    }

# ---------------- 认证 ----------------
class LoginBody(BaseModel):
    username: str
    password: str

@app.post("/api/auth/login")
def login(body: LoginBody):
    if not ADMIN_PASSWORD:
        raise HTTPException(500, "server admin password not configured")
    if body.username != ADMIN_USER or body.password != ADMIN_PASSWORD:
        raise HTTPException(401, "用户名或密码错误")
    return {
        "accessToken": make_token(ACCESS_TTL, "access"),
        "refreshToken": make_token(REFRESH_TTL, "refresh"),
        "user": {"username": ADMIN_USER},
    }

class RefreshBody(BaseModel):
    refreshToken: str

@app.post("/api/auth/refresh")
def refresh(body: RefreshBody):
    try:
        payload = jwt.decode(body.refreshToken, JWT_SECRET, algorithms=["HS256"])
        if payload.get("kind") != "refresh":
            raise ValueError
    except Exception:
        raise HTTPException(401, "invalid refresh token")
    return {
        "accessToken": make_token(ACCESS_TTL, "access"),
        "refreshToken": make_token(REFRESH_TTL, "refresh"),
    }

@app.get("/api/me")
def me(user=Depends(auth)):
    return {"username": user["user"]}

# ---------------- 数据集合 ----------------
def _check_collection(col: str):
    if col not in ALLOWED_COLLECTIONS:
        raise HTTPException(404, f"unknown collection: {col}")

def _to_ms(v) -> float:
    """updatedAt 可能是毫秒时间戳或 ISO 字符串（前端 Store 用 ISO 格式）。"""
    if v is None:
        return time.time() * 1000
    try:
        return float(v)
    except (TypeError, ValueError):
        pass
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp() * 1000
    except Exception:
        return time.time() * 1000

def upsert_records(col: str, items: list) -> int:
    n = 0
    with db() as conn:
        for it in items:
            rid = str(it.get("id") or uuid.uuid4())
            it["id"] = rid
            ua = _to_ms(it.get("updatedAt"))
            if "updatedAt" not in it:
                it["updatedAt"] = ua  # 仅在缺失时补，保留前端原始格式
            row = conn.execute(
                "SELECT updated_at FROM records WHERE collection=? AND id=?",
                (col, rid)).fetchone()
            if row is None or ua >= row["updated_at"]:   # updatedAt 新者胜
                conn.execute(
                    "INSERT OR REPLACE INTO records(collection,id,data,updated_at)"
                    " VALUES(?,?,?,?)", (col, rid, json.dumps(it, ensure_ascii=False), ua))
                n += 1
    return n

# 注意：sync / snapshot 必须注册在 /api/data/{col} 之前，否则会被 {col} 抢走
class SyncBody(BaseModel):
    collections: dict = {}
    lastSyncAt: Optional[float] = None

@app.post("/api/data/sync")
def sync(body: SyncBody, user=Depends(auth)):
    for col, items in (body.collections or {}).items():
        _check_collection(col)
        if isinstance(items, list) and items:
            upsert_records(col, items)
    out = {}
    with db() as conn:
        for col in ALLOWED_COLLECTIONS:
            rows = conn.execute(
                "SELECT data FROM records WHERE collection=?", (col,)).fetchall()
            out[col] = [json.loads(r["data"]) for r in rows]
    return {"collections": out, "serverTime": time.time() * 1000}

@app.get("/api/data/snapshot")
def snapshot(user=Depends(auth)):
    with db() as conn:
        out = {}
        for col in ALLOWED_COLLECTIONS:
            rows = conn.execute(
                "SELECT data FROM records WHERE collection=?", (col,)).fetchall()
            out[col] = [json.loads(r["data"]) for r in rows]
    return {"collections": out, "exportedAt": time.time() * 1000}

@app.get("/api/data/{col}")
def list_records(col: str, user=Depends(auth)):
    _check_collection(col)
    with db() as conn:
        rows = conn.execute(
            "SELECT data FROM records WHERE collection=? ORDER BY updated_at DESC",
            (col,)).fetchall()
    return {"items": [json.loads(r["data"]) for r in rows]}

@app.post("/api/data/{col}")
async def create_records(col: str, request: Request, user=Depends(auth)):
    _check_collection(col)
    body = await request.json()
    items = body if isinstance(body, list) else body.get("items", [body])
    n = upsert_records(col, items)
    return {"ok": True, "count": n}

@app.put("/api/data/{col}/{rid}")
async def put_record(col: str, rid: str, request: Request, user=Depends(auth)):
    _check_collection(col)
    body = await request.json()
    body["id"] = rid
    upsert_records(col, [body])
    return {"ok": True}

@app.delete("/api/data/{col}/{rid}")
def delete_record(col: str, rid: str, user=Depends(auth)):
    _check_collection(col)
    with db() as conn:
        conn.execute("DELETE FROM records WHERE collection=? AND id=?", (col, rid))
    return {"ok": True}

# ---------------- 单词 ----------------
class ImportBody(BaseModel):
    bookName: str
    words: list

@app.post("/api/words/import")
def import_words(body: ImportBody, user=Depends(auth)):
    book_id = uuid.uuid4().hex[:12]
    now = time.time() * 1000
    added = 0
    with db() as conn:
        conn.execute("INSERT INTO books(id,name,created_at) VALUES(?,?,?)",
                     (book_id, body.bookName, now))
        for w in body.words:
            word = (w.get("word") or "").strip()
            if not word:
                continue
            try:
                conn.execute(
                    "INSERT INTO words(id,book_id,word,meaning,data,updated_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (uuid.uuid4().hex[:12], book_id, word,
                     w.get("meaning", ""), json.dumps(w, ensure_ascii=False), now))
                added += 1
            except sqlite3.IntegrityError:
                pass  # 同书同词去重
    return {"bookId": book_id, "imported": added, "skipped": len(body.words) - added}

@app.get("/api/words/books")
def word_books(user=Depends(auth)):
    with db() as conn:
        rows = conn.execute("""
            SELECT b.id, b.name, b.created_at, COUNT(w.id) AS total,
                   SUM(CASE WHEN w.status=1 THEN 1 ELSE 0 END) AS done
            FROM books b LEFT JOIN words w ON w.book_id=b.id
            GROUP BY b.id ORDER BY b.created_at DESC""").fetchall()
    return {"books": [dict(r) for r in rows]}

@app.get("/api/words/books/{book_id}/words")
def book_words(book_id: str, user=Depends(auth)):
    with db() as conn:
        rows = conn.execute(
            "SELECT id, word, meaning, status, review_count, data FROM words"
            " WHERE book_id=? ORDER BY rowid", (book_id,)).fetchall()
    return {"words": [dict(r) for r in rows]}

class ReciteBody(BaseModel):
    wordId: str
    remembered: bool = True

@app.put("/api/words/recite")
def recite(body: ReciteBody, user=Depends(auth)):
    now = time.time() * 1000
    with db() as conn:
        conn.execute(
            "UPDATE words SET status=?, review_count=review_count+1, updated_at=?"
            " WHERE id=?", (1 if body.remembered else 0, now, body.wordId))
        conn.execute(
            "INSERT OR REPLACE INTO records(collection,id,data,updated_at) VALUES(?,?,?,?)",
            ("wordLogs", uuid.uuid4().hex[:12],
             json.dumps({"wordId": body.wordId, "remembered": body.remembered,
                         "ts": now, "updatedAt": now}, ensure_ascii=False), now))
    return {"ok": True}

# ---------------- AI（DeepSeek，OpenAI 兼容） ----------------
SYSTEM_PROMPT = (
    "你是「麺包的工作台」的内置学习助手，服务对象是一名考研学生。"
    "回答务实、简洁、可执行，多给具体做法而非空话。"
)

async def _deepseek_stream(messages):
    """向上游 DeepSeek 请求流式输出，逐行转发 OpenAI 兼容 chunk。"""
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
    payload = {"model": MODEL_NAME, "messages": messages, "stream": True}
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST", f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers=headers, json=payload) as resp:
            if resp.status_code != 200:
                text = await resp.aread()
                yield f"data: {json.dumps({'error': text.decode()[:300]})}\n\n"
                yield "data: [DONE]\n\n"
                return
            async for line in resp.aiter_lines():
                if line:
                    yield line + "\n\n" if line.startswith("data:") else f"{line}\n"
        yield "data: [DONE]\n\n"

class ChatBody(BaseModel):
    sessionId: Optional[str] = None
    messages: list
    context: Optional[Any] = None  # 前端 buildContext() 可能给 dict 或 JSON 字符串

@app.post("/api/ai/chat")
async def ai_chat(body: ChatBody, user=Depends(auth)):
    if not DEEPSEEK_API_KEY:
        raise HTTPException(500, "DEEPSEEK_API_KEY 未配置")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if body.context:
        ctx = body.context if isinstance(body.context, str) \
            else json.dumps(body.context, ensure_ascii=False)
        messages.append({"role": "system", "content":
            "以下是用户当前的备考数据快照（JSON）：\n" + ctx})
    messages += body.messages
    return StreamingResponse(_deepseek_stream(messages),
                             media_type="text/event-stream")

async def _deepseek_once(prompt: str) -> str:
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
    payload = {"model": MODEL_NAME, "stream": False, "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{DEEPSEEK_BASE_URL}/chat/completions",
                                 headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

class SimpleAIBody(BaseModel):
    prompt: str = ""
    payload: Optional[dict] = None

def _merge_prompt(body: SimpleAIBody) -> str:
    p = body.prompt
    if body.payload:
        p += "\n\n相关数据：\n" + json.dumps(body.payload, ensure_ascii=False)
    return p

@app.post("/api/ai/analyze")
async def ai_analyze(body: SimpleAIBody, user=Depends(auth)):
    return {"text": await _deepseek_once("请对以下内容做分析并给出建议：\n" + _merge_prompt(body))}

@app.post("/api/ai/plan")
async def ai_plan(body: SimpleAIBody, user=Depends(auth)):
    return {"text": await _deepseek_once("请基于以下情况制定可执行的学习计划：\n" + _merge_prompt(body))}

@app.post("/api/ai/review")
async def ai_review(body: SimpleAIBody, user=Depends(auth)):
    return {"text": await _deepseek_once("请根据以下素材生成一篇复盘笔记草稿：\n" + _merge_prompt(body))}

@app.get("/api/ai/sessions")
def ai_sessions(user=Depends(auth)):
    with db() as conn:
        rows = conn.execute(
            "SELECT data FROM records WHERE collection='chatSessions'"
            " ORDER BY updated_at DESC").fetchall()
    return {"sessions": [json.loads(r["data"]) for r in rows]}

@app.exception_handler(Exception)
async def on_error(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return JSONResponse({"detail": str(exc)}, status_code=500)

# ---------------- 静态托管前端（放在所有 API 路由之后） ----------------
# 手机/电脑浏览器直接访问 http://IP:8000/ 即可打开工作台，与 API 同源
import os as _os
from fastapi.staticfiles import StaticFiles
_static_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "static")
if _os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
