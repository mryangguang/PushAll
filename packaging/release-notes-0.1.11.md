修复更新时内置插件不更新

- 修复更新器误排除 _internal/app/plugins 的问题
- 内置插件现在会随版本正确更新
- update.log 记录本次复制的内置插件数量
- Oracle 数据源插件（含 config_dir / 11g 提示）现在能随更新生效

Windows 便携版：解压后双击 PushAll.exe，无需安装 Python。
首次运行如提示“未知发布者”，选择“更多信息 → 仍要运行”。
