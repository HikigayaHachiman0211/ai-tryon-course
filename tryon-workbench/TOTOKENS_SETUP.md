# ToTokens 试穿生图配置

1. 在管理后台的「AI 模型/API 管理中心 → 试衣站 API」选择 **ToTokens**。
2. 填写中转站 HTTPS 地址（默认为 `https://totokens.cc`）和该站的 API Key，确认密钥分组有目标模型权限。
3. 确认 Gemini 生图模型 ID 为 `gemini-3.1-flash-image`，GPT 生图模型 ID 为 `gpt-image-2`。如果中转站提供的实际模型 ID 不同，可在此修改。
4. 启用并保存配置。在试穿工作台选择相应模型；配置变更通常在约 30 秒内生效，也可刷新工作台。

原有 Gemini 直连配置与 ToTokens 的密钥、模型设置分别保存。中转模式对每张图片仅发送一次生成请求，不自动重试或切换模型；管理后台的连接测试只读取模型列表，不生成图片。

[ToTokens 配置教程](https://doc.totokens.cc/config.html)仅说明站点地址及客户端配置，并未列出生图 API 格式。本适配按常见中转接口实现：Gemini 使用 `/v1beta/models/{model}:generateContent`，GPT 使用 `/v1/images/edits`；实际模型权限和接口兼容性取决于中转站及密钥分组。
