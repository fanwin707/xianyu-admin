from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import sqlite3, os, json
from datetime import datetime, timedelta
import random, string

app = FastAPI(title="闲鱼AI服务自动化交付平台")
app.add_middleware(SessionMiddleware, secret_key="xianyu-demo-secret-2026")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TMPL_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TMPL_DIR)

DB = os.path.join(BASE_DIR, "demo.db")

# ─── 数据库初始化 ─────────────────────────────────────────────
def init_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT UNIQUE,
        buyer TEXT,
        product TEXT,
        amount REAL,
        status TEXT DEFAULT 'delivered',
        token TEXT,
        created_at TEXT,
        delivered_at TEXT
    );
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token TEXT UNIQUE,
        product TEXT,
        status TEXT DEFAULT 'unused',
        expire_date TEXT,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS replies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keywords TEXT,
        reply TEXT,
        enabled INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT,
        message TEXT,
        created_at TEXT
    );
    """)
    # 填充演示数据
    if cur.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0:
        sample_orders = []
        products = ["Claude API Token 100K", "GPT-4 API Token 50K", "通用AI Token包月"]
        buyers = ["用户_张**", "用户_李**", "用户_王**", "用户_赵**", "用户_陈**"]
        amounts = [29.9, 49.9, 99.0, 19.9, 39.9]
        for i in range(30):
            dt = datetime.now() - timedelta(hours=random.randint(1, 720))
            oid = "XY" + dt.strftime("%Y%m%d") + str(random.randint(10000,99999))
            tok = "sk-" + ''.join(random.choices(string.ascii_letters+string.digits, k=32))
            sample_orders.append((
                oid, random.choice(buyers), random.choice(products),
                random.choice(amounts), "delivered", tok,
                dt.strftime("%Y-%m-%d %H:%M:%S"),
                (dt + timedelta(seconds=random.randint(8,28))).strftime("%Y-%m-%d %H:%M:%S")
            ))
        cur.executemany("INSERT OR IGNORE INTO orders(order_id,buyer,product,amount,status,token,created_at,delivered_at) VALUES(?,?,?,?,?,?,?,?)", sample_orders)

    if cur.execute("SELECT COUNT(*) FROM inventory").fetchone()[0] == 0:
        tokens = []
        for _ in range(85):
            tok = "sk-" + ''.join(random.choices(string.ascii_letters+string.digits, k=32))
            exp = (datetime.now() + timedelta(days=random.randint(10,90))).strftime("%Y-%m-%d")
            prod = random.choice(["Claude API Token 100K", "GPT-4 API Token 50K", "通用AI Token包月"])
            tokens.append((tok, prod, "unused", exp, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        cur.executemany("INSERT OR IGNORE INTO inventory(token,product,status,expire_date,created_at) VALUES(?,?,?,?,?)", tokens)

    if cur.execute("SELECT COUNT(*) FROM replies").fetchone()[0] == 0:
        default_replies = [
            ("发货|什么时候|多久", "您好！付款成功后系统将在30秒内自动发货，请查收站内消息～", 1),
            ("怎么用|使用方法|教程", "将收到的Token填入AI平台的API Key栏即可使用，如需帮助请联系客服。", 1),
            ("退款|不想要|取消", "您好，虚拟商品发货后不支持退款，如有质量问题请截图联系我们。", 1),
            ("失效|无效|用不了", "您好，请提供问题截图，我们24小时内核实后补发或退款。", 1),
            ("谢谢|感谢|好评", "感谢您的支持！如果满意请给我们五星好评，期待下次为您服务～", 1),
        ]
        cur.executemany("INSERT INTO replies(keywords,reply,enabled) VALUES(?,?,?)", default_replies)

    if cur.execute("SELECT COUNT(*) FROM logs").fetchone()[0] == 0:
        log_msgs = [
            ("INFO",  "系统启动，开始监听闲鱼订单"),
            ("INFO",  "订单 XY202605310001 检测到，已付款，开始发货"),
            ("INFO",  "Token发送成功 → 用户_张**，耗时 12秒"),
            ("INFO",  "订单 XY202605310002 检测到，已付款，开始发货"),
            ("INFO",  "Token发送成功 → 用户_李**，耗时 9秒"),
            ("WARN",  "库存剩余 85 个，低于预警值 100，请及时补货"),
            ("INFO",  "自动回复触发：关键词「怎么用」→ 用户_王**"),
            ("INFO",  "今日累计处理订单 12 笔，成功率 100%"),
            ("ERROR", "API调用失败（网络超时），已自动重试，第2次成功"),
            ("INFO",  "系统运行正常，下次轮询：30秒后"),
        ]
        for level, msg in log_msgs:
            dt = (datetime.now() - timedelta(minutes=random.randint(1,120))).strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("INSERT INTO logs(level,message,created_at) VALUES(?,?,?)", (level, msg, dt))

    con.commit()
    con.close()

init_db()

# ─── 认证工具 ─────────────────────────────────────────────────
USERS = {"admin": "demo2026", "test": "test123"}

def current_user(request: Request):
    return request.session.get("user")

def require_login(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user

def db():
    return sqlite3.connect(DB)

# ─── 路由 ─────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    # OAuth 回调落点：不跳转，让 JS 读取 URL fragment 中的 access_token
    return HTMLResponse("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>OAuth 回调</title>
<style>
body{font-family:'Microsoft YaHei',sans-serif;background:#f5f6fa;display:flex;align-items:center;
     justify-content:center;min-height:100vh;margin:0;}
.box{background:#fff;border-radius:16px;padding:40px;max-width:600px;width:90%;
     box-shadow:0 4px 20px rgba(0,0,0,.1);}
h2{color:#ff6900;margin-top:0;}
.token-box{background:#1a1a2e;color:#52c41a;padding:16px;border-radius:10px;
           font-family:monospace;font-size:13px;word-break:break-all;margin:16px 0;}
.tip{font-size:13px;color:#888;margin-top:16px;}
.btn{display:inline-block;margin-top:16px;padding:10px 24px;background:#ff6900;
     color:#fff;border-radius:8px;text-decoration:none;font-weight:600;}
#no-token{display:none;color:#f5222d;}
</style></head>
<body><div class="box">
  <h2>🔑 OAuth 授权成功</h2>
  <p>已捕获您的 Access Token，请复制下方内容发给 Claude：</p>
  <div class="token-box" id="token-display">正在读取...</div>
  <p id="no-token">⚠️ 未检测到 Token，请重新授权。</p>
  <div class="tip">复制以上 Token 后发送给 Claude，机器人即可启动。</div>
  <a href="/dashboard" class="btn">进入管理后台</a>
</div>
<script>
const hash = window.location.hash.substring(1);
const params = Object.fromEntries(new URLSearchParams(hash));
const el = document.getElementById('token-display');
if (params.access_token) {
  el.textContent = 'ACCESS_TOKEN=' + params.access_token;
  if (params.r_token) {
    el.textContent += '\\nR_TOKEN=' + params.r_token;
  }
  if (params.expires_in) {
    el.textContent += '\\n有效期（秒）=' + params.expires_in;
  }
} else {
  el.style.display = 'none';
  document.getElementById('no-token').style.display = 'block';
}
</script>
</body></html>""")


