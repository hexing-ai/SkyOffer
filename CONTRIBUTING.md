# 参与 SkyOffer

欢迎提交修复、界面改进和数据来源更新。先阅读 README 的运行步骤，再在独立分支修改。

1. 清楚描述触发条件、实际表现和预期结果。
2. 后端修改运行 `pytest -q`；前端修改运行 lint、typecheck、test 和 build。演示变更同时运行 `npm run build:demo`。
3. 新增院校规则必须附官方 URL、适用学年、核验日期和说明；不要用经验推断替代官网证据。
4. 示例只使用合成档案；不提交密钥、个人材料、数据库或日志。
5. PR 说明影响与验证方式。数据结构及规则语义变化应有回归测试。

演示快照可以通过 `python -m backend.scripts.export_demo` 重建。页面截图由 Demo 工作流在 Chromium 中生成。

共享 CI 使用 `pytest -q -m "not performance"` 验证功能，并单独报告性能目标。`pytest -q` 仍会执行包括 100 ms 门槛在内的完整测试；性能复核应使用受控硬件，详见架构文档。
