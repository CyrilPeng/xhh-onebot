# xhh-onebot

小黑盒到 OneBot v11 反向 WebSocket 的轻量适配器。由于 AstrBot 插件侧限制，本适配器推荐作为独立 Docker 容器运行，再通过 OneBot v11 反向 WebSocket 接入 AstrBot。

## 工作流

1. `xhh-onebot` 独立运行，定时轮询小黑盒 @ 消息。
2. 适配器获取帖子上下文，并转换为 OneBot `message.group` 事件。
3. 适配器作为反向 WebSocket 客户端连接 AstrBot，并上报事件。
4. AstrBot 生成回复后，通过 `send_group_msg` / `send_msg` action 发回适配器。
5. 适配器根据待回复队列，把回复写回对应小黑盒评论。

## 独立 Docker 部署

### 1. 准备配置

```bash
cd xhh-onebot
cp config.docker.example.json config.json
mkdir -p data
```

必须先修改 `config.json`：

- `onebot.reverse_ws_url`：AstrBot 提供的 OneBot v11 反向 WebSocket 地址。
- `xhh.owner`：允许触发机器人的小黑盒用户 ID，多个 ID 用英文逗号分隔；公共机器人填 `*` 表示任何人都能触发。
- `xhh.device_id`：建议填写固定设备 ID，避免频繁变化导致登录态异常。

### 2. 配置 AstrBot 连接地址

如果 AstrBot 跑在宿主机，保持 Docker 示例配置即可：

```json
"reverse_ws_url": "ws://host.docker.internal:6199/ws"
```

如果 AstrBot 是另一个 Docker 容器，建议让两个容器加入同一个 Docker network，然后使用 AstrBot 的服务名：

```json
"reverse_ws_url": "ws://astrbot:6199/ws"
```

如果 AstrBot 在局域网另一台机器上，使用该机器 IP：

```json
"reverse_ws_url": "ws://192.168.1.10:6199/ws"
```

AstrBot 侧需要启用 OneBot v11 反向 WebSocket 接入，并确保监听地址、端口和路径与 `reverse_ws_url` 一致；如果适配器运行在容器中，AstrBot 不应只监听容器不可访问的本地回环地址。

### 3. 构建镜像

```bash
docker compose build
```

### 4. 扫码登录小黑盒

登录态会保存到 `./data/cookie.json`，后续容器重建不会丢失。

```bash
docker compose run --rm xhh-onebot login --config /app/config.json
```

命令会在终端输出二维码，并生成 `qrcode.png`。扫码成功后确认 `./data/cookie.json` 已生成。

### 5. 启动适配器

```bash
docker compose up -d
```

查看日志：

```bash
docker compose logs -f xhh-onebot
```

停止服务：

```bash
docker compose down
```

## 本地源码调试

源码调试建议使用项目内 `.venv`，避免污染全局 Python 环境。

Windows PowerShell：

```powershell
cd xhh-onebot
$env:XHH_ONEBOT_PYTHON = "C:\Path\To\Python\python.exe"
.\scripts\setup-venv.ps1
.\.venv\Scripts\Activate.ps1
Copy-Item config.example.json config.json
python -m xhh_onebot login
python -m xhh_onebot start
```

`XHH_ONEBOT_PYTHON` 用于指定创建 `.venv` 的 Python 解释器；也可以改用通用的 `PYTHON` 环境变量。如果两个环境变量都未设置，脚本会使用当前 `PATH` 中的 `python`。

如果 `.venv` 是从其他目录复制来的，或原 Python 已被删除，可能出现 `did not find executable`。这时需要删除旧虚拟环境后重建：

```powershell
Remove-Item -Recurse -Force .\.venv
$env:XHH_ONEBOT_PYTHON = "C:\Path\To\Python\python.exe"
.\scripts\setup-venv.ps1
```

Linux / macOS：

```bash
cd xhh-onebot
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install --no-build-isolation -e .
cp config.example.json config.json
python -m xhh_onebot login
python -m xhh_onebot start
```

