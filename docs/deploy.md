# 天枢部署说明（E11 可部署系统）

## 一键启动（Podman / Docker）

在项目根目录执行：

```bash
# Podman
podman-compose up -d

# 或 Docker
docker compose up -d
```

将启动：

- **tianshu**：天枢核心（Bridge + 健康探针），端口 8080（/health, /ready）
- **synapse**：Matrix Home Server，端口 8008；首次启动自动生成配置到卷 `synapse-data`

## 首次使用：Matrix 网关用户与 Token

天枢以「网关用户」身份连接 Synapse，需在 Synapse 中存在该用户并持有 access token。

**使用根目录一键启动时**（`ziwei` 仓库 `deploy/docker-compose.integration.yml`）：**无需填写 `MATRIX_GATEWAY_TOKEN`**。Compose 会传入 `REGISTRATION_SHARED_SECRET`，天枢启动时自动向 Synapse 注册 `@gateway:matrix.local` 并将 token 写入卷（如 `/data/gateway_token`），下次启动直接读取。仅当自举失败（如 Synapse 未就绪、secret 不一致）或网关用户已存在但 token 文件丢失时，才需按下列步骤手动处理。

**仅部署天枢或接已有 Synapse 时**，需手动注册并配置 token：

1. 等 Synapse 健康后再操作：
   ```bash
   podman-compose exec synapse register_new_matrix_user -c /data/homeserver.yaml http://localhost:8008
   ```
   若镜像内无该脚本，可在宿主机用 Synapse 管理 API 或 Web 客户端注册用户（如 `@gateway:matrix.local`），并获取 access_token。

2. 在项目根目录创建或编辑 `.env`，填入：
   ```env
   MATRIX_HOMESERVER=http://synapse:8008
   MATRIX_GATEWAY_USER=@gateway:matrix.local
   MATRIX_GATEWAY_TOKEN=syt_xxxxxxxx
   FEISHU_APP_ID=...
   FEISHU_APP_SECRET=...
   ```

3. 重启天枢使配置生效：`podman-compose up -d tianshu`

## 健康与就绪

- **GET http://localhost:8080/health**：存活探针（liveness）
- **GET http://localhost:8080/ready**：就绪探针（readiness），当前与 health 一致，可扩展为检查 Matrix 连接

## 仅启动天枢（外接已有 MHS）

若已有 Matrix Home Server，只需启动天枢：

```bash
# 在 .env 中设置 MATRIX_HOMESERVER、MATRIX_GATEWAY_USER、MATRIX_GATEWAY_TOKEN 指向已有 MHS
podman-compose up -d tianshu
```

或注释掉 compose.yaml 中 synapse 服务及 tianshu 的 depends_on，再 `up -d`。

## 构建镜像

```bash
podman build -t tianshu:latest -f Containerfile .
# 或
docker build -t tianshu:latest -f Containerfile .
```

## 持久化（E11-S4）

存储抽象层支持 **memory / sqlite / postgres / mysql**，通过环境变量切换：

| 后端 | 说明 | 环境变量 |
|------|------|----------|
| **memory** | 默认，进程内内存，重启丢失 | 不设或 `TIANSHU_STORAGE=memory` |
| **sqlite** | 单文件，单实例/本地首选，挂卷持久化 | `TIANSHU_STORAGE=sqlite`，`TIANSHU_SQLITE_PATH=/data/tianshu.db` |
| **postgres** | 多实例共享、生产推荐 | `TIANSHU_STORAGE=postgres`，`TIANSHU_PG_URL=postgresql://user:pass@host:5432/tianshu` |
| **mysql** | 与 PG 同构，适合已有 MySQL | `TIANSHU_STORAGE=mysql`，`TIANSHU_MYSQL_*` |

选型理由：SQLite 零额外服务、单机联调方便；PostgreSQL 多实例/生产常用、与 Synapse 等生态一致；MySQL 可按需选用。业务模块（身份、关系、审批、投递日志）迁移至存储层后，重启/多副本即可共享同一库。
