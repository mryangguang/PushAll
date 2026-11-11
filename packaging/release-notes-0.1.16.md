## 修复：SQL 数据源结尾分号导致 ORA-00911

- 数据源 SQL 结尾带分号时（从 SQL Developer / PLSQL Developer 直接粘贴很常见），Oracle 会报 `ORA-00911: invalid character`
- 现在会自动去掉 SQL 结尾的分号，粘贴即可用，不必手动删除
- ORA-00911 的报错提示更明确：会提示「删除结尾分号 / 检查是否混入中文标点」
- SQL 编辑框补充了说明文字

## 说明

- 更新只替换程序文件，`data`、`plugins`、`logs` 均保留
