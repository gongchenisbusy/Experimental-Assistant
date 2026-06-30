# EA v0.1 Git Workflow

> 用途：给正式构建 EA v0.1 的 Main Orchestrator 使用。  
> 读者：Main Orchestrator、QA Reviewer、所有会修改代码或文档的子 agent。  
> 用户背景：用户不需要有 Git 仓库管理经验，agent 必须主动承担 Git 初始化、提交、同步和可回滚检查。

---

## 1. 总原则

Git 的作用是保护构建过程：

- 每个稳定阶段都能回到上一版。
- 每次较大改动都有清晰提交记录。
- 出错时优先创建回滚分支或 revert，不破坏已有工作。
- 远程仓库可用时，定期 push，避免本地机器或窗口状态丢失。

Main Orchestrator 必须把 Git 当成构建基础设施，不是可选项。

---

## 2. 开工前必须做

正式构建 agent 进入 `EAv0.1-build/` 后，第一步检查：

```bash
pwd
git rev-parse --show-toplevel
git status --short
git branch --show-current
git remote -v
git config user.name
git config user.email
```

如果不是 Git 仓库：

```bash
git init -b main
```

如果没有 Git identity，应设置本仓库本地 identity，并告诉用户：

```bash
git config user.name "EA Build Agent"
git config user.email "ea-build-agent@example.local"
```

如果没有 remote：

- 不要假装已经上传。
- 先继续使用本地 commit 保护阶段进度。
- 向用户说明需要创建 GitHub private repo 或提供 remote URL。
- remote 配置完成后，再执行 push。

---

## 3. `.gitignore` 必须保护的内容

正式构建 repo 必须有 `.gitignore`，至少覆盖：

```gitignore
# evaluator-only material
test_cases/**/hidden_truth/
test_cases/**/evaluation.md

# user/private research material
private/
secrets/
credentials/
*.token
*.key
.env
.env.*

# runtime caches
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.DS_Store

# generated outputs
outputs/
reports/generated/
processed/
figures/generated/

# live project raw data, not public test fixtures
raw/
```

注意：

- public test fixture 的 raw txt 可以进入 repo。
- 用户真实项目运行时导入的 `raw/` 不进入 repo。
- hidden truth 和 evaluator-only 文件不进入构建 agent repo。

---

## 4. 分支策略

推荐分支：

```text
main
codex/stage-0-bootstrap
codex/stage-1-schema
codex/stage-2-project-init
codex/stage-3-log-review
codex/stage-4-raw-import
codex/stage-5-raman
codex/stage-6-memory-provenance
codex/stage-7-test-hardening
```

规则：

- `main` 只保留阶段稳定点。
- 每个阶段在自己的 `codex/stage-*` 分支上开发。
- 阶段通过测试和 QA review 后，再合并到 `main`。
- 不要在多个 agent 之间同时修改同一个文件，除非 Main Orchestrator 明确安排合并。

---

## 5. 提交节奏

必须提交：

- 初始化构建包后。
- 每个阶段开始前，如果工作区已有稳定改动。
- 每个阶段完成后。
- 每次通过关键测试后。
- 每次 risky refactor 前后。
- 长时间工作时，至少每 30-60 分钟提交一次 checkpoint。

建议 commit message：

```text
stage-0: bootstrap EA v0.1 build package
stage-1: add core schemas
stage-2: implement project initialization
stage-3: add experiment log review workflow
stage-4: implement raw import safeguards
stage-5: implement Raman parser and reports
stage-6: add memory and provenance updates
stage-7: harden public test workflow
checkpoint: before Raman refactor
fix: preserve raw file immutability
```

提交前必须运行：

```bash
git status --short
git diff --stat
```

提交后必须运行：

```bash
git status --short
git log --oneline --decorate -5
```

---

## 6. Push / 上传同步规则

如果 remote 已配置，必须定期上传：

```bash
git push -u origin <branch>
git push origin main
git push origin --tags
```

上传频率：

- 每个阶段完成并 commit 后 push。
- 每个工作时段结束前 push。
- 每次创建阶段 tag 后 push tags。
- 发生较大风险修改前，先 commit + push 当前稳定点。

如果 push 失败：

- 不要继续假装同步成功。
- 记录错误。
- 保留本地 commit。
- 告诉用户 remote / authentication / network 需要处理。

---

## 7. 阶段 Tag

每个稳定阶段建议打 tag：

```bash
git tag stage-0-bootstrap
git tag stage-1-schema
git tag stage-2-project-init
git tag stage-3-log-review
git tag stage-4-raw-import
git tag stage-5-raman
git tag stage-6-memory-provenance
git tag stage-7-test-hardening
```

如果 tag 已存在，不要强制覆盖。使用带日期的新 tag：

```bash
git tag stage-5-raman-20260602
```

---

## 8. 回滚协议

不要直接运行破坏性命令，例如：

```bash
git reset --hard
git clean -fd
git push --force
```

除非用户明确要求，并且 Main Orchestrator 已说明后果。

推荐回滚方式：

### 8.1 从稳定 tag 创建回滚分支

```bash
git switch -c codex/rollback-stage-4 stage-4-raw-import
```

然后在回滚分支上检查和恢复。

### 8.2 撤销某个错误 commit

```bash
git revert <commit-sha>
```

这会创建一个新的反向提交，比 `reset --hard` 更安全。

### 8.3 只恢复某个文件

先查看差异：

```bash
git diff -- path/to/file
```

如果确认只恢复单文件，再执行：

```bash
git restore path/to/file
```

恢复文件前必须确认它不是用户刚刚手动修改的内容。

---

## 9. Agent 协作规则

每个会修改文件的 agent 必须：

- 先看 `git status --short`。
- 只修改自己任务范围内的文件。
- 不回滚其他 agent 或用户的改动。
- 交付时说明新增/修改文件、测试结果和 Git 状态。

Main Orchestrator 必须：

- 在每个阶段结束时统一提交。
- 防止并行 agent 修改同一文件。
- 在提交前检查 hidden truth、token、private data 没有被 staged。
- 如果使用 remote，阶段结束必须 push。

QA Reviewer 必须检查：

- 是否存在未提交的关键改动。
- 是否误提交 hidden truth、private raw data 或 token。
- 是否缺少阶段 tag。
- 是否缺少测试后 commit。

---

## 10. Stage 0 Git Checklist

正式构建 agent 的 Stage 0 必须完成：

- [ ] 确认当前目录是 `EAv0.1-build/`。
- [ ] 确认 Git repo 已初始化。
- [ ] 确认分支为 `main`。
- [ ] 确认 `.gitignore` 已创建。
- [ ] 确认 hidden truth 不在构建 repo 中。
- [ ] 创建初始 commit：`stage-0: bootstrap EA v0.1 build package`。
- [ ] 创建 tag：`stage-0-bootstrap`。
- [ ] 如果 remote 可用，push `main` 和 tag。
- [ ] 如果 remote 不可用，告诉用户：“当前只有本地 Git 保护，尚未上传远程。”

