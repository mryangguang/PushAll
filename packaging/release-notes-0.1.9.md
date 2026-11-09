中文路径更新修复

- 更新器改为由新版本 exe 用 Python 复制文件，不再依赖 cmd / robocopy
- 修复安装目录含中文（例如 C:\Users\...\软件\PushAll）时更新脚本不执行、版本一直是旧版的问题
- 复制完成后自动重启；data、plugins、logs 原样保留
- 更新日志写入 logs\update.log，包含源目录、目标目录和复制结果

Windows 便携版：解压后双击 PushAll.exe，无需安装 Python。
首次运行如提示“未知发布者”，选择“更多信息 → 仍要运行”。
