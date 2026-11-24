# Xmax X2.1 实时试穿接入与成本控制指南

试衣工作台现已原生适配 **Xmax X2.1 / X2.1-Flash**（最高 1080p 低延迟 WebRTC 实时试穿，使用官方 `@xmaxai/web-sdk` v1.1.5），并与 Decart Lucy VTON 3.6 共享同一套香港时间自然日/自然月防刷预算账本与管理后台监控体系。

## 安全与成本核心设计

1. **永久主密钥绝不出服务端**：管理员填入的 Xmax `uk-...` 永久 API Key 仅以 Fernet 密文存储在共享 PostgreSQL 中，绝不下发到浏览器。
2. **单场受限临时密钥 `tk-`**：每次访客点击「开始实时试穿」且通过体验码、全站日/月预算、单浏览器日预算、并发与频控检查后，工作台才向 Xmax 申请一次性临时密钥（`POST /temporary-api-key`）：
   - `expireSeconds = limit_seconds + 25`（TTL 自动到期）
   - `pointsLimit = max_credits`（积分硬上限封顶）
   - `temporaryApiKeySessionLimit = 1`（单临时密钥最多 1 路并发）
3. **最低账户余额熔断**：若配置了 `min_account_credits`（默认 `60` 积分），每次签发 `tk-` 前会先调用零费用的 `GET /balance`；余额不足直接拒绝并释放预留额度。
4. **先传图、再连接、服务端看门狗兜底**：
   - 参考服装图先通过 COS STS 上传（不开启 RTC 推流，**0 计费秒数**）。
   - 会话开始后客户端倒计时 + 服务端定时看门狗到期或用户结束/切后台时，自动调用 `DELETE /session/{sessionUid}`、`PUT /temporary-api-key/{tk}/inactive` 注销临时密钥，并从 `/temporary-api-key/{tk}/status` 拉取真实 `consumedCredit` 精准核销。
5. **跨引擎统一防重与防刷**：同一浏览器同一时刻最多只能进行一场 Decart **或** Xmax 实时试穿；两套引擎各自独立的日/月/访客预算互不干扰。

## 管理后台启用步骤

1. 登录管理后台，进入 **AI 模型/API → 实时试穿**（`/ai-models?tab=realtime`），切换顶部引擎选择器至 **「Xmax X2.1 实时试穿」**：
   - 选择服务节点：`global`（`https://api.xmax.ai/open/api/v1`）或 `china`（`https://cloud.xmax.22duck.cn/open/api/v1`）。
   - 选择默认模型（`x2.1` 1080p / `x2.1-flash` 720p）、允许模型、默认采集分辨率预设及人脸保持（Face Restoration）。
   - 填入 Xmax `uk-` 主密钥并保存，点击 **「检验余额与连通性（零费用）」** 验证连通性与当前可用积分。
   - 生成或填写 16–256 位体验码、配置预算上限（官方费率参考：`1 credit/s ≈ $0.10/min` / `$6/hour`）。
   - 打开 **「启用 Xmax 实时试穿」** 并保存（15 秒内自动同步到工作台，无需重启容器）。
2. 进入管理后台 **「实时试穿」**（`/realtime-tryon`）：
   - 顶部可筛选 `全部引擎` / `Decart Lucy VTON` / `Xmax X2.1`，并点击 **「查询 Xmax 余额」** 实时查看剩余积分及 24 小时消耗。
   - 若某场异常断线按上限保留，可点击该行的 **「同步账单」**（实时调用 Xmax `/temporary-api-key/{tk}/status` 或 `/session/{uid}/status` 自动核销）或使用 **「人工核销对账」** / **「紧急全部熔断」**。

## 环境变量兜底（无管理数据库时生效）

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `XMAX_REALTIME_ENABLED` | `false` | 是否启用 Xmax 实时试穿 |
| `XMAX_API_KEY` | - | Xmax 永久主密钥（`uk-...`） |
| `XMAX_REALTIME_ENVIRONMENT` | `global` | `global` 或 `china` |
| `XMAX_REALTIME_MODEL` | `x2.1` | 默认模型 `x2.1` 或 `x2.1-flash` |
| `XMAX_REALTIME_CAMERA_PRESET` | `1080x1920` | 采集分辨率预设 |
| `XMAX_REALTIME_FACE_RESTORATION` | `true` | 是否保持人脸特征 |
| `XMAX_REALTIME_REQUIRE_ACCESS_CODE` | `true` | 是否要求体验码 |
| `XMAX_REALTIME_ACCESS_CODE` | - | 16–256 位访客体验码 |
| `XMAX_REALTIME_ORIGIN` | - | 生产环境 HTTPS Origin |
| `XMAX_REALTIME_MIN_SECONDS` / `MAX_SECONDS` / `DEFAULT_SECONDS` | `10` / `60` / `30` | 时长控制（秒） |
| `XMAX_REALTIME_CREDITS_PER_SECOND` | `1` | 积分速率（积分/秒） |
| `XMAX_REALTIME_CENTS_PER_MINUTE` | `10` | 预算折算单价（美分/分钟） |
| `XMAX_REALTIME_DAILY_CENTS` / `MONTHLY_CENTS` / `VISITOR_DAILY_CENTS` | `200` / `1000` / `50` | 全站日/月/单浏览器日预算（美分） |
| `XMAX_REALTIME_MIN_ACCOUNT_CREDITS` | `60` | 最低账户积分熔断阈值 |
| `XMAX_REALTIME_MAX_ACTIVE` / `STARTS_PER_MINUTE` | `1` / `3` | 全站并发与每分钟启动上限 |

## 官方参考

- [Xmax X2.1 Realtime Video Docs](https://platform.xmax.ai/docs/capabilities/realtime-video)
- [@xmaxai/web-sdk (npm)](https://www.npmjs.com/package/@xmaxai/web-sdk)
