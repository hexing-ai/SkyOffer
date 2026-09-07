# 安装与运行

## 最短体验路径

Node.js 22 + Git 即可。克隆后在 `frontend/` 运行 `npm ci`、`npm run demo`，打开 http://127.0.0.1:3200/。演示资源全部随仓库提供，不需要联网调用 AI。第一次安装 npm 依赖需要访问 npm。

## 完整模式

需要 Python 3.11、Node.js 22、DeepSeek API Key。macOS / Linux 命令见根 README。Windows PowerShell 可替换环境创建和激活命令为：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

之后编辑 `.env` 设置 `MODEL_API_KEY`，在仓库根目录执行：

```bash
python -m backend.scripts.bootstrap_internal_alpha
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001
```

另开终端，在 `frontend/` 运行 `npm ci` 和 `npm run dev`。Windows 若不允许激活脚本，也可以直接运行 `.venv\Scripts\python.exe`。

## 配置

| 变量 | 用途 |
| --- | --- |
| `MODEL_API_KEY` | 服务端模型密钥，只写本地 `.env` 或部署平台环境变量 |
| `MODEL_BASE_URL` / `MODEL_NAME` | 默认 DeepSeek 官方 API / deepseek-chat |
| `DATABASE_URL` | 默认项目根目录下 `data/skyoffer.db`；生产改为 PostgreSQL |
| `BACKEND_URL` | 前端转发目的地，默认 `http://127.0.0.1:8001`，可在 `frontend/.env.local` 设置 |
| `NEXT_PUBLIC_DEMO_MODE` | 由 `npm run demo` / `build:demo` 设置为 `1` |
| `NEXT_PUBLIC_BASE_PATH` | 静态 Demo 子路径，GitHub Pages 工作流设为 `/SkyOffer` |

任何 `NEXT_PUBLIC_*` 值都可能进入浏览器，禁止放置密钥。三个 `.example` 文件仅作为模板。

## 成功运行的标志

- 前端首页 http://127.0.0.1:3200/ 可打开。
- 完整模式后端 `/api/v1/ready` 返回 `ready` 和 20 个项目。
- `/programs` 能搜索院校并进入详情。
- 完整模式保存申请档案后，选校页面自动带入；示例模式始终只读固定合成档案。

## 常见问题

- **端口被占用**：关闭之前的 demo/dev 进程；前端默认 3200，后端 8001。
- **页面出现 502 或数据库加载失败**：完整模式需先启动后端；检查 `BACKEND_URL`。
- **SERVICE_NOT_READY**：检查模型配置，先运行数据引导脚本；请只分享错误码和 Request ID。
- **模型故障时仍有结果**：完整版本会按规则降级解释，页面明确标注，不代表模型已经调用成功。
- **示例没有随着我的背景变化**：公开示例不是个人分析工具；运行完整模式后再输入自己的资料。
- **数据长期未维护**：来源具有核验与到期时间，质量门禁可能拒绝过期版本；请按官网重新复核，不应绕过门禁。

## Docker Compose

提供 `deploy/compose.production.yaml`，使用前后端容器和 PostgreSQL。复制 `deploy/production.env.example` 为 `deploy/production.env`，填写配置后执行：

```bash
docker compose --env-file deploy/production.env -f deploy/compose.production.yaml up --build -d
```

这条生产路径不是无需配置的快速体验。它要求模型密钥、数据库口令、数据库连接串、明确 Host 和发布版本，参见 [生产说明](../PRODUCTION_READINESS.md)。
