Oracle 11g 连接支持与错误提示

- 优化 DSN 解析：只填服务名（如 tsoa）+ 主机时，自动拼成 host:port/tsoa
- 新增「TNS 配置目录」字段，支持 tnsnames.ora 别名
- 明确提示 DPY-3010：Oracle 11g 不支持 thin 模式，需要 thick + Instant Client
- 明确提示 DPY-4027 / DPY-4011 / DPY-6001 的原因和处理方式
- Oracle 11g 使用方式：安装 Instant Client 19c/21c x64 → 数据源选 thick → 填 Instant Client 目录 → DSN 填 tsoa 或 host:1521/tsoa

Windows 便携版：解压后双击 PushAll.exe，无需安装 Python。
首次运行如提示“未知发布者”，选择“更多信息 → 仍要运行”。
