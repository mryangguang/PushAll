## 开机自动启动（新增）

- 设置页新增「启动」开关：开启后，登录 Windows 会自动在系统托盘运行 PushAll，不弹主窗口
- 写入当前用户注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`，无需管理员权限；关闭即删除
- 程序目录移动后，下次启动会自动更新注册表里的启动路径

## 说明

- 更新只替换程序文件，`data`、`plugins`、`logs` 均保留