已创建 `.venv` 后，后续调试只需要重新激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
python -m xhh_onebot start
```

常用源码调试命令：

```powershell
python -m xhh_onebot sign --path /bbs/app/user/message --timestamp 1770000000 --random 123456
python -m xhh_onebot check-login
python -m xhh_onebot poll-once --ws-timeout 10
pytest -q
```

本地运行时，如果 AstrBot 在同一台机器上，通常使用：

```json
"reverse_ws_url": "ws://127.0.0.1:6199/ws"
```

## 诊断命令

本地执行：

```bash
python -m xhh_onebot sign --path /bbs/app/user/message --timestamp 1770000000 --random 123456
python -m xhh_onebot check-login
python -m xhh_onebot poll-once --ws-timeout 10
```

Docker 中执行：

```bash
docker compose run --rm xhh-onebot check-login --config /app/config.json
docker compose run --rm xhh-onebot poll-once --config /app/config.json --ws-timeout 10
```

说明：

- `sign` 用于和 Go 版本签名结果做固定输入对照。
- `check-login` 用当前 `cookie.json` 请求小黑盒消息接口，检查登录是否有效。
- `poll-once` 会临时连接 AstrBot 反向 WebSocket，执行一次小黑盒轮询、去重、入库、事件构造和投递；持续运行请使用 `start` 常驻模式。
- `start` 启动后会自动校验登录；pending 事件超过 `poller.reply_timeout` 会标记为 `expired`，避免长期占用回复队列。

## 配置说明

关键字段：

- `onebot.reverse_ws_url`：AstrBot 的 OneBot v11 反向 WebSocket 地址。
- `onebot.access_token`：AstrBot 如果启用了 OneBot token，这里填写同一个 token；未启用则留空。
- `xhh.owner`：触发用户白名单；公共机器人填 `*`，表示任何小黑盒用户 @ 都会转发给 AstrBot。
- `xhh.owner` 也支持白名单模式，例如 `123456` 或 `123456,789012`；留空表示不投递任何消息。
- `xhh.device_id`：固定设备 ID，建议填写稳定 UUID，避免频繁变化影响登录态。
- `xhh.cookie_file`：登录态文件路径，Docker 推荐 `data/cookie.json`。
- `poller.context_max_chars`：投递给 AstrBot 的整条消息最大长度。
- `poller.post_context_max_chars`：帖子正文背景最大长度，默认 `1200`，用于避免长正文抢占 AI 对用户最后提问的注意力。
- `database.path`：SQLite 状态库路径，Docker 推荐 `data/xhh-onebot.db`。

公共机器人推荐配置：

```json
"xhh": {
  "owner": "*",
  "cookie_file": "data/cookie.json"
}
```

## 数据文件

Docker 模式下建议只持久化 `./data`：

- `./data/cookie.json`：小黑盒登录态。
- `./data/xhh-onebot.db`：已处理消息和待回复队列。

`config.json` 以只读方式挂载到容器内 `/app/config.json`，修改配置后需要重启容器：

```bash
docker compose restart xhh-onebot
```

## 已支持的 OneBot v11 子集

- 事件：`message.group`、`meta_event.lifecycle`、`meta_event.heartbeat`。
- Action：`send_group_msg`、`send_msg`、`get_login_info`、`get_status`、`get_version_info`、`get_group_info`、`get_group_member_info`、`can_send_image`、`can_send_record`。
- 回复定位：优先识别 `reply` 消息段中的 `id`，否则使用对应 `group_id` 下最早待回复事件。

## 排障建议

- 反复显示 `OneBot reverse WS disconnected`：检查 AstrBot 是否已启用反向 WS、端口路径是否一致、容器是否能访问该地址。`HTTP 401` 表示 AstrBot 启用了 OneBot 鉴权，需要把 AstrBot 中配置的 token 填到 `onebot.access_token`，或关闭 AstrBot 侧 token。
- `xhh login check failed`：重新执行 `login`，确认 `xhh.cookie_file` 指向 `data/cookie.json`。
- 收不到事件：公共机器人确认 `xhh.owner` 为 `*`；白名单模式确认用户 ID 已配置，且消息没有被 SQLite 标记为已处理。
- AstrBot 回复后没有写回：确认 AstrBot 发出的是 `send_group_msg` / group 类型 `send_msg`，并且 `group_id` 对应小黑盒 `link_id`。
- 出现 `failed to get xhh link context, delivering comment only`：表示帖子详情接口不可用或被小黑盒判为非法请求；适配器会继续把用户评论内容投递给 AstrBot。只要日志出现 `delivered xhh message ... as OneBot event`，就说明事件已经发出。













