# 麺包的工作台

一个面向考研备考的个人工作台：课表、单词打卡、每日待办、考研进度、错题复习、复盘笔记、DDL 倒计时、数据总览、AI 学习助手，共 9+1 个模块。

**PWA 应用**：支持「添加到主屏幕 / 安装应用」，手机（iOS/Android）和电脑（Chrome/Edge）都能像原生 App 一样从桌面图标打开。

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

## 安装为应用（PWA）

服务通过 **HTTPS**（或 localhost）访问时即可安装：

- **Android / 手机 Chrome**：浏览器菜单 →「添加到主屏幕」/「安装应用」
- **iOS / Safari**：分享按钮 →「添加到主屏幕」
- **电脑 Chrome / Edge**：地址栏右侧「安装」图标

> 注意：HTTP（非 localhost）下浏览器不触发安装，接入域名 + SSL 后即可（见部署章节）。

## License

[MIT](LICENSE) — 随意使用、修改、分发，保留版权声明即可。

## 技术栈

- 前端：零依赖单文件 HTML（原生 JS + Font Awesome CDN），localStorage + 云端双写
- 后端：FastAPI + SQLite（records 通用表 upsert 合并），JWT/共享 Key 双鉴权
- AI：DeepSeek OpenAI 兼容接口，后端转发 SSE 逐字流回

## 汽车测试开发学习计划

“学习进度”支持测试开发、数学、英语、政治；首页和数据总览只对有条目的分类计算平均进度。完整的[四周学习计划](docs/汽车测试开发-四周学习计划.md)安排在 2026-10-31 至 2026-11-27，含 28 条每日待办、4 个周进度、4 个验收节点与一份学习计划笔记。新设备初始化为空，再同步云端，不再生成演示记录或虚构学习时长。

在现有服务器上先预览导入与示例清理：

```bash
python3 scripts/import_testing_plan.py --db /opt/ytwb-backend/ytwb.db
```

核对输出后加 `--apply` 执行。脚本在数据库旁建立权限为 `0600` 的 SQLite 完整备份，再事务性地软删除与历史示例匹配的记录、导入计划。真实或已修改的记录、聊天记录保留。固定导入 ID 可避免重复创建，也不会覆盖已经更新的学习进度。数据库路径必须指向现存文件；不会创建空库。前端仍需将 `frontend/index.html` 与 `backend/static/index.html` 一起部署到现有静态目录。

无需安装额外测试依赖：

```bash
node --test tests/frontend.test.cjs
python3 -m unittest discover -s tests -p 'test_*.py'
```

## 安全红线

- `DEEPSEEK_API_KEY`、`API_KEY`、`JWT_SECRET`、`ADMIN_PASSWORD` 只存在于服务器 `.env`
- 代码与前端无任何明文密钥；`.env` 已被 `.gitignore` 拦截
