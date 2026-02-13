# Agent 发现天枢端点（E4-S6 契约）

## 目的

初生 Agent 通过开放、业界通用方式发现天枢端点（Matrix Home Server 或 HTTP API 入口），以便发起注册或上线。

## 发现方式

### 1. Matrix Home Server

- 天枢底层基于 Matrix，Agent 连接的是 **Matrix Home Server（MHS）**。
- 若 MHS 支持 [.well-known](https://spec.matrix.org/v1.1/server-server-api/#well-known-uri) / federation，Agent 可按 Matrix 规范发现 MHS 地址。
- 若由天枢统一配置，则天枢部署时暴露「端点发现」URL，返回包含 `matrix_homeserver` 的 JSON。

### 2. 天枢端点发现 URL（推荐）

部署天枢时，应暴露以下之一（或等价路径），返回 **JSON**：

- `GET /.well-known/tianshu-matrix`
- `GET /api/v1/discovery`

**响应示例：**

```json
{
  "matrix_homeserver": "https://matrix.example.com",
  "api_base": "https://tianshu.example.com/api/v1",
  "version": "1.0"
}
```

| 字段 | 说明 |
|------|------|
| `matrix_homeserver` | Matrix Home Server 根 URL，Agent 用于登录、Room、Event |
| `api_base` | 可选。天枢 HTTP API 根地址（注册、上线、心跳等） |
| `version` | 契约版本 |

Agent 可据此解析 Home Server 或 API 入口，再发起注册或上线。

## 程序化获取（同仓调用）

若 Agent 与天枢同仓或已知配置，可直接调用：

```python
from src.discovery import get_discovery_payload
payload = get_discovery_payload()
# payload["matrix_homeserver"], payload.get("api_base")
```

## 与 Matrix 的关系

- 天枢不替代 Matrix；Agent 与 Matrix 的协议交互（登录、Room、Event）仍指向 **matrix_homeserver**。
- 天枢的「注册、上线、心跳」等业务接口可走 HTTP（api_base）或经 Matrix 约定事件，由实现与契约定。
