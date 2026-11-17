## 修复：内网网关 / cc-switch 测试连接报 HTTP 400

- 修复「测试连接」提示 `'messages' must contain the word 'json'` 的 400 错误：测试请求现在明确包含 json 并要求返回 json
- 网关不支持 `response_format`（json_object）时自动降级重试一次，不再直接失败
- AI 报错提示改为显示网关返回的具体 message，便于定位问题

## 说明

- 更新只替换程序文件，`data`、`plugins`、`logs` 均保留
