# 天枢端到端测试展开指南

## 1. 目标与范围

端到端测试验证**多模块串联**的完整流程，确保真实使用路径在内存/持久化、有无真实 Matrix/飞书 等环境下均可验证。

| 层级 | 说明 | 当前 |
|------|------|------|
| **单测** | 单模块/单函数，mock 依赖 | `tests/test_identity.py`、`test_bridge.py`、`test_delivery.py` 等 |
| **集成/串联** | 跨模块同进程，不启外部服务 | 部分在单测中覆盖；可增 `test_e2e_flows.py` |
| **E2E（真实依赖）** | 启动 Matrix（Synapse）+ 天枢，可选飞书 | 需 `compose up` 后跑脚本或手动 |

---

## 2. 建议的 E2E 流程（按优先级）

### 2.1 不依赖真实 Matrix/飞书（CI 可跑）

在**内存存储**下，用代码串联调用，不启动 Bridge 主进程、不连真实 MHS/飞书：

| 流程 | 步骤 | 验证点 |
|------|------|--------|
| **身份与注册** | 登记 Owner → 人发起注册 Agent → 绑定 → 查询关系 | `list_relationships_for_diting`、`get_owner_agent_list` 含新 Agent |
| **审批** | 发起审批请求（仅内存）→ 回调 → 查结果 | `get_approval_result` 幂等、结果一致 |
| **投递与日志** | 构造投递事件 → 经 delivery_log 记录 → 查询 | `query_delivery_log`、`get_delivery_status` 有记录 |
| **协作链** | 主 Agent 登记 Sub-agent → 查协作关系与摘要 | `get_agent_relationships`、`get_collaboration_chains_summary` 含主从 |
| **健康** | 启动健康 HTTP（短生命周期）→ GET /health, /ready | 返回 200、body 含 ok/ready |

上述流程用 **pytest** 写在 `tests/test_e2e_flows.py`，单进程、无真实网络，适合 CI。

**已实现用例：**

| 用例 | 说明 |
|------|------|
| `test_e2e_health_and_ready` | 健康探针 `/health`、`/ready` 返回 200 与约定 JSON |
| `test_e2e_identity_registration_flow` | Owner 登记 → 人发起注册 Agent → 绑定 → 关系/Owner 列表可见 |
| `test_e2e_approval_callback_flow` | 审批回调写入 → 可查询；同一 request_id 幂等 |
| `test_e2e_delivery_log_flow` | 投递开始/完成记录 → 按 delivery_id 与 receive_id 查询 |
| `test_e2e_collaboration_chain_flow` | 主从登记 → 协作关系与协作链摘要（需先绑定 Owner） |

运行：`pytest tests/test_e2e_flows.py -v`

### 2.2 依赖真实 Matrix（可选）

在 **compose 已启动（tianshu + synapse）** 且配置好 `MATRIX_GATEWAY_USER`、`MATRIX_GATEWAY_TOKEN` 后：

| 流程 | 步骤 | 验证点 |
|------|------|--------|
| **连接与投递** | MatrixClient.connect → create_room → send_delivery（approval_request） | Bridge 消费后飞书侧收到卡片（需飞书配置）或至少无异常 |
| **Agent 路由** | 注册 Agent → ensure_room_for_agent → send_agent_message | 目标 Room 收到事件（可用第二客户端或 API 查） |

建议用 **独立脚本**（如 `tests/run_e2e_matrix.py`）或 **pytest + 环境变量** 控制是否执行（如 `E2E_MATRIX=1 pytest tests/test_e2e_matrix.py`），CI 默认不跑。

### 2.3 依赖飞书（可选）

需要飞书应用、回调 URL、真实群/会话时，用于验收「飞书收消息 / 回调天枢」：

- 手动或脚本：发飞书事件到天枢回调 → 检查 Matrix Room 是否收到；或天枢发投递 → 检查飞书是否收到卡片。
- 可放在文档或运维手册，不作为 CI 必跑。

---

## 3. 如何展开（执行顺序）

1. **先跑通「无真实依赖」的串联测试**  
   - 在 `tests/test_e2e_flows.py` 中实现 2.1 的流程，全部用内存存储、不启 Matrix。  
   - 命令：`pytest tests/test_e2e_flows.py -v`

2. **再选「真实 Matrix」的 E2E**  
   - 本地或 CI 中 `podman-compose up -d`，配置 `.env` 中 Matrix 凭证。  
   - 运行 `tests/run_e2e_matrix.py` 或 `E2E_MATRIX=1 pytest tests/test_e2e_matrix.py`（若实现）。  
   - 验证：连接、发事件、Bridge 消费无报错；可选：再验证飞书收到。

3. **最后按需补「飞书 + 谛听」**  
   - 在测试环境配置飞书 App、谛听 URL，用 2.3 的流程做手工或脚本验收，并记录在 `docs/deploy.md` 或运维文档。

---

## 4. 环境与标记

- **默认**：`TIANSHU_STORAGE=memory`，不依赖数据库。  
- **持久化**：E2E 若需验证落库，可设 `TIANSHU_STORAGE=sqlite`、`TIANSHU_SQLITE_PATH=/tmp/e2e.db`，测试后删除文件。  
- **真实 Matrix**：用环境变量控制，例如 `E2E_MATRIX=1` 或 `RUN_E2E_MATRIX=true`，CI 中不设则跳过。

---

## 5. 与单测的边界

- **单测**：覆盖模块内逻辑、边界条件、mock 外部依赖。  
- **E2E**：覆盖「用户/运维可见」的完整路径，尽量少 mock，用真实存储与（可选）真实 Matrix。  
- 不重复：单测已覆盖的纯逻辑不必在 E2E 再测一遍，E2E 侧重串联与契约（如 API 返回结构、投递状态一致）。

---

*端到端测试展开指南 v1.0，随实现补充用例与命令。*
