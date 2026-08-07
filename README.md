# AI 羽绒服推荐与虚拟试衣平台

这是课程项目的可公开备份，包含羽绒服智能推荐主站、AI 导购、站长后台和虚拟试衣工作台。仓库中的代码可以在本地启动；需要联网模型能力时，请使用自己的 API Key 或 Google Cloud 项目配置。

## 已公开化处理的内容

- 未包含 `.env`、API Key、JWT 密钥、数据库口令、Service Account 或私钥文件。
- 未包含本地 SQLite/PostgreSQL 数据、用户上传照片、试穿结果、历史记录或日志。
- 未包含真实云项目 ID、Cloud Run 地址、Cloud SQL 实例名、GCS 桶名或本机绝对路径。
- 原真人示例照片已删除，替换为无真实身份、无面部特征的通用人台图。
- 原始商品全集未公开，仓库提供 8 条合成商品数据，保证目录初始化和演示流程可运行。
- `node_modules`、虚拟环境、缓存和构建产物均由 `.gitignore` 排除。

示例值只用于说明格式，不是可用凭据。请勿把生产密钥写进源码、命令历史或提交记录。

## 功能组成

- 主站推荐：按性别、颜色、尺码、款式、价格等条件生成推荐，并展示评分解释。
- AI 导购：从自然语言提取偏好，支持自动填表、生成推荐和规则回退。
- 商品目录：支持搜索、筛选、推荐历史和商品详情。
- 站长后台：管理商品、Prompt、模型 Provider、功能路由、试穿任务和系统状态。
- 虚拟试衣：接收主站商品与用户图片，调用配置的 Gemini 图像模型生成试穿结果。

## 目录结构

```text
.
├── main-app/
│   ├── database.json             # 合成商品目录
│   ├── backend/                  # 主站 FastAPI 后端
│   ├── frontend/                 # 主站 React + Vite 前端
│   └── admin/
│       ├── backend/              # 管理后台 FastAPI 后端
│       └── frontend/             # 管理后台 React 前端
├── tryon-workbench/
│   ├── database.json             # 合成商品目录副本
│   ├── main.py                   # 试衣 FastAPI 服务
│   └── static/                   # 试衣页面与通用人台素材
├── DESIGN.md
├── PROJECT_OVERVIEW.md
├── SECURITY.md
└── README.md
```

## 环境要求

- Python 3.10 或更高版本（推荐 3.11）
- Node.js 18 或更高版本
- npm
- 可选：Docker、Google Cloud SDK

以下命令以 PowerShell 为例，均从仓库根目录执行。

## 1. 启动主站后端

```powershell
Set-Location main-app/backend
python -m venv .venv-local
.\.venv-local\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000/health` 检查状态。首次启动会根据 `main-app/database.json` 创建本地 SQLite 商品库。

## 2. 启动主站前端

新开一个 PowerShell：

```powershell
Set-Location main-app/frontend
Copy-Item .env.example .env
npm ci
npm run dev -- --host 127.0.0.1 --port 3000
```

访问 `http://127.0.0.1:3000`。开发模式默认连接 `http://127.0.0.1:8000`、`http://127.0.0.1:8080/static/index.html` 和 `http://127.0.0.1:8081`。

## 3. 启动虚拟试衣工作台

不配置模型密钥也能启动页面和商品浏览；生成试穿图前必须配置自己的 Gemini/Vertex AI 凭据。

```powershell
Set-Location tryon-workbench
python -m venv .venv-local
.\.venv-local\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 二选一：Gemini API Key，或 Google Cloud Application Default Credentials
$env:GEMINI_API_KEY="<your-own-api-key>"
# $env:GCP_PROJECT_ID="<your-gcp-project-id>"

python -m uvicorn main:app --host 127.0.0.1 --port 8080
```

访问 `http://127.0.0.1:8080/static/index.html`，健康检查为 `http://127.0.0.1:8080/health`。

## 4. 启动站长后台

后台没有提交默认密码。先复制配置模板，再填写你自己的值：

```powershell
Set-Location main-app/admin/backend
Copy-Item .env.example .env

# 可用以下命令生成随机 JWT/服务间密钥：
python -c "import secrets; print(secrets.token_urlsafe(48))"

# 安装并启动后端
python -m venv .venv-local
.\.venv-local\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8081
```

请至少在 `.env` 中设置：

- `JWT_SECRET_KEY`：不少于 32 个字符。
- `ADMIN_INIT_PASSWORD`：不少于 12 个字符；这是首次创建管理员时使用的密码。
- `INGEST_SECRET_KEY`：不少于 32 个字符，并与主站、试衣服务保持一致。
- `FERNET_SECRET_KEY`：用于加密后台保存的模型 API Key。

Fernet 密钥可在安装后台依赖后生成：

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

再启动后台前端：

```powershell
Set-Location main-app/admin/frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 3001
```

访问 `http://127.0.0.1:3001`，使用你在 `.env` 中设置的管理员用户名和密码登录。

## AI Provider 配置

启动后台后进入 `/ai-models`，填写自己的 Provider、Base URL、模型名和 API Key。API Key 会通过 `FERNET_SECRET_KEY` 加密后写入后台数据库。主站与试衣服务按以下顺序读取配置：

1. `AI_CONFIG_DATABASE_URL`
2. `DATABASE_URL`
3. 本地开发数据库 `main-app/admin/backend/admin_local.db`

未配置模型或模型请求失败时，推荐主站会回退到规则推荐；虚拟试衣生成能力则会返回明确的未配置错误。

## Docker 与云部署

- 主站容器入口：`main-app/Dockerfile`
- 后台 Compose：先把 `main-app/admin/.env.example` 复制为 `.env` 并填写必填项，再运行 `docker compose up --build`。
- Cloud Build 文件只保留 substitution 变量。请在构建触发器或 Secret Manager 中注入真实值。
- 生产前端必须显式设置 `VITE_TRYON_BASE_URL` 和 `VITE_ADMIN_BASE_URL`；代码中没有绑定任何现有线上服务。

## 验证

```powershell
# 主站后端
Set-Location main-app/backend
python -m pip install -r requirements-test.txt
python -m pytest -q

# 主站前端
Set-Location ../frontend
npm ci
npm run build

# 后台后端
Set-Location ../admin/backend
python -m pip install pytest
python -m pytest -q

# 后台前端
Set-Location ../frontend
npm ci
npm run build

# 试衣服务
Set-Location ../../../tryon-workbench
python -m pip install pytest
python -m pytest -q
```

## 隐私与安全

用户上传的全身照和生成结果属于敏感数据。公开部署前应设置访问控制、数据保留期限、删除机制、日志脱敏和隐私告知；不要直接沿用课程演示配置。完整注意事项见 [SECURITY.md](SECURITY.md)。

本仓库用于课程学习和原型演示，不承诺生产级可用性，也不包含任何第三方服务额度或授权。
