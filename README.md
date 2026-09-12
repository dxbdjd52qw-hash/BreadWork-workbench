# 麺包的工作台（研途工作台 YTWB）

一个面向考研备考的个人工作台：课表、单词打卡、每日待办、考研进度、错题复习、复盘笔记、DDL 倒计时、数据总览、AI 学习助手，共 9+1 个模块。

**云端架构**：FastAPI 后端跑在阿里云 ECS（systemd 常驻），前端由后端静态托管，手机/电脑浏览器直接访问即可使用；AI 对话走 DeepSeek（SSE 流式）；多设备数据双向同步（10s 轮询 + 改动防抖推送，`updatedAt` 新者胜 + 墓碑软删）。

## 目录结构

```
backend/            FastAPI 后端（单文件 main.py）
  static/index.html 后端托管的前端（线上实际使用的版本）
frontend/index.html 前端原型源码（改动后需同步到 backend/static/）
docs/               交接文档、需求规格、数据迁移脚本
```

## 快速部署（阿里云 ECS · Alibaba Cloud Linux）

```bash
# 1. 服务器上准备目录
sudo mkdir -p /opt/ytwb-backend && cd /opt/ytwb-backend
python3 -m venv venv && venv/bin/pip install -r backend/requirements.txt

# 2. 配置环境变量（⚠️ .env 永远不要提交到 git）
cp backend/.env.example /opt/ytwb-backend/.env   # 然后填入真实密钥

# 3. systemd 常驻
sudo cp backend/ytwb-api.service /etc/systemd/system/
sudo systemctl enable --now ytwb-api
```

详细接口契约见 [docs/研途工作台-需求规格大纲-v2.md](docs/研途工作台-需求规格大纲-v2.md)；旧数据迁移脚本见 [docs/迁移脚本-浏览器控制台版.js](docs/迁移脚本-浏览器控制台版.js)。

## 前端配置

前端与后端同源部署时**开箱即用**（自动识别 `location.origin`）；单独打开 `frontend/index.html` 则为本地模式。云端模式只需在页面 AI 抽屉「配置接口」填入你 `.env` 里的 `API_KEY`。

## License

[MIT](LICENSE) — 随意使用、修改、分发，保留版权声明即可。

## 技术栈

- 前端：零依赖单文件 HTML（原生 JS + Font Awesome CDN），localStorage + 云端双写
- 后端：FastAPI + SQLite（records 通用表 upsert 合并），JWT/共享 Key 双鉴权
- AI：DeepSeek OpenAI 兼容接口，后端转发 SSE 逐字流回

## 安全红线

- `DEEPSEEK_API_KEY`、`API_KEY`、`JWT_SECRET`、`ADMIN_PASSWORD` 只存在于服务器 `.env`
- 代码与前端无任何明文密钥；`.env` 已被 `.gitignore` 拦截
