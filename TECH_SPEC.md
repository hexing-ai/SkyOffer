# SkyOffer 技术说明

完整架构见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，安装配置见 [docs/INSTALLATION.md](docs/INSTALLATION.md)。

- 前端：Next.js App Router、React、TypeScript、Zod、Tailwind CSS 与 CSS Modules。
- 后端：FastAPI、Pydantic、SQLAlchemy、Alembic；本地 SQLite，生产 PostgreSQL。
- 规则：确定性函数求值；满足、未满足、缺信息、人工核验、不适用五态。
- 模型：DeepSeek 官方接口；受限解释、结构与语义校验、可观察的保守降级。
- 数据：院校项目、字段级 Evidence、候选版本、人工复核及发布流程。
- 公开演示：Next.js 静态导出、合成档案、固定规则快照；不包含后端或密钥。

## 核心接口

| 接口 | 职责 |
| --- | --- |
| `GET /api/v1/programs` | 项目列表 |
| `GET /api/v1/programs/{program_ref}` | 项目详情与官网依据 |
| `POST /api/v1/selection-advice` | 对当前背景生成选校建议 |
| `POST /api/v1/profile-analysis` | 资料整理与缺口分析 |
| `GET /api/v1/health` | 进程健康 |
| `GET /api/v1/ready` | 模型配置、数据库和项目数据就绪 |

内部维护、版本审核及验收接口是开发与运营工具，生产部署必须限制访问。公开 Demo 不部署这些接口。
