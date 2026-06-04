# AI 羽绒服推荐与虚拟试衣课程项目

这是一个面向课程展示和本地学习的 AI 羽绒服推荐平台。项目包含主站推荐系统、AI 导购聊天助手、站长后台、虚拟试衣工作台，以及商品与用户推荐记录相关的管理能力。

本仓库是公开发布版本，已经移除本地数据库、真实 API Key、云服务凭据、生成图片数据集、依赖目录和构建产物。你可以基于 `.env.example` 或后台配置页面填写自己的模型服务与部署参数。

## 项目功能

### 主站推荐平台

- 根据用户颜色偏好、性别、尺码、款式偏好、价格区间等条件推荐羽绒服商品。
- 支持上传全身照，用多模态模型辅助判断身型和适配风格。
- 支持商品评分、颜色适配、身材适配、款式适配等维度展示。
- 支持推荐历史记录查看。
- 支持跳转虚拟试衣工作台，进一步体验试穿效果。

### AI 导购

- 以悬浮聊天窗口形式出现在主站。
- 可以从自然语言中提取推荐条件，例如颜色、性别、尺码、风格。
- 支持自动填表、填表并生成推荐。
- 默认优先使用后台配置的大模型 Provider；模型不可用时回退到规则逻辑。

### AI 羽绒服推荐推断

- 推荐推断默认优先调用后台配置的大模型。
- 当前公开版本支持 MiMo、Gemini、Deepseek 等 Provider 的配置结构。
- 当 API 不可用、模型响应异常或返回非 JSON 时，系统会回退到规则推荐，并在调试字段中记录原因。
- MiMo v2.5 已适配 `reasoning_content` 较长的情况，推荐调用保留足够 token 以获得最终 JSON 输出。

### 站长后台

- Provider 管理：配置模型名称、Base URL、API Key、认证方式、默认 Provider。
- 功能路由：配置推荐、图像分析、AI 导购等功能优先使用的 Provider 和回退顺序。
- Prompt 管理：维护推荐、图像分析、导购等模型提示词。
- 商品管理、图片管理、推荐历史、系统监控等后台页面。

### 虚拟试衣工作台

- `tryon-workbench/` 是独立的本地试衣工作台。
- 可与主站推荐结果联动，也可作为单独页面运行。
- 公开仓库不包含真实云服务凭据，部署或本地测试时需要自行配置。

## 目录结构

```text
.
├── main-app/                  # 主站、主后端、后台系统
│   ├── backend/               # 推荐 API、AI 推断、商品读取、历史记录
│   ├── frontend/              # 主站前端
│   └── admin/
│       ├── backend/           # 站长后台 API、本地配置数据库
│       └── frontend/          # 站长后台前端
├── tryon-workbench/           # 虚拟试衣工作台
├── DESIGN.md                  # 设计说明
├── PROJECT_OVERVIEW.md        # 项目概览
├── RESUME_PROJECT_SUMMARY.md  # 项目恢复说明
├── stop_all_local_debug.bat   # Windows 一键停止本地调试服务
└── README.md
```

## 本地运行

### 环境要求

- Windows 10/11
- Python 3.10 或更高版本
- Node.js 18 或更高版本
- npm
- 可选：自己的大模型 API Key

### 主站后端

