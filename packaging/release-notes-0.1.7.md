数据库驱动打包修复

- 修复打包版测试 Oracle 数据源时提示 No module named 'oracledb'
- 内置 oracledb / pymysql / psycopg 驱动
- SQL 数据源可直接使用 Oracle / MySQL / PostgreSQL / SQLite
- 构建脚本会自动检查并安装数据库驱动

Windows 便携版：解压后双击 PushAll.exe，无需安装 Python。
首次运行如提示“未知发布者”，选择“更多信息 → 仍要运行”。
