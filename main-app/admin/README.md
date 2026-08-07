# 站长后台

站长后台由 FastAPI 后端和 React 前端组成，提供登录、商品与图片管理、Prompt 管理、AI Provider 配置、推荐记录、试穿任务和系统状态页面。

## 本地启动

### 后端

```powershell
Set-Location backend
Copy-Item .env.example .env
python -m venv .venv-local
.\.venv-local\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8081
```

启动前编辑 `.env`，设置自己的 `JWT_SECRET_KEY`、`ADMIN_INIT_PASSWORD`、`INGEST_SECRET_KEY` 和 `FERNET_SECRET_KEY`。仓库不提供默认登录密码；未设置管理员密码时不会创建管理员账号。

### 前端

```powershell
Set-Location frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 3001
```

访问 `http://127.0.0.1:3001`。

## Docker Compose

```powershell
Copy-Item .env.example .env
# 填写 .env 中所有必填密钥与数据库密码
docker compose up --build
```

Compose 使用 PostgreSQL。`${VAR:?message}` 形式的变量若未填写，Compose 会在启动前直接报错，避免服务以公开默认口令运行。

## 关键环境变量

| 变量 | 必填 | 说明 |
|---|---:|---|
| `DATABASE_URL` | 是 | SQLAlchemy 数据库连接串 |
| `JWT_SECRET_KEY` | 是 | JWT 签名密钥，生产环境不少于 32 字符 |
| `ADMIN_INIT_USERNAME` | 否 | 初始管理员用户名，默认 `admin` |
| `ADMIN_INIT_PASSWORD` | 是 | 初始管理员密码，生产环境不少于 12 字符 |
| `INGEST_SECRET_KEY` | 是 | 主站、试衣站向后台写入统计数据时使用的共享密钥 |
| `FERNET_SECRET_KEY` | 是 | 加密后台保存的 Provider API Key |
| `MAIN_SITE_URL` | 否 | 主站地址 |
| `TRYON_WORKBENCH_URL` | 否 | 虚拟试衣工作台地址 |
| `CORS_ALLOW_ORIGINS` | 生产必填 | 逗号分隔的允许来源；生产环境不得使用 `*` |
| `GCS_BUCKET_NAME` | 使用云存储时 | GCS 桶名 |
| `PUBLIC_IMAGE_BASE_URL` | 使用公共图片时 | 商品图片公共 URL 前缀 |

真实配置只应存在于未跟踪的 `.env`、Secret Manager 或 CI/CD 密钥中。
