# SkyOffer 生产部署

GitHub Pages 上的公开 Demo 仅部署静态示例，不接收个人资料，不调用模型，不需要数据库。

## 自行部署完整服务

`deploy/compose.production.yaml` 编排 Next.js、FastAPI 与 PostgreSQL。配置参考 `deploy/production.env.example`。前端端口默认只绑定本机 3200，后端和数据库不直接暴露主机端口。

```bash
cp deploy/production.env.example deploy/production.env
# 本机编辑并填写真实配置
docker compose --env-file deploy/production.env -f deploy/compose.production.yaml up --build -d
```

后台启动时执行迁移、20 项数据引导与就绪校验。生产模式要求 PostgreSQL、显式 Host、JSON 日志、限流和模型配置。数据库持久化在 Compose volume 中，不随代码上传。

## 公开真实分析服务前

现有配置不是完整的多用户 SaaS 安全边界。不要直接把本机端口转发到公网。应在前端入口配置 HTTPS 和认证网关；只允许实际用户需要的 API 方法及路径，阻止内部维护、版本写入与阶段验收接口。开发接口尚未实现用户级权限系统。

反向代理允许的用户 API 可从 `TECH_SPEC.md` 表格中选择。限流目前为单实例内存实现，多实例需要共享限流及模型预算控制。配置适当的日志、备份与告警，不记录用户原始材料或密钥。

## 验证与回滚

先在隔离数据库运行数据引导与 `/api/v1/ready` 检查；备份数据库后再切换版本。`SKYOFFER_RELEASE` 标识容器版本。回滚应用镜像不等于回滚数据库结构，迁移变更需单独评估，不应删除持久卷。

Compose 中的数据库口令与连接串必须一致；连接串中的特殊字符需要 URL 编码。API Key 只存在于后端环境变量。