@app.get("/go", response_class=HTMLResponse)
async def go(request: Request):
    if not current_user(request):
        return RedirectResponse("/login", status_code=302)
    return RedirectResponse("/dashboard", status_code=302)

@app.get("/oauth", response_class=HTMLResponse)
async def oauth_callback(request: Request):
    """OAuth 专用回调页，无需登录，JS 捕获 URL fragment 中的 access_token"""
    return HTMLResponse("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>授权成功 · 获取Token</title>
<style>
*{box-sizing:border-box}
body{font-family:'Microsoft YaHei',sans-serif;background:#f0f2f5;
     display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}
.card{background:#fff;border-radius:16px;padding:40px 36px;max-width:640px;width:92%;
      box-shadow:0 8px 32px rgba(0,0,0,.1);}
h2{margin:0 0 8px;color:#ff6900;font-size:22px;}
.sub{color:#888;font-size:14px;margin-bottom:24px;}
.label{font-size:13px;font-weight:600;color:#444;margin-bottom:8px;}
.token-box{background:#0d1117;color:#7ee787;padding:18px 16px;border-radius:10px;
           font-family:'Courier New',monospace;font-size:13px;word-break:break-all;
           line-height:1.8;margin-bottom:12px;position:relative;}
.copy-btn{position:absolute;top:12px;right:12px;background:#ff6900;color:#fff;
          border:none;border-radius:6px;padding:4px 12px;font-size:12px;
          cursor:pointer;font-family:inherit;}
.copy-btn:hover{opacity:.85}
.tip{font-size:13px;color:#666;background:#fff8f0;border-left:3px solid #ff6900;
     padding:12px 14px;border-radius:6px;margin-top:16px;}
.err{color:#f5222d;font-weight:600;}
</style></head>
<body>
<div class="card">
  <h2>🔑 授权成功！</h2>
  <p class="sub">请复制下方 Access Token 发送给 Claude</p>
  <div class="label">您的 Access Token：</div>
  <div class="token-box" id="box">
    <span id="token-text">检测中...</span>
    <button class="copy-btn" onclick="copyToken()">复制</button>
  </div>
  <p id="err" class="err" style="display:none">⚠️ 未检测到 Token，请重新授权。</p>
  <div class="tip">✅ 将上方 Token 完整复制后粘贴给 Claude，机器人即可正式启动。</div>
</div>
<script>
const hash = window.location.hash.replace(/^#/,'');
const p = Object.fromEntries(new URLSearchParams(hash));
const el = document.getElementById('token-text');
if (p.access_token) {
  el.textContent = p.access_token;
} else {
  el.style.display = 'none';
  document.getElementById('err').style.display = 'block';
}
function copyToken(){
  const t = document.getElementById('token-text').textContent;
  navigator.clipboard.writeText(t).then(()=>{
    const btn = document.querySelector('.copy-btn');
    btn.textContent='已复制✓'; btn.style.background='#52c41a';
    setTimeout(()=>{btn.textContent='复制';btn.style.background='#ff6900';},2000);
  });
}
</script>
</body></html>""")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": ""})

@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    if USERS.get(username) == password:
        request.session["user"] = username
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": "账号或密码错误"})

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    con = db()
    cur = con.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    stats = {
        "today_orders":   cur.execute("SELECT COUNT(*) FROM orders WHERE created_at LIKE ?", (today+"%",)).fetchone()[0],
        "today_revenue":  cur.execute("SELECT COALESCE(SUM(amount),0) FROM orders WHERE created_at LIKE ?", (today+"%",)).fetchone()[0],
        "total_orders":   cur.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "total_revenue":  cur.execute("SELECT COALESCE(SUM(amount),0) FROM orders").fetchone()[0],
        "inventory":      cur.execute("SELECT COUNT(*) FROM inventory WHERE status='unused'").fetchone()[0],
        "success_rate":   99.7,
    }
    # 近7天销售数据（for chart）
    chart_labels, chart_data = [], []
    for i in range(6, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        cnt = cur.execute("SELECT COUNT(*) FROM orders WHERE created_at LIKE ?", (d+"%",)).fetchone()[0]
        chart_labels.append(d[5:])  # MM-DD
        chart_data.append(cnt if cnt > 0 else random.randint(2, 8))
    recent = cur.execute("SELECT order_id,buyer,product,amount,status,delivered_at FROM orders ORDER BY id DESC LIMIT 8").fetchall()
    con.close()
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user, "stats": stats,
        "chart_labels": json.dumps(chart_labels, ensure_ascii=False),
        "chart_data": json.dumps(chart_data),
        "recent_orders": recent,
        "active": "dashboard"
    })

@app.get("/orders", response_class=HTMLResponse)
async def orders(request: Request, status: str = "all", page: int = 1):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    con = db()
    cur = con.cursor()
    per_page = 15
    offset = (page - 1) * per_page
    if status == "all":
        rows = cur.execute("SELECT order_id,buyer,product,amount,status,created_at,delivered_at FROM orders ORDER BY id DESC LIMIT ? OFFSET ?", (per_page, offset)).fetchall()
        total = cur.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    else:
        rows = cur.execute("SELECT order_id,buyer,product,amount,status,created_at,delivered_at FROM orders WHERE status=? ORDER BY id DESC LIMIT ? OFFSET ?", (status, per_page, offset)).fetchall()
        total = cur.execute("SELECT COUNT(*) FROM orders WHERE status=?", (status,)).fetchone()[0]
    con.close()
    total_pages = max(1, (total + per_page - 1) // per_page)
    return templates.TemplateResponse("orders.html", {
        "request": request, "user": user, "orders": rows,
        "status": status, "page": page, "total_pages": total_pages, "total": total,
        "active": "orders"
    })

@app.get("/inventory", response_class=HTMLResponse)
async def inventory(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    con = db()
    cur = con.cursor()
    rows = cur.execute("SELECT id,token,product,status,expire_date,created_at FROM inventory ORDER BY id DESC LIMIT 50").fetchall()
    counts = {
        "unused":  cur.execute("SELECT COUNT(*) FROM inventory WHERE status='unused'").fetchone()[0],
        "sold":    cur.execute("SELECT COUNT(*) FROM inventory WHERE status='sold'").fetchone()[0],
        "expired": cur.execute("SELECT COUNT(*) FROM inventory WHERE status='expired'").fetchone()[0],
    }
    con.close()
    return templates.TemplateResponse("inventory.html", {
        "request": request, "user": user, "tokens": rows, "counts": counts,
        "active": "inventory"
    })

@app.post("/inventory/add")
async def add_tokens(request: Request, tokens_text: str = Form(...), product: str = Form(...), expire_date: str = Form(...)):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    lines = [l.strip() for l in tokens_text.strip().splitlines() if l.strip()]
    con = db()
    cur = con.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    added = 0
    for tok in lines:
        try:
            cur.execute("INSERT INTO inventory(token,product,status,expire_date,created_at) VALUES(?,?,?,?,?)",
                        (tok, product, "unused", expire_date, now))
            added += 1
        except:
            pass
    con.commit()
    con.close()
    return RedirectResponse(f"/inventory?added={added}", status_code=302)

@app.get("/replies", response_class=HTMLResponse)
async def replies(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    con = db()
    rows = con.execute("SELECT id,keywords,reply,enabled FROM replies ORDER BY id").fetchall()
    con.close()
    return templates.TemplateResponse("replies.html", {
        "request": request, "user": user, "replies": rows, "active": "replies"
    })

@app.post("/replies/add")
async def add_reply(request: Request, keywords: str = Form(...), reply: str = Form(...)):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    con = db()
    con.execute("INSERT INTO replies(keywords,reply,enabled) VALUES(?,?,1)", (keywords, reply))
    con.commit()
    con.close()
    return RedirectResponse("/replies", status_code=302)

@app.post("/replies/delete/{rid}")
async def delete_reply(rid: int, request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    con = db()
    con.execute("DELETE FROM replies WHERE id=?", (rid,))
    con.commit()
    con.close()
    return RedirectResponse("/replies", status_code=302)

@app.get("/logs", response_class=HTMLResponse)
async def logs(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    con = db()
    rows = con.execute("SELECT id,level,message,created_at FROM logs ORDER BY id DESC LIMIT 100").fetchall()
    con.close()
    return templates.TemplateResponse("logs.html", {
        "request": request, "user": user, "logs": rows, "active": "logs"
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
