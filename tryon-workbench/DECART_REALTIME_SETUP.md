# Decart Lucy VTON 实时试穿

推荐页打开试衣工作台后，可直接用已选商品图开始实时试穿，也可在实时区上传服装参考图或从羽绒服库选品。在同一次会话里点「应用服装」即可换衣，也支持切换前后摄像头、镜像本地预览和截取实时试穿帧。用户先打开免费的本地相机预览，再同意发送至 Decart，并确认页面显示的本次最高费用。应用只转发连接信令和服装图，摄像头和试穿视频通过 WebRTC 在浏览器与 Decart 之间传输。工作台不录制视频，也不读取麦克风。

## 启用方式（推荐：通过管理后台统一配置）

1. 登录管理后台，进入 **AI 模型/API → 实时试穿 (Decart)**（`/ai-models?tab=realtime`）：
   - 填入 **Decart API Key**，保存后点击 **「测试连接（零费用）」** 验证（仅申请短寿命受限 Client Token，不发起视频推流，不产生费用）。
   - 开启或配置 **体验码**（支持一键生成 24 位强随机体验码），也可按需关闭体验码校验。
   - 按需调整单秒费率、单场最长秒数、全站日/月预算、单浏览器日预算、并发与频控，以及默认提示词。
   - 打开 **「启用实时试穿」** 并保存。所有敏感密钥使用 `FERNET_SECRET_KEY` 加密保存在共享 PostgreSQL 中，试衣工作台每 **15 秒**自动热更新，无需重启容器。
2. 若在未配置管理数据库的环境运行，工作台会自动回退读取环境变量 `DECART_REALTIME_ENABLED=true`、`DECART_API_KEY`、`DECART_REALTIME_ACCESS_CODE`（至少 16 位）等。
3. **Azure Container Apps / 生产环境 Origin**：工作台在生产模式（`APP_ENV=production`）开启实时试穿时要求工作台公开地址为 `https://`。可在管理后台填写 **工作台公开 Origin**，或在容器环境变量配置 `DECART_REALTIME_ORIGIN` / `WORKBENCH_PUBLIC_URL`（以及 `ROUTER01_MEDIA_BASE_URL`）。
4. Docker 构建会打包固定版本的浏览器 SDK。本地直接启动 Python 服务时，从 `tryon-workbench` 目录先运行 `npm ci` 和 `npm run build`。用 `localhost` 打开工作台，本地账本可使用 SQLite。

## 价格和限制

Lucy VTON 3.6 标准档 720p 的公开价为 2 credits／秒，即 US$0.02／秒。10 秒上限是 US$0.20，15 秒是 US$0.30，20 秒是 US$0.40。工作台发出的连接固定使用标准档。核价日期为 2026-11-22。[Decart 实时价格](https://docs.platform.decart.ai/getting-started/pricing)

| 环境变量（DB 未配置时生效） | 默认 | 控制什么 |
| --- | ---: | --- |
| `DECART_REALTIME_MAX_SECONDS` | 20 | 每次会话可选 10 秒至该值。可配置范围 10–60 秒 |
| `DECART_REALTIME_DEFAULT_SECONDS` | 15 | 页面默认单场秒数 |
| `DECART_REALTIME_REQUIRE_ACCESS_CODE` | true | 是否强制访客输入体验码 |
| `DECART_REALTIME_CENTS_PER_SECOND` | 2 | 每秒预留的美元分。公开费率上涨时要同步调高此值 |
| `DECART_REALTIME_DAILY_CENTS` | 200 | 工作台每日总预算 US$2 |
| `DECART_REALTIME_MONTHLY_CENTS` | 1000 | 工作台每月总预算 US$10 |
| `DECART_REALTIME_VISITOR_DAILY_CENTS` | 80 | 每个浏览器每日预算 US$0.80 |
| `DECART_REALTIME_MAX_ACTIVE` | 1 | 整个工作台的并发上限，每个浏览器同时至多一场 |
| `DECART_REALTIME_STARTS_PER_MINUTE` | 3 | 整个工作台过去 60 秒允许的开始次数 |

每日和每月预算按香港时间（`Asia/Hong_Kong`）的自然日、自然月计算。当天剩余时间不足以完成一场会话时，工作台暂缓接受新的会话，到了零点再开放。三个预算中任一个不足时，工作台拒绝连接。可将每日或每月预算设为 0 来拒绝新会话。

## 管理后台监控、熔断与对账

1. 登录管理后台，进入左侧导航 **「实时试穿」**（`/realtime-tryon`）：
   - 实时查看今日/本月已计入金额、Decart 已确认金额与未确认保留金额、近 14 天费用与场次趋势、今日各访客占用情况与实时会话账本明细。
   - **单场强制停止**：对运行中或等待中的会话直接发送停止信号。
   - **人工核销对账**：对因断线按上限保留的会话，可对照 Decart 控制台账单输入实际秒数重新结算并释放多余预留额度。
   - **紧急全部熔断**：一键停用实时试穿、取消所有待连接票据并通知所有活动会话停止。
2. 命令行查账仍可用：从工作台服务的同一运行环境执行 `python -m app.realtime_budget`。

## 验收

先运行 `python -m pytest tests/test_realtime.py`（工作台）与 `python -m pytest app/tests/test_realtime_tryon.py`（管理后台）做模拟验收，无需 API 密钥或余额。要验收真实视频，可启用功能、先在管理后台点 **「测试连接（零费用）」**，然后在工作台选好商品图，先验证本地预览，再手动开始一场 10 秒会话。检查实时画面、同一会话内的服装切换、后台切换后相机关闭，并在管理后台 `/realtime-tryon` 页面与 Decart 账单核对本次用量。
