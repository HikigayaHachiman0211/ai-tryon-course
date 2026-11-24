# AI 羽绒服推荐与虚拟试穿平台

这是一个课程项目。选好颜色、尺码和预算后，可以查看羽绒服推荐、了解每件衣服为何适合自己，再把商品和照片带进试穿工作台。平台包含 Web 主站、试穿工作台、站长后台和原生微信小程序。

## v1.1.0 新增功能

| 功能 | 可以做什么 |
| --- | --- |
| 中英日三语 | 在主站、工作台、后台和小程序切换简体中文、English 或日本語。支持切换商品、推荐解释、历史记录和错误提示的展示语言。 |
| 微信小程序 | 在微信端完成推荐、商品筛选、Style Lab 单品分析和图片试穿。还可以看历史、使用文字与语音导购，以及把试穿图交给视频生成。 |
| 图片试穿 | 选择 Gemini/Vertex AI 或已配置的 ToTokens 等兼容渠道。界面按当前模型展示画幅、分辨率、质量等可用选项。 |
| 试穿视频 | 把试穿图或可用图片作为参考交给 01Router，选择转身、行走、面料特写等动作。支持按模型查看参数和报价、恢复异步任务、播放及下载。 |
| 实时试穿 | 在 Web 工作台用摄像头预览试穿效果。支持 Decart Lucy、Xmax 和 Reactor 配置，后台可管理访问权限、会话时长、预算和紧急停止。 |
| 后台与部署 | 后台统一管理提示词、模型与试穿渠道。提供 Docker、GCP 构建配置、Azure VM/Container Apps 和阿里云 ECS 部署模板。 |

功能入口、模型配置和版本差异见 [v1.1.0 更新日志](CHANGELOG.md)。

## 目录结构

| 目录 | 用途 |
| --- | --- |
| `main-app/frontend/` | React 主站，包括推荐、商品目录、Style Lab 和 AI 导购 |
| `main-app/backend/` | FastAPI 推荐、商品、历史和语音接口 |
| `main-app/admin/` | React 与 FastAPI 站长后台 |
| `tryon-workbench/` | FastAPI 工作台，包括图片、视频与实时试穿 |
| `miniprogram/` | TypeScript、WXML、WXSS 微信小程序 |
| `deploy/` | Azure 与阿里云的部署配置 |
| `scripts/` | 目录资源生成、语言校验与打包工具 |

## 本地启动

推荐 Python 3.11 和 Node.js 22.12 或更新的 22.x。以下命令使用 PowerShell，每组命令从仓库根目录在独立窗口执行。

先安装 Python 依赖，并为 8 件演示商品生成两个服务使用的目录文件。

```powershell
python -m venv .venv-local
.\.venv-local\Scripts\python.exe -m pip install -r main-app/backend/requirements.txt -r main-app/admin/backend/requirements.txt -r tryon-workbench/requirements.txt
.\.venv-local\Scripts\python.exe main-app/backend/scripts/build_catalog_read_model.py
.\.venv-local\Scripts\python.exe scripts/i18n/sync_workbench_catalog.py
```

### 1. 主站后端

```powershell
Set-Location main-app/backend
..\..\.venv-local\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

首次启动会用合成目录初始化 SQLite。可以访问 [主站健康检查](http://127.0.0.1:8000/health)。

### 2. 主站前端

```powershell
Set-Location main-app/frontend
Copy-Item .env.example .env
npm ci
npm run dev -- --host 127.0.0.1 --port 3000
```

打开 [推荐主站](http://127.0.0.1:3000)。

### 3. 虚拟试穿工作台

```powershell
Set-Location tryon-workbench
Copy-Item .env.example .env
npm ci
npm run build
..\.venv-local\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8080
```

打开 [试穿工作台](http://127.0.0.1:8080/static/index.html)。页面和演示目录可以本地浏览。图片生成、视频和实时效果需要各自的供应商配置。单独使用 Gemini 图片试穿时，可在工作台的 `.env` 中设置自己的 `GEMINI_API_KEY`。

### 4. 站长后台

先在 `main-app/admin/backend/` 将 `.env.example` 复制为 `.env`。设置自己的 `ADMIN_INIT_PASSWORD`（至少 12 字符）、`JWT_SECRET_KEY` 和 `INGEST_SECRET_KEY`（各至少 32 字符）。为后台保存模型密钥时，也要设置 `FERNET_SECRET_KEY`，并将相同值配置到读取该后台模型配置的主站和工作台。

```powershell
Set-Location main-app/admin/backend
Copy-Item .env.example .env
# 复制后先在 .env 中填入上面的值，再启动服务。
..\..\..\.venv-local\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8081
```

可用 `python -c "import secrets; print(secrets.token_urlsafe(48))"` 生成随机应用密钥。Fernet 密钥可用 `from cryptography.fernet import Fernet` 后调用 `Fernet.generate_key()` 生成。主站和工作台向后台上报时使用同一个 `INGEST_SECRET_KEY`。

```powershell
Set-Location main-app/admin/frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 3001
```

打开 [站长后台](http://127.0.0.1:3001)。初次登录后可在 **AI 模型设置** 配置供应商、模型、功能路由和密钥。模型不可用时，商品推荐可以使用规则推荐。

### 5. 微信小程序

在微信开发者工具中导入 `miniprogram/`。如果按上面的端口启动，在小程序 **设置** 选择 **本地手动端口（8000 / 8080）**。真机需要自己的小程序 AppID、可访问的 HTTPS 域名和相应的合法域名配置。参见 [小程序接入说明](miniprogram/README.md)。

## 配置与验证

- 图片试穿、视频和摄像头串流分别配置。详见 [ToTokens 图片试穿](tryon-workbench/TOTOKENS_SETUP.md)、[01Router 视频](tryon-workbench/VIDEO_GENERATION_SETUP.md)、[Decart 实时试穿](tryon-workbench/DECART_REALTIME_SETUP.md)、[Xmax 实时试穿](tryon-workbench/XMAX_REALTIME_SETUP.md)和 [Reactor 实时试穿](tryon-workbench/REACTOR_REALTIME_SETUP.md)。
- 两个 Web 前端在各自目录运行 `npm test -- --run` 和 `npm run build`。工作台运行 `npm test`，小程序运行 `npm run verify`。三个 Python 服务在各自的服务目录运行 `python -m pytest -q`，先为虚拟环境安装 `pytest` 与对应服务的依赖。
- 可用 `python scripts/i18n/check_catalog_coverage.py` 检查生成后的目录和语言资源。部署模板需要自己的域名、存储和数据库。生产构建应配置 `VITE_TRYON_BASE_URL` 与 `VITE_ADMIN_BASE_URL`。参见 [架构概览](PROJECT_OVERVIEW.md)、[Azure 模板](deploy/azure/README.md)和 [阿里云模板](deploy/aliyun/README.md)。

公开版使用 8 条合成商品和 4 张通用人台。演示商品链接和图片为占位素材。真实云凭据、商品原始数据、真人照片和运行数据由部署者自行管理。上传和生成媒体的访问策略见 [SECURITY.md](SECURITY.md)。
