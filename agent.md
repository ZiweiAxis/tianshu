# 天枢（Tianshu）子项目 Agent 约束

本文件为本子项目**自认的 Agent 行为约束**。在 Cursor、Claude Code CLI、Codex 中打开本子项目或在本目录下工作时，应自动加载并遵守本文件。若在紫微主仓（ziwei）下工作，须同时遵守根目录 **AGENTS.md**。

---

## 1. 身份与职责

- **天枢**：通信枢纽与身份控制平面；任务中枢，负责任务接收、路由、投递与（可选）持久化。
- 渠道与 Agent 管理（混合模式、发件人身份、回复链落库）在天枢侧实现；子项目只负责生产或消费任务。

---

## 2. 本子项目接到的开发任务：去哪里查

- **规划侧待办**（repo/文件）：本子项目 **ISSUE_LIST**（若有）、**_bmad-output/**；若可访问紫微主仓（ziwei），则还有根仓 **docs/open/technical/**、**_bmad-output/planning-artifacts/**（含《下一步执行清单》天枢节）。约定见 `ziwei/docs/open/technical/子项目任务下发与查看约定.md`。
- **与方案目标相关的具体任务**（天枢需要做的变更）：见本仓库 **`tianshu/docs/天枢-方案相关待办.md`**（当前仅小谛身份 T1）；非说明性，可按单执行。
- **运行态「要做的内容」**：当前仅通过接入该 Agent 的 Matrix 房间收天枢消息，见本仓库 **`tianshu/docs/任务与消费-实现状态.md`**。
- 任务归属与调度见 `ziwei/docs/open/technical/子项目任务与Agent调度约定.md`。

---

## 3. 必守规约

- 代码与配置仅限 **本目录（tianshu/）**；跨子项目改动由主仓或对应子项目 Agent 执行。
- 设计对齐：先读 **`tianshu/docs/design-alignment-with-ziwei.md`** 及根 `docs/open/technical/紫微智能体治理基础设施-技术方案.md`。
- BMAD：规划与产出放在 `tianshu/_bmad/`、`tianshu/_bmad-output/`；遵循根 `docs/open/technical/子项目任务与Agent调度约定.md`。
- 引用根技术文档时使用路径 **`ziwei/docs/open/technical/...`**。

---

## 4. 参考

- 子项目任务下发与查看：`ziwei/docs/open/technical/子项目任务下发与查看约定.md`
- 子项目任务与 Agent 调度：`ziwei/docs/open/technical/子项目任务与Agent调度约定.md`
- 规约与多 IDE 约定：`ziwei/docs/open/technical/规约与多IDE约定.md`