```powershell
cd main-app/backend
python -m venv .venv-local
.\.venv-local\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
$env:ENABLE_DEBUG_PAGES="true"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查：

```text
http://127.0.0.1:8000/health
```

AI 运行时诊断：

```text
http://127.0.0.1:8000/api/debug/ai-runtime
```

### 主站前端

```powershell
cd main-app/frontend
npm install
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run dev -- --host 127.0.0.1 --port 3000
```

访问：

```text
http://127.0.0.1:3000
```

### 后台后端

```powershell
cd main-app/admin/backend
python -m venv .venv-local
.\.venv-local\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
$env:DATABASE_URL="sqlite:///./admin_local.db"
$env:JWT_SECRET_KEY="<replace-with-a-local-dev-secret>"
$env:ADMIN_INIT_USERNAME="admin"
$env:ADMIN_INIT_PASSWORD="Admin@2026!"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8081
```

### 后台前端

```powershell
cd main-app/admin/frontend
npm install
npm run dev -- --host 127.0.0.1 --port 3001
```

访问：

```text
http://127.0.0.1:3001
```

默认本地账号：

```text
用户名：admin
密码：Admin@2026!
```

这是本地调试密码，正式部署前必须改成强密码，并通过环境变量或密钥管理系统注入。

## AI 模型配置

推荐方式是先启动后台，然后进入：

```text
http://127.0.0.1:3001/ai-models
```

在后台配置：

- Provider 名称和 Key，例如 `mimo`、`gemini`、`deepseek`
- Base URL
- 默认模型
- API Key
- 认证方式，例如 `api-key` header 或 Bearer Token
- 功能路由，例如推荐、视觉分析、AI 导购的默认 Provider 和回退链

主站后端会按以下顺序读取 AI 配置数据库：

1. `AI_CONFIG_DATABASE_URL`
2. `DATABASE_URL`
3. 本地开发回退：`main-app/admin/backend/admin_local.db`

因此，本地调试时只要后台已经保存配置，主站后端通常可以直接读取后台本地数据库。

## 一键停止本地服务

Windows 下可以双击：

```text
stop_all_local_debug.bat
```

它会停止本地调试常用端口：

```text
8000  主站后端
3000  主站前端
8080  试衣工作台
8081  后台后端
3001  后台前端
```

脚本只针对这些端口和本项目启动脚本打开的窗口，不会全局终止所有 Python 或 Node 进程。

## 安全说明

本公开仓库不会提交以下内容：

- `.env`、`.env.*` 真实环境文件
- API Key、JWT Secret、云服务凭据
- `*.db`、`*.sqlite` 本地数据库
- `node_modules/`
- `dist/`、`build/`
- Python 虚拟环境
- 生成图片、上传文件、历史记录
- GCP Service Account、私钥文件

如果你要部署到线上，请通过平台环境变量、Secret Manager 或 CI/CD 密钥注入配置，不要把真实密钥写入源码。

## 常见问题

### 主站显示“未配置 AI 引擎密钥”

先检查：

```text
http://127.0.0.1:8000/api/debug/ai-runtime
```

重点看：

- `db_available`
- `providers.mimo.enabled`
- `providers.mimo.has_api_key`
- `providers.mimo.decrypt_ok`
- `features.recommendation.default_provider`

如果后台显示配置成功，但主站仍显示旧状态，通常是主站后端没有重启。重启 `main-app/backend` 的 `uvicorn` 进程后再刷新页面。

### Mimo 接口返回 200 但推荐仍回退

MiMo v2.5 可能先输出较长 `reasoning_content`，最终 JSON 在 `message.content` 中。如果 token 上限太低，最终 JSON 会被截断。当前版本已将推荐调用的 `max_completion_tokens` 调整为更安全的值，并在返回空或非 JSON 时记录明确错误。

### 前端能打开但接口失败

确认前端环境变量指向正确后端：

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
```

同时确认后端：

```text
http://127.0.0.1:8000/health
```

### 后台配置保存后主站没生效

确认主站后端读取的是同一个数据库。调试接口中的 `db_url_source` 应显示：

```text
local_admin_db
```

或你显式配置的 `AI_CONFIG_DATABASE_URL` / `DATABASE_URL`。

## 课程用途

这个项目适合用于：

- AI 应用课程设计
- 大模型 API 接入示例
- 多 Provider 回退架构示例
- 前后端分离项目练习
- 管理后台与主站联动练习
- AI 推荐和虚拟试衣方向的原型演示

公开版本以学习和演示为目标，不包含生产环境的密钥、数据和部署凭据。
