# 存储后端选型说明（E11-S4）

## 为什么先做 SQLite，而不是直接用 MySQL/PostgreSQL？

- **零额外依赖**：Python 标准库自带 sqlite3，不需要单独起数据库进程，适合单机与本地联调。
- **单文件**：一个文件即一库，卷挂载简单，备份与迁移直观。
- **快速落地**：先打通「有持久化」；抽象层已支持多后端，后续切 PG/MySQL 只改配置。

## 什么时候用 PostgreSQL？

- 多实例部署、生产环境、并发写、与 Synapse 生态一致（Synapse 推荐 PG）。
- 配置：TIANSHU_STORAGE=postgres，TIANSHU_PG_DSN=postgresql://user:pass@host/db

## 什么时候用 MySQL？

- 现网已是 MySQL 或团队标准库为 MySQL 时。
- 配置：TIANSHU_STORAGE=mysql，TIANSHU_MYSQL_DSN=...

同一套业务通过 get_backend() 访问，切换后端只需环境变量。
