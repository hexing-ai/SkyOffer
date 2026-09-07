# SkyOffer 项目资料

本目录包含 20 个候选项目的数据包和来源信息，用于 Beta 规则验证和公开示例复现。候选数据不等于正式发布的招生结论。

- `internal_manifest.json`：20 项候选数据索引，运行时必须经过质量门禁。`public_publishable=false` 表示未通过正式业务发布流程；公开源代码不会更改该状态，也不会把候选版本提升为正式版本。
- `manifest.json`：正式发布索引，目前为空。
- `programs/`：院校项目身份、要求字段、官网 Evidence、版本与复核信息。
- `historical_references/`：单独标注的 2026/27 历史参考，不用于 2027/28 分层。
- `program_field_registry.v1.json`：字段合同、状态、时效要求。
- `scope_snapshot.json`、`sources/`：院校范围与来源索引。
- `candidate_batches/`：候选导入数据及质量记录，相关脚本和测试用于验证它们。

详见仓库 `docs/DATA.md`。第三方官网材料的权利归原权利人，保留链接便于核验；申请时应以最新官方要求为准。
