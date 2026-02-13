# 天枢（Tianshu）

飞书 ↔ Matrix 消息桥接系统，集成谛听审计服务。

## 项目概述

天枢是一个消息枢纽系统，负责：
- 飞书与 Matrix 之间的双向消息桥接
- 用户身份映射与房间管理
- 与独立谛听系统交互进行消息审计

## 技术栈

- Python 3.8+
- 飞书 Stream SDK (lark-oapi)
- Matrix 客户端 (matrix-nio)
- 异步 HTTP (aiohttp)

## 项目结构

```
tianshu/
├── src/
│   ├── main.py                   # 应用入口
│   ├── config.py                 # 配置加载
│   ├── bridge/
│   │   └── feishu.py            # 飞书适配层
│   ├── matrix/
│   │   └── client.py            # Matrix 客户端
│   ├── core/
│   │   ├── translator.py        # 消息格式转换
│   │   ├── user_mapper.py       # 用户 ID 映射
│   │   └── room_manager.py      # 房间生命周期管理
│   └── diting_client/
│       ├── reporter.py          # 上报审计消息
│       └── callback_server.py   # 接收谛听回调
├── scripts/
│   └── create_matrix_user.py   # 辅助脚本
├── tests/
├── .env.example                 # 环境变量模板
├── .gitignore
├── requirements.txt
└── README.md
```

## 快速开始

### 1. 创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate   # Windows
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入实际配置
```

### 4. 运行

```bash
python src/main.py
```

## 配置说明

参考 `.env.example` 中的注释配置：
- 飞书应用凭证
- Matrix 服务器信息
- 房间策略（独立房间 vs 共享房间）
- 谛听服务接口

## 开发指南

（待补充）

## License

（待定）
