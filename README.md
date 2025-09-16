# 多平台机器人

这是一个支持Discord和KOOK双平台的机器人项目，具有消息监听、消息转发、多语言翻译和基本命令功能。

## 项目结构

```
├── bot.py              # 主启动文件，同时运行两个机器人
├── discord_bot.py      # Discord机器人模块
├── kook.py             # KOOK机器人模块
├── message_forwarder.py # 消息转发器
├── translator.py       # 多平台翻译服务
├── forward_config.py   # 转发配置管理
├── requirements.txt    # 统一依赖文件
├── .env.example        # 环境变量配置示例
└── README.md           # 项目说明文档
```

## 功能特点

### Discord机器人
- 🎧 监听所有频道消息并在控制台输出（包含频道ID）
- 🏓 ping命令 - 检查机器人延迟
- 👋 greet命令 - 问候用户
- 📊 serverinfo命令 - 显示服务器信息
- 📡 listening命令 - 显示监听状态

### KOOK机器人
- 🎧 监听所有频道消息并在控制台输出（包含频道ID）
- 🏓 /ping命令 - 检查机器人延迟
- 👋 /hello命令 - 问候用户
- 📊 /serverinfo命令 - 显示服务器信息（卡片消息）
- 📡 /listening命令 - 显示监听状态

### 消息转发功能
- 🔄 Discord消息自动转发到KOOK
- 📝 支持文本消息转发
- 🖼️ 支持图片转发
- 🎬 支持视频转发
- 🌐 支持多频道映射配置

### 翻译功能
- 🌍 支持多种翻译平台（Google、百度、有道、腾讯云、LibreTranslate、DeepL、必应、阿里云）
- 🔤 一行原文一行译文的格式
- 📊 段落间添加空行，提高可读性
- 🔠 译文前添加表情符号，增强用户体验

### 自动清理功能
- 🧹 定期自动清理下载的媒体文件
- ⏱️ 可自定义清理间隔时间
- 🗑️ 可自定义文件最大保留时间
- 💾 防止磁盘空间被长期占用

## 安装和配置

### 使用Docker部署（Linux）

1. 确保已安装Docker和Docker Compose
2. 克隆项目到本地
3. 复制环境变量示例文件并修改配置
   ```bash
   cp .env.example .env
   # 编辑.env文件，填入必要的配置信息
   ```
4. 使用Docker Compose启动服务
   ```bash
   docker-compose up -d
   ```
5. 查看日志
   ```bash
   docker-compose logs -f
   ```

### 手动安装

#### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置机器人Token和功能

1. **Discord机器人配置：**
   - 访问 [Discord开发者平台](https://discord.com/developers/applications)
   - 创建新的机器人应用并获取Token

2. **KOOK机器人配置：**
   - 访问 [KOOK开发者平台](https://developer.kookapp.cn/)
   - 创建新的机器人应用并获取Token

3. **环境变量配置：**
   - 复制 `.env.example` 为 `.env`
   - 在 `.env` 文件中填入你的Token和其他配置：

```
# 基本配置
DISCORD_BOT_TOKEN=你的Discord机器人token
KOOK_BOT_TOKEN=你的KOOK机器人token

# 转发配置
FORWARD_RULES=discord频道ID:kook频道ID
FORWARD_BOT_MESSAGES=true
MESSAGE_PREFIX=[Discord]

# 翻译功能配置
TRANSLATION_ENABLED=true
TRANSLATION_SERVICE=google  # 可选值: libre, tencent, google, baidu, youdao, deepl, bing, ali
TRANSLATION_SOURCE_LANGUAGE=auto
TRANSLATION_TARGET_LANGUAGE=zh-CN
```

4. **翻译平台配置：**
   - 根据你选择的翻译平台，在`.env`文件中配置相应的API密钥：

```
# Google翻译API配置
GOOGLE_TRANSLATION_API_KEY=你的Google API密钥

# 百度翻译API配置
BAIDU_APP_ID=你的百度APP ID
BAIDU_APP_KEY=你的百度APP KEY

# 有道翻译API配置
YOUDAO_APP_KEY=你的有道APP KEY
YOUDAO_APP_SECRET=你的有道APP SECRET

# 更多翻译平台配置请参考.env.example文件
```

### 3. 运行机器人

#### 同时运行两个机器人（推荐）
```bash
python bot.py
```

#### 单独运行Discord机器人
```bash
python discord.py
```

#### 单独运行KOOK机器人
```bash
python kook.py
```

## 命令使用

### Discord命令
- `/ping` - 检查机器人延迟
- `/greet [用户名]` - 问候指定用户（可选参数）
- `/serverinfo` - 显示当前服务器信息
- `/listening` - 显示机器人监听状态

### KOOK命令
- `/ping` - 检查机器人延迟
- `/hello [用户名]` - 问候指定用户（可选参数）
- `/serverinfo` - 显示当前服务器信息
- `/listening` - 显示机器人监听状态

## 消息监听

两个机器人都会自动监听所有频道的消息，并在控制台输出格式如下：

```
[频道ID: 123456789] [频道名称] 用户类型 用户名: 消息内容
```

## 注意事项

- 确保机器人有足够的权限访问频道和使用命令
- Token请妥善保管，不要泄露给他人
- 可以只配置其中一个平台的Token，程序会自动跳过未配置的平台
- 如需修改功能，请编辑对应的模块文件

## 开发文档

- [Discord.py官方文档](https://discordpy.readthedocs.io/)
- [Discord开发者文档](https://discord.com/developers/docs)
- [KOOK开发者文档](https://developer.kookapp.cn/doc/)
- [khl.py库文档](https://khl-py.eu.org/)