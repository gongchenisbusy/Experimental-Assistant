# EAv0.1-build

这是 EA v0.1 的正式构建项目文件夹。

新 agent 打开本项目后，先阅读：

1. `工作指南/README.md`
2. `工作指南/docs/EA_V0_1_BUILD_PACKAGE_MANIFEST.md`
3. `工作指南/docs/EA_V0_1_GIT_WORKFLOW.md`
4. `工作指南/docs/EA_V0_1_AGENT_TEAM_SETUP.md`
5. `工作指南/docs/EA_V0_1_SKILL_SETUP.md`

重要边界：

- `工作指南/` 是正式构建指南包。
- 产品代码应在本仓库根目录下创建，不要写进 `工作指南/`。
- 构建 agent 可读 `工作指南/test_cases/test-case-001/public/`。
- hidden truth 和 evaluator-only 文件没有放入本正式构建仓库。
- 每个稳定阶段都要 commit；remote 可用时每阶段 push。

当前 Git 状态：

- branch: `main`
- remote: `origin`
- remote URL: `https://github.com/gongchenisbusy/EAv0.1-build.git`

