# EA Stable Error Catalog / 稳定错误码目录

EA command failures use a stable record with `code`, `summary`, `cause`, `safe_to_retry`, `artifacts_written`, `next_steps`, and `debug_log_ref`. `safe_to_retry: true` means retry can be reasonable after the stated condition is checked; it does not mean an unchanged command should be repeated blindly.

EA 命令失败时会返回稳定字段：错误码、摘要、原因、是否适合重试、已经写入的文件、下一步和本地调试日志。先确认 `artifacts_written` 和操作日志，再决定是否重试。

| Code | Meaning | First action |
|---|---|---|
| `EA-MODE-COMMAND-BLOCKED` | Selected interaction mode blocks the command before project writes / 当前交互模式在项目写入前拒绝命令 | Use a read-only command or explicitly select `record`/`execute` as appropriate. |
| `EA-INPUT-INVALID` | Invalid value or record / 输入或记录无效 | Use preview/dry-run and correct the indicated field. |
| `EA-SCHEMA-MISSING-FIELD` | Required field missing / 缺少必填字段 | Validate or migrate the project record. |
| `EA-IO-NOT-FOUND` | File or directory missing / 路径不存在 | Check the user-supplied path and status output. |
| `EA-IO-PATH-NOT-FILE` | A regular file was required / 需要文件但给出了目录 | Select an existing regular file. |
| `EA-IO-PERMISSION-DENIED` | OS or sandbox denied access / 系统或沙盒拒绝访问 | Check permission/policy; do not infer that companion software is stopped. |
| `EA-IO-ERROR` | Other operating-system I/O failure / 其他系统读写失败 | Inspect diagnostics and the operation journal. |
| `EA-INTEGRATION-CONNECTION-REFUSED` | Integration endpoint refused connection / 集成端拒绝连接 | Verify endpoint and process state. |
| `EA-INTEGRATION-TIMEOUT` | Integration request timed out / 集成请求超时 | Check current target status and retry only that target. |
| `EA-OPERATION-TIMEOUT` | Local operation timed out / 本地操作超时 | Inspect status/journal before retrying. |
| `EA-OPERATION-FAILED` | Controlled operation failed / 受控操作失败 | Follow the operation journal recovery action. |
| `EA-UNEXPECTED-ERROR` | Unclassified failure / 未分类异常 | Collect a local redacted diagnostics bundle. |
| `EA-INSTALL-CLI-NOT-FOUND` | `ea` is missing from PATH | Reinstall and restart the shell. |
| `EA-INSTALL-CLI-EXECUTION-FAILED` | PATH command cannot execute | Inspect/remove the stale executable, then reinstall. |
| `EA-INSTALL-CLI-IDENTITY-MISMATCH` | PATH resolves to another EA version/distribution | Run `ea doctor`, then reinstall the intended release. |
| `EA-INSTALL-DISTRIBUTION-MISMATCH` | Official and legacy distributions conflict | Verify projects, then remove the diagnosed legacy distribution. |

## Privacy-Safe Diagnostics

```bash
ea diagnostics collect /path/to/project --output /path/to/ea-diagnostics.json
```

Diagnostics stay local and exclude raw/processed research data, private full text, credentials, cookies, browser profiles, session identifiers, and signed URL query strings. Submission is a separate user-confirmed action; `ea diagnostics collect` does not upload anything.
