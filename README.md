# ERP Material Master Agent

用自然语言查询 ERP 物料、检查重复编码，并在新建物料前给出录入建议。

当前内置用友 NCC 数据源，ERP 数据库只读。检索索引和管理员反馈保存在 PostgreSQL。

## 功能

- 按物料编码精确查询。
- 按名称或规格型号查询已有物料。
- 识别“番茄 / 西红柿”类别名和一物多码。
- 新建前提示重复风险、物料状态和录入建议。
- 支持增量索引、失败续传和 SSE 流式对话。

## Docker 启动

复制并修改配置：

```bash
cp .env.example .env
```

`.env.example` 默认同时启动 Agent 和 PostgreSQL 17 + pgvector：

```bash
docker compose up -d --build
```

使用外部 PostgreSQL 时，把 `MATERIAL_POSTGRES_URL` 改为实际地址，并把 `COMPOSE_PROFILES` 留空。

打开：

- 对话页面：<http://127.0.0.1:8000/>
- 接口文档：<http://127.0.0.1:8000/docs>

查看日志：

```bash
docker compose logs -f material-agent postgres
```

停止：

```bash
docker compose down
```

## 本地启动

需要 Python 3.11+、PostgreSQL + pgvector。使用 NCC 数据源时还需要 Microsoft ODBC Driver 18 for SQL Server。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

## 配置

| 变量 | 说明 |
|---|---|
| `MATERIAL_CHAT_MODEL` | 对话模型名称 |
| `MATERIAL_CHAT_BASE_URL` | OpenAI-compatible 对话接口地址 |
| `MATERIAL_CHAT_API_KEY` | 对话接口密钥 |
| `MATERIAL_EMBEDDING_MODEL` | Embedding 模型名称 |
| `MATERIAL_EMBEDDING_API_URL` | Embedding 接口完整地址 |
| `MATERIAL_EMBEDDING_API_KEY` | Embedding 接口密钥 |
| `MATERIAL_EMBEDDING_DIMENSION` | 向量维度 |
| `MATERIAL_SOURCE_TYPE` | ERP 数据源，当前支持 `ncc` |
| `MATERIAL_SOURCE_URL` | ERP 数据库连接地址 |
| `MATERIAL_POSTGRES_URL` | PostgreSQL 完整连接地址 |
| `COMPOSE_PROFILES` | `postgres` 表示部署内置 PostgreSQL；留空表示使用外部 PostgreSQL |
| `POSTGRES_DB` | Docker PostgreSQL 数据库名 |
| `POSTGRES_USER` | Docker PostgreSQL 用户 |
| `POSTGRES_PASSWORD` | Docker PostgreSQL 密码 |
| `POSTGRES_PORT` | Docker PostgreSQL 宿主机端口 |

## 建立索引

在对话页面点击“添加向量索引”，或调用：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/materials/index/rebuild
```

首次读取全部物料，后续根据 `modified_at` 增量更新。

## 接口

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/v1/agent/chat` | 自然语言对话 |
| `POST` | `/api/v1/agent/chat/stream` | SSE 流式对话 |
| `POST` | `/api/v1/materials/search` | 名称和规格检索 |
| `POST` | `/api/v1/materials/validate` | 新建物料查重 |
| `POST` | `/api/v1/materials/feedback` | 记录管理员确认结果 |
| `POST` | `/api/v1/materials/index/rebuild` | 触发索引同步 |
| `GET` | `/api/v1/materials/index/status` | 查询索引任务状态 |

自然语言对话示例：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"查询物料代码 170300000068"}'
```

## 接入其他 ERP

新数据源需实现 `MaterialSource` 的两个方法：

```python
def fetch_materials(modified_since=None): ...
def fetch_codes(): ...
```

Adapter 负责把 ERP 字段映射为 `MaterialRecord`，然后在 `src/sources/factory.py` 注册。检索和 Agent 代码不需要修改。

## 目录

```text
src/
├── web/        # FastAPI 和对话页面
├── agent/      # LangChain Agent
├── materials/  # 物料检索与判重
├── indexing/   # PGVector 索引和同步
└── sources/    # ERP 数据源
```

ERP 连接账号必须只读。Agent 不会创建、修改、启用或停用 ERP 物料。
