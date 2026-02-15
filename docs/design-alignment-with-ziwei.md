# 天枢与紫微主项目设计方案对齐

**版本**：v1.0  
**日期**：2026-02-13  
**目的**：天枢子项目（tianshu）与 ziwei 主项目架构文档、BMAD 多子项目管理实践保持一致；供天枢子 agent 与开发者在规划与实现时引用。

---

## 1. 对齐依据

| 文档 | 路径 | 用途 |
|------|------|------|
| 紫微智能体治理基础设施 技术方案 | `ziwei/docs/open/technical/紫微智能体治理基础设施-技术方案.md` | 总体架构、天枢/谛听/太白职责、DID/链/接口约定 |
| 紫微架构图 | `ziwei/docs/open/technical/紫微智能体治理基础设施-架构图.drawio` | 组件关系与边界 |
| BMAD 多子项目管理最佳实践 | `ziwei/docs/open/technical/BMAD-多子项目管理-最佳实践.md` | 每子项目 _bmad、架构工作流、根目录共享文档 |
| 谛听 BMAD 架构 | `ziwei/diting/_bmad-output/planning-artifacts/architecture.md` | 谛听组件边界、接口、与天枢集成时的约定 |
| 谛听 Issue/扩展 | `ziwei/diting/ISSUE_LIST.md` | 跨子项（如 I-018 天枢对接谛听 DID） |

天枢子 agent 在进行 BMAD 规划（PRD、architecture、epics/stories）或实现前，应**优先阅读上述文档**，确保设计与主项目一致。

---

## 2. 天枢在紫微中的定位（与技术方案 2 节对齐）

### 2.1 角色

- **名称**：天枢 · 通信与身份底座  
- **职责**（摘自技术方案 2.1）：
  - 为每个智能体提供**全局唯一、不可伪造**的数字身份
  - 作为所有人类-AI、AI-AI 通信的**可信路由枢纽**
  - 与企业 IM（飞书、钉钉、企微）无缝集成，作为审批触达通道
  - 消息传递**端到端加密**，每条消息携带身份签名

### 2.2 关键技术

| 能力 | 技术方案约定 | 天枢当前实现/规划 |
|------|--------------|-------------------|
| 通信底座 | Matrix 联邦协议、端到端加密 | `src/matrix/`，飞书 ↔ Matrix 桥接 |
| 身份 | 区块链 DID、环境指纹绑定 | `src/identity/`（agent_id、owner 绑定）；**链上 DID 未实现**，依赖谛听链接口（见 4） |
| 企业 IM | 飞书/钉钉/企微适配器 | 飞书已实现（`bridge/`、channel_adapter）；钉钉/企微为扩展 |
| 审批触达 | 审批事件 → IM 卡片 → 回调 | 与谛听配合：谛听决策审批，天枢负责触达与回调 |

### 2.3 边界

- **天枢不运维链**：DID 注册/查询通过**谛听暴露的链上 DID 接口**完成（技术方案 3.6）。
- **天枢不做法策决策**：策略与审批等级由谛听（Cedar、分级审批）负责；天枢负责注册/心跳、消息路由、审计上报、审批触达与回调。

---

## 3. 与 BMAD 的配合方式（与最佳实践对齐）

### 3.1 目录

- **天枢自有**：`tianshu/_bmad/`、`tianshu/_bmad-output/`（与「每子项目一 _bmad」一致）。
- **根目录共享**：`ziwei/docs/open/technical/` 下技术方案与架构图为跨子项目统一依据；规划时引用，不复制为天枢本地权威副本。

### 3.2 工作流

- **Phase 2 Planning**：若有新 Epic/大功能，PRD 或 epic 需与 `ziwei/docs/open/technical/紫微智能体治理基础设施-技术方案.md` 中天枢职责与接口一致。
- **Phase 3 Solutioning**：架构/ADR 需显式引用主项目技术方案与（若涉及）谛听 architecture；子项目级 ADR 放在 `tianshu/_bmad-output/planning-artifacts/` 或 `tianshu/docs/`。
- **Phase 4 Implementation**：Story 与实现保持在 `ziwei/tianshu/` 内；跨子项目（如调用谛听 DID）在 Issue/Story 中注明依赖（如 diting I-017、I-018）。

### 3.3 文档产出位置

- 规划类：`tianshu/_bmad-output/planning-artifacts/`（如 architecture、epics、对齐/偏差分析）。
- 与主项目对齐的稳定说明：`tianshu/docs/`（如本文档、deploy、e2e-testing）。

---

## 4. 与谛听的接口与扩展（与技术方案 3.6、diting ISSUE_LIST 对齐）

### 4.1 当前已用接口

| 能力 | 环境变量/配置 | 说明 |
|------|----------------|------|
| 审计上报 | `DITING_AUDIT_URL` | 消息审计上报 |
| 审批回调 | `DITING_APPROVE_CALLBACK_URL` | 天枢接收谛听/审批回调 |
| 注册后初始化权限 | `DITING_INIT_PERMISSION_URL` | Agent 注册完成后通知谛听 |
| Sub-agent 登记 | `DITING_SUB_AGENT_REGISTER_URL`（可选） | 主 Agent 登记 Sub-agent 后可选通知谛听 |
| **I-018 链上 DID** | `DITING_CHAIN_URL` | 注册时 POST /chain/did/register；上线登记时异步刷新 DID（与谛听 I-017 联调） |

### 4.2 已实现（I-018 对接谛听 DID）

| 能力 | 接口约定 | 实现位置 |
|------|----------|----------|
| DID 链上注册/查询 | 谛听暴露 `POST /chain/did/register`、`GET /chain/did/{did}` | 谛听 I-017（diting） |
| 天枢调用 DID | 注册流程调用 DID 注册；上线登记时异步刷新 | `src/diting_client/chain_did.py`、`human_initiated`、`agent_presence` |

DID 命名：`did:ziwei:local:{agent_id}`；请求体与谛听 I-016 §3 一致（id、publicKey、environmentFingerprint、owner、status）。

---

## 5. 天枢子 agent 使用本对齐文档的约定

- **规划或架构讨论**：先阅读 `ziwei/docs/open/technical/紫微智能体治理基础设施-技术方案.md` 第 2 节（天枢）及 3.6（私有链/谛听）；再阅读本文档。
- **与谛听联调或跨子项目 Story**：查阅 `ziwei/diting/ISSUE_LIST.md`（如 I-017、I-018）及谛听 `architecture.md` 中与天枢相关的接口与部署约定。
- **BMAD 产出**：PRD/architecture/epics 中涉及身份、DID、链、审计、审批触达的部分，须与本文档及主项目技术方案一致；若有偏差，在 `_bmad-output/planning-artifacts/` 下用偏差/对齐文档记录并说明原因。

---

**文档结束**
