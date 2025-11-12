# macOS Launchd 自动推送模板（watch_and_push）

本目录提供一个可配置的 Launchd `plist` 模板，用于在 macOS 上监控本地项目目录变更并触发一次性推送到服务器（调用 `scripts/watch_and_push.sh` → `push_local_to_server.sh`）。

## 适用场景
- 你在本地频繁开发，需要在保存或变更时自动同步到远端服务器（rsync）。
- 希望由系统守护（Launchd）负责监听目录变化，而不是常驻前台工具。

## 先决条件
- 已安装 `rsync`（macOS 自带）与以下任一监控工具：
  - `fswatch`（推荐）：`brew install fswatch`
  - 或 `entr`：`brew install entr`
- 仓库根目录下存在脚本：`scripts/watch_and_push.sh` 与 `scripts/push_local_to_server.sh`。
- 你拥有远端服务器 SSH 访问权限（建议配置免密登录）。

## 使用步骤
1. 复制模板到用户 LaunchAgents 目录：
   - 路径：`~/Library/LaunchAgents/com.nebula.watchpush.plist`
   - 内容：将 `launchd_watchpush.plist.example` 中的 `{{PROJECT_ROOT}}` 替换为你的本地项目绝对路径，例如：`/Users/yourname/Desktop/剧本分析`
   - 环境变量按需修改：`SERVER`、`REMOTE_DIR`、`PORT`、`GIT_ENABLE`、`PIP_INDEX_URL`、`PIP_TIMEOUT`。

2. 加载并启用：
   - 加载：`launchctl load -w ~/Library/LaunchAgents/com.nebula.watchpush.plist`
   - 查看：`launchctl list | grep com.nebula.watchpush`

3. 日志查看：
   - 标准输出：`tail -f /tmp/nebula_watch.log`
   - 标准错误：`tail -f /tmp/nebula_watch.err`

4. 关闭或卸载：
   - 卸载：`launchctl unload -w ~/Library/LaunchAgents/com.nebula.watchpush.plist`

## 模板关键项说明
- `ProgramArguments`：调用 `watch_and_push.sh`，在 `USE_LAUNCHD_WATCH=true` 下，目录变更触发后只执行一次推送即退出。
- `WatchPaths`：设置为你的项目根目录，目录中任意变更都会触发一次执行。
- `ThrottleInterval`：防抖间隔，避免极短时间内的多次触发。
- `EnvironmentVariables`：
  - `SERVER`：远端 SSH，例如 `user@your-server`
  - `REMOTE_DIR`：远端项目目录，例如 `/opt/nebula`
  - `PORT`：应用端口（与服务器运行保持一致，默认 5000）
  - `GIT_ENABLE`：是否在推送前进行本地 Git 提交与推送（true/false）
  - `PIP_INDEX_URL`/`PIP_TIMEOUT`：传递给远端的构建参数，提高拉取依赖稳定性

## 常见问题
- 未检测到 `fswatch/entr`：请按上文安装其一（推荐 `fswatch`）。
- 无法推送到远端：确认你可以在终端运行 `ssh user@your-server`，且远端具备 `rsync` 与 Docker Compose 环境（参考仓库根目录部署文档）。
- 目录路径不生效：`plist` 中路径必须为绝对路径，不能使用 `~`。

## 参考
- Apple Launchd 文档：https://www.launchd.info/
- 本仓库脚本：`scripts/watch_and_push.sh`、`scripts/push_local_to_server.sh`、`scripts/auto_update.sh`