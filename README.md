# 线上仲裁证据交换服务

## 项目简介

本服务是基于 FastAPI + PostgreSQL 构建的线上仲裁证据交换系统，用于管理仲裁案件中的证据提交、交换、质证和庭审引用全流程。

## 原始需求

> 请开发线上仲裁证据交换服务，使用 FastAPI 和 PostgreSQL 管理案件、申请人、被申请人、代理人、证据目录、文件上传、交换批次、质证意见、补充材料和庭审引用。申请人提交合同、聊天记录、付款凭证、验收材料和损失说明；被申请人按批次查看并提交真实性、关联性、合法性质证；仲裁秘书审核格式、脱敏、页码和截止时间；仲裁员查看证据链条和争议焦点。服务要处理大文件断点上传、证据撤回、超期补交、双方可见范围、文件哈希、目录顺序冻结和庭审引用留痕。

## 技术栈

- **后端框架**: FastAPI 0.115
- **数据库**: PostgreSQL 16
- **ORM**: SQLAlchemy 2.0
- **认证**: JWT (python-jose) + bcrypt
- **文件处理**: 分块断点上传、SHA-256 哈希校验
- **部署**: Docker + Docker Compose

## 功能模块

| 模块 | 说明 |
|------|------|
| 案件管理 | 创建、查询、更新、删除仲裁案件，支持案件状态流转 |
| 当事人管理 | 申请人、被申请人、代理人的分配和管理 |
| 证据目录 | 多级目录结构，支持目录冻结/解冻 |
| 文件上传 | 大文件分块断点续传，自动计算 SHA-256 哈希 |
| 证据管理 | 支持合同、聊天记录、付款凭证、验收材料、损失说明等类型 |
| 交换批次 | 按批次管理证据交换，设置截止时间和可见范围 |
| 质证意见 | 被申请人提交真实性、关联性、合法性三性意见 |
| 证据审核 | 仲裁秘书审核格式、脱敏、页码合规性 |
| 补充材料 | 证据补充关联，标记补交和超期补交 |
| 庭审引用 | 庭审中引用证据，记录争议焦点和引用内容，留痕可追溯 |
| 证据链条 | 仲裁员视角查看完整证据链路和质证情况 |

## 启动方式

### 前置要求

- Docker 20.10+
- Docker Compose v2.0+
- 或本地 Python 3.12+ + PostgreSQL 14+

### Docker 一键启动（推荐）

#### 1. 启动服务

```bash
docker compose up --build
```

如需后台运行：

```bash
docker compose up --build -d
```

#### 2. 访问地址

- API 服务地址：http://localhost:8000
- Swagger 文档：http://localhost:8000/docs
- ReDoc 文档：http://localhost:8000/redoc
- PostgreSQL：localhost:5432

#### 3. 停止服务

```bash
docker compose down
```

如需清除数据卷：

```bash
docker compose down -v
```

### 本地启动方式

#### 1. 安装依赖

```bash
pip install -r requirements.txt
```

#### 2. 配置环境变量

```bash
copy .env.example .env
```

根据需要修改 `.env` 中的数据库连接信息。

#### 3. 启动 PostgreSQL

请确保本地已启动 PostgreSQL，并创建数据库：

```sql
CREATE DATABASE arbitration_evidence;
```

#### 4. 启动服务

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问地址：http://localhost:8000/docs

## API 使用说明

### 1. 注册用户

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "secretary1",
    "email": "secretary@example.com",
    "full_name": "仲裁秘书",
    "password": "test123456",
    "role": "secretary"
  }'
```

### 2. 登录获取 Token

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "secretary1",
    "password": "test123456"
  }'
```

### 3. 角色说明

| 角色值 | 说明 | 权限范围 |
|--------|------|----------|
| `claimant` | 申请人 | 提交证据、查看质证 |
| `respondent` | 被申请人 | 查看证据、提交质证意见 |
| `agent` | 代理人 | 代表当事人操作 |
| `secretary` | 仲裁秘书 | 审核证据、管理批次、冻结目录 |
| `arbitrator` | 仲裁员 | 查看证据链条、争议焦点 |
| `admin` | 管理员 | 全部权限 |

### 4. 大文件分块上传流程

1. **初始化上传会话**：`POST /api/upload/init`
2. **上传分块**：`POST /api/upload/chunk/{upload_id}/{chunk_number}`
3. **查询状态**：`GET /api/upload/status/{upload_id}`
4. **创建证据记录**：使用 upload_id 创建证据记录

分块大小固定为 5MB，支持断点续传，服务端记录已上传的分块编号，客户端可从断点继续上传。

### 5. 核心业务流程

1. 仲裁秘书创建案件 → 添加申请人、被申请人、代理人 → 创建证据目录
2. 申请人分块上传文件 → 创建证据记录（合同/聊天记录/付款凭证/验收材料/损失说明）→ 提交
3. 仲裁秘书审核证据格式、脱敏、页码 → 通过后证据可被对方查看
4. 仲裁秘书创建交换批次并激活 → 设置截止时间
5. 被申请人按批次查看证据 → 提交真实性、关联性、合法性质证意见
6. 支持证据撤回、超期补交、补充材料关联
7. 庭审中仲裁员引用证据 → 记录争议焦点 → 形成证据链条
8. 目录顺序冻结后不可调整，保障证据目录稳定性

## 目录结构

```
.
├── app/
│   ├── __init__.py
│   ├── main.py              # 主应用入口
│   ├── config.py            # 配置
│   ├── database.py          # 数据库连接
│   ├── models.py            # SQLAlchemy 数据模型
│   ├── schemas.py           # Pydantic 数据模型
│   ├── auth.py              # JWT 认证与权限
│   └── routers/
│       ├── __init__.py
│       ├── auth.py              # 认证路由
│       ├── cases.py             # 案件管理
│       ├── parties.py           # 当事人管理
│       ├── agents.py            # 代理人管理
│       ├── catalogs.py          # 证据目录
│       ├── upload.py            # 文件上传（断点续传）
│       ├── evidences.py         # 证据管理
│       ├── batches.py           # 交换批次
│       ├── cross_examinations.py # 质证意见
│       ├── reviews.py           # 证据审核
│       ├── supplements.py       # 补充材料
│       └── hearings.py          # 庭审引用
├── uploads/                 # 文件上传目录
├── Dockerfile               # 应用容器
├── docker-compose.yml       # 编排配置
├── .dockerignore
├── .env.example             # 环境变量示例
├── requirements.txt
└── README.md
```

## 注意事项

1. 生产环境务必修改 `SECRET_KEY` 为强随机字符串
2. 建议配置 HTTPS，避免传输中证据文件被窃听
3. 大文件上传请确保磁盘空间充足，默认单文件最大 1GB
4. 证据目录冻结后，其下所有子目录自动冻结，无法新增或修改
5. 已撤回的证据无法被质证或庭审引用，但保留历史记录可审计
6. 超期补交的证据会被标记 `is_overdue=true`，仲裁秘书可酌情决定是否接受
