# 月夜 · 大模型语音狼人杀

[![WatcheRobot](https://img.shields.io/badge/WatcheRobot-Python%20SDK-2563eb)](https://wiki.orulink.ai/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776ab)](https://www.python.org/)

面向 WatcheRobot 的单人语音狼人杀：1 名真人固定为 1 号位，与 2～6 号五名大模型玩家完成身份分配、夜间行动、公开讨论、投票放逐和胜负结算。

- 本地 Vosk 将机器人麦克风音频转写为中文文本。
- OpenAI Chat Completions 兼容接口负责自然语言理解和 AI 玩家决策。
- 确定性规则引擎负责合法目标校验、阶段推进、票数及胜负裁决。
- 机器人播放主持语音，并在自身屏幕私密显示身份、狼人队友和预言家查验结果。
- 不使用摄像头、实体身份卡或网页操作按钮。

## 游戏配置

- 1 名真人玩家：固定为 1 号位。
- 5 名大模型玩家：2～6 号位。
- 角色：2 名狼人、1 名预言家、3 名村民。
- 真人可能随机获得任意角色。

## 使用的 WatcheRobot SDK 能力

| 设备能力 | 用途 |
|---|---|
| `microphone` | 获取玩家语音，交由本地 Vosk 转写 |
| `audio.stream` | 播放应用提供的 24 kHz、单声道、16-bit PCM 主持音频 |
| `expression.runtime.v3` | 私密显示身份、狼人队友座位和预言家查验结果 |
| Application Context / 生命周期 | 获取机器人、检查能力，并在异常或退出时释放设备资源 |

应用不会调用摄像头。公开监控页面只显示阶段、轮次、存活座位和已结算的公开票数，不显示身份或查验结果。

## 环境要求

- Windows 或 macOS。
- Python 3.11 或兼容版本。
- 已安装并正确配套的 WatcheRobot Desktop、Daemon 和 Python SDK。
- 已配对且处于 Desktop Link 状态的 WatcheRobot。
- 可访问的 OpenAI Chat Completions 兼容文本模型接口。
- Vosk 中文模型。

停止其他应用后，可检查机器人能力：

```powershell
watcherobot robot capabilities --json
```

机器人必须同时上报 `audio.stream`、`microphone` 和 `expression.runtime.v3`。缺少能力时，应升级相互配套的 Desktop、SDK 和机器人固件；删除能力检查不能让旧固件支持相应接口。

## 获取源码

```powershell
git clone https://github.com/fretelli/moonlit-werewolf.git
cd moonlit-werewolf
```

安装应用依赖：

```powershell
python -m pip install vosk==0.3.45
```

WatcheRobot SDK 请按照官方文档安装并保持与设备固件版本匹配。

## 准备 Vosk 中文模型

Vosk 模型体积较大且属于第三方资源，因此不纳入 Git。运行安装脚本可直接从 Vosk 官方模型站下载、校验并解压默认中文小模型：

```powershell
python prepare_vosk_model.py
```

模型会安装到：

```text
assets/vosk-model-cn/
```

重复运行不会重新下载完整模型；需要覆盖不完整或旧模型时使用 `python prepare_vosk_model.py --force`。目录中应直接包含 `am`、`conf`、`graph` 和 `ivector` 等模型子目录。也可以自行下载其他兼容中文模型，并在 `.env` 中配置绝对路径：

```dotenv
VOSK_MODEL_PATH=C:/path/to/vosk-model-cn
```

## 准备主持音频

应用运行时需要 [`werewolf_speech.py`](werewolf_speech.py) 中 `TEXTS` 定义的全部 WAV 文件，路径为：

```text
assets/werewolf_speech/<key>.wav
```

音频格式必须是：

- 24 kHz
- 单声道
- 16-bit PCM WAV

仓库已包含运行所需的全部主持 WAV，项目所有者已确认这些特定音频可随本项目公开分发；来源说明见 [`assets/werewolf_speech/SOURCE.txt`](assets/werewolf_speech/SOURCE.txt)。无需另外生成音频。

可导出最新录音脚本：

```powershell
python prepare_werewolf_speech.py
```

如需修改台词，仅用于本地开发时可以明确选择在线重新生成；使用者需自行确认服务条款和新音频的分发权：

```powershell
python prepare_werewolf_speech.py --edge-online
```

校验已准备的音频：

```powershell
python prepare_werewolf_speech.py --check
```

## 配置大模型接口

复制示例配置：

```powershell
Copy-Item .env.example .env
```

填写所用服务提供的真实参数：

```dotenv
OPENAI_BASE_URL=https://gateway.example/v1
OPENAI_API_KEY=replace-with-your-key
OPENAI_MODEL=your-chat-model

# 可选
# VOSK_MODEL_PATH=C:/path/to/vosk-model-cn
```

- `OPENAI_BASE_URL`：兼容服务基础地址，可以带或不带 `/v1`。
- `OPENAI_API_KEY`：访问密钥。
- `OPENAI_MODEL`：服务支持的模型名称。
- `VOSK_MODEL_PATH`：可选的本地 Vosk 模型路径。

真实 `.env` 已被 [`.gitignore`](.gitignore) 忽略。不要把密钥写入源码、日志、截图、演示视频或 [`app.json`](app.json)。

## 启动

1. 启动 WatcheRobot Desktop 和 Daemon。
2. 确认机器人处于 Desktop Link 状态。
3. 运行 `python prepare_vosk_model.py`，并根据 [`.env.example`](.env.example) 准备 `.env`。
4. 在仓库根目录运行：

```powershell
watcherobot app run
```

应用入口为 [`app.py`](app.py)，公开监控页面为：

```text
http://127.0.0.1:8766
```

## 语音操作

1. 启动后说“开始”或“开始游戏”。
2. 机器人私密显示身份；记住后直接说“继续”，不需要再次确认。
3. 真人为狼人时，机器人继续私密显示狼人队友座位；看完直接说“继续”。
4. 狼人、预言家夜间行动时，先说目标座位，再说“确认”。
5. 白天公开怀疑和投票时，说座位或“弃票”，再说“确认”。
6. 暂停后恢复只需说一次“继续”。
7. 结束游戏需先说“结束游戏”，再说“确认”。
8. 目标识别错误时说“取消”，然后重新选择。

| 操作 | 是否需要二次确认 |
|---|---|
| 开始游戏 | 否 |
| 查看身份后继续 | 否 |
| 暂停后继续 | 否 |
| 选择座位 | 是 |
| 弃票 | 是 |
| 结束游戏 | 是 |

待确认目标不会显示在机器人屏幕或公开监控页面。

## 模型能力边界

- 原始麦克风音频不会写入文件，也不会发送给模型接口。
- 只有 Vosk 转写后的文本会发送给配置的兼容接口。
- 每个 AI 玩家只会收到自己的身份、自己的队友或查验信息，以及公开游戏状态。
- AI 输出只能从规则引擎提供的合法候选项中选择。
- 模型不能修改身份、游戏阶段、票数、规则或胜负结果。
- 超时、非 JSON 响应或非法座位会被拒绝，不会自动猜测目标。

## 已知限制与注意事项

- 当前仅支持一名真人与五名 AI 玩家，真人固定为 1 号位。
- AI 决策需要网络；接口超时、限流、余额不足或不可用可能导致对局安全中止。
- 语音识别受噪声、口音、说话距离和多人同时说话影响，建议在安静环境中、主持播报结束后再发言。
- 私密信息显示在机器人自身屏幕，录制 Demo 时应避免把身份和查验结果投到公开画面。
- 公开监控地址默认仅限本机访问，不是控制界面。
- 当前正式支持平台由 [`app.json`](app.json) 声明为 Windows 和 macOS。

## 项目结构

- [`werewolf_voice.py`](werewolf_voice.py)：麦克风采集、Vosk 识别和语音选择流程。
- [`werewolf_llm.py`](werewolf_llm.py)：OpenAI 兼容客户端、指令解释和 AI 玩家。
- [`werewolf_engine.py`](werewolf_engine.py)：确定性游戏规则。
- [`werewolf_solo.py`](werewolf_solo.py)：单人对局编排。
- [`werewolf_device.py`](werewolf_device.py)：机器人音频和私密屏幕。
- [`werewolf_monitor.py`](werewolf_monitor.py)：公开状态投影。
- [`werewolf_web`](werewolf_web)：只读公开监控页面。
- [`prepare_vosk_model.py`](prepare_vosk_model.py)：从 Vosk 官方站自动下载并安装中文模型。
- [`tests`](tests)：离线测试。

## 测试

测试不会访问真实模型服务或真实机器人：

```powershell
python -m unittest discover -s tests -v
```

需要验证主持音频时，先准备全部 WAV，再运行：

```powershell
python prepare_werewolf_speech.py --check
```

## 发布安全

本仓库刻意排除以下内容：

- `.env` 和任何真实 API Key。
- `.venv`、缓存和构建产物。
- 体积较大的第三方 Vosk 模型及下载 ZIP。
主持 WAV 已在项目所有者确认可公开分发后纳入仓库；第三方 Vosk 模型仍通过官方地址按需下载，不进入 Git 历史。

仓库地址：<https://github.com/fretelli/moonlit-werewolf>
