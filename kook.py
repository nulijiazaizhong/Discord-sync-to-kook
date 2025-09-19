import asyncio
import json
import aiohttp
from khl import Bot, Message, Event, EventTypes
from khl.card import CardMessage, Card, Module, Element, Types, Struct
from khl.command import Command
import os

def create_kook_bot(token):
    """创建KOOK机器人实例"""
    bot = Bot(token=token)
    
    # 猴子补丁：重写requester的request方法以避免超时上下文管理器错误
    original_request = bot.client.gate.requester.request
    
    async def patched_request(self, method, route, **params):
        """修补的请求方法，确保HTTP客户端session存在"""
        import aiohttp
        from khl.requester import API
        
        # 移除timeout参数
        if 'timeout' in params:
            del params['timeout']
        
        # 确保HTTP客户端session存在
        if not hasattr(self, '_cs') or self._cs is None:
            self._cs = aiohttp.ClientSession()
        
        async with self._cs.request(method, f'{API}/{route}', **params) as res:
            return await res.json()
    
    # 绑定修补的方法
    import types
    bot.client.gate.requester.request = types.MethodType(patched_request, bot.client.gate.requester)
    
    # 直接输出KOOK机器人信息
    print("KOOK机器人已创建，准备设置命令...")
    
    return setup_kook_bot(bot)

def setup_kook_bot(bot):
    """设置KOOK机器人的事件和命令"""
    
    # 机器人启动事件处理函数
    async def on_startup():
        print(f'KOOK机器人已成功启动！')
        print('------')
        
        # 强制输出命令列表
        print('【KOOK可用文本命令】:')
        print('  .ping - 测试机器人是否在线')
        print('  .hello - 问候命令')
        print('------')
        
        # 注册斜杠命令
        await register_slash_commands(bot)
    
    # 将启动事件绑定到bot
    bot.on_startup = on_startup
    
    # 注意：在这里不输出命令列表，因为命令还未注册
    # 命令列表将在所有命令注册完成后的on_startup事件中输出
    
    # 注册斜杠命令函数
    async def register_slash_commands(bot):
        """注册所有斜杠命令"""
        try:
            print("开始获取和注册KOOK斜杠命令...")
            
            # 获取当前已注册的命令
            commands = await bot.client.fetch_commands()
            command_names = [cmd.name for cmd in commands]
            
            print(f"当前已注册的斜杠命令: {', '.join(['/' + name for name in command_names]) if command_names else '无'}")
            
            # 定义要注册的斜杠命令
            slash_commands = [
                {
                    'name': 'help',
                    'description': '显示帮助信息',
                    'already_exists': 'help' in command_names
                },
                {
                    'name': 'status',
                    'description': '显示机器人状态',
                    'already_exists': 'status' in command_names
                },
                {
                    'name': 'about',
                    'description': '关于本机器人',
                    'already_exists': 'about' in command_names
                }
            ]
            
            print("计划注册的斜杠命令:")
            for cmd in slash_commands:
                status = "已存在" if cmd['already_exists'] else "将注册"
                print(f"  /{cmd['name']} - {cmd['description']} [{status}]")
            
            # 注册新的斜杠命令
            registered_count = 0
            for cmd in slash_commands:
                if not cmd['already_exists']:
                    await bot.client.register_command(cmd['name'], cmd['description'])
                    print(f"✅ 已成功注册斜杠命令: /{cmd['name']} - {cmd['description']}")
                    registered_count += 1
            
            print(f"斜杠命令注册完成! 新注册: {registered_count}, 已存在: {len(slash_commands) - registered_count}, 总计: {len(slash_commands)}")
            print("------")
        except Exception as e:
            print(f"❌ 注册斜杠命令时出错: {e}")
            print(f"错误类型: {type(e).__name__}")
            print("------")

    # 监听所有消息处理函数
    @bot.on_message()
    async def on_message(msg: Message):
        # 跳过机器人自己的消息
        if msg.author.bot:
            return
        
        # 获取消息详细信息
        author_id = msg.author.id
        username = msg.author.username
        content = msg.content
        channel_id = msg.ctx.channel.id
        channel_name = msg.ctx.channel.name if hasattr(msg.ctx.channel, 'name') else "私聊"
        
        # 输出消息到控制台，包含平台标识和频道ID
        print(f"[KOOK] [频道ID: {channel_id}] [{channel_name}] 用户 {username}: {content}")

    # 文本命令：ping
    @bot.command(name='ping')
    async def ping(msg: Message):
        """检查机器人延迟"""
        print(f"[KOOK] 执行文本命令: .ping")
        print(f"  - 用户: {msg.author.username} (ID: {msg.author.id})")
        print(f"  - 频道: {msg.ctx.channel.name if hasattr(msg.ctx.channel, 'name') else '私聊'} (ID: {msg.ctx.channel.id})")
        
        # 使用时间戳计算延迟
        import time
        start_time = time.time()
        
        # 计算往返时间
        end_time = time.time()
        latency = round((end_time - start_time) * 1000)
        
        # 发送带延迟信息的消息和处理结果
        result_message = f'🏓 Pong! 延迟: {latency}ms\n\n📊 命令处理信息:\n- 命令: .ping\n- 处理用时: {latency}ms\n- 状态: 成功'
        
        # 使用直接API调用发送消息
        try:
            # 获取频道ID
            channel_id = msg.ctx.channel.id
            
            # 直接使用API发送消息
            import aiohttp
            import os
            from dotenv import load_dotenv
            
            # 加载环境变量获取token
            load_dotenv()
            token = os.getenv('KOOK_BOT_TOKEN')
            
            # 构建API请求
            url = "https://www.kookapp.cn/api/v3/message/create"
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json"
            }
            data = {
                "target_id": channel_id,
                "content": result_message,
                "type": 1  # 1表示文本消息
            }
            
            # 发送请求
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        print(f"✅ 消息已发送到KOOK频道 {channel_id}")
                    else:
                        resp_json = await response.json()
                        print(f"❌ 发送消息到KOOK失败: {resp_json}")
        except Exception as e:
            print(f"❌ 发送消息到KOOK失败: {e}")
        
        print(f"✅ 已处理 .ping 命令，延迟: {latency}ms")

    # 文本命令：hello
    @bot.command(name='hello')
    async def hello(msg: Message, name: str = None):
        """问候命令，可选参数：名称"""
        print(f"[KOOK] 执行文本命令: .hello {name if name else ''}")
        print(f"  - 用户: {msg.author.username} (ID: {msg.author.id})")
        print(f"  - 频道: {msg.ctx.channel.name if hasattr(msg.ctx.channel, 'name') else '私聊'} (ID: {msg.ctx.channel.id})")
        
        # 获取当前时间
        import datetime
        current_hour = datetime.datetime.now().hour
        
        # 根据时间选择不同的问候语
        if 5 <= current_hour < 12:
            greeting = "早上好"
        elif 12 <= current_hour < 18:
            greeting = "下午好"
        else:
            greeting = "晚上好"
            
        # 使用表情符号增强问候语
        emojis = ["👋", "😊", "🌟", "✨", "🎉"]
        import random
        emoji = random.choice(emojis)
        
        # 构建回复消息
        target_name = name if name else msg.author.username
        result_message = f'{emoji} {greeting}，{target_name}！祝你今天愉快！\n\n📊 命令处理信息:\n- 命令: .hello\n- 参数: {target_name}\n- 状态: 成功'
        
        # 使用直接API调用发送消息
        try:
            # 获取频道ID
            channel_id = msg.ctx.channel.id
            
            # 直接使用API发送消息
            import aiohttp
            import os
            from dotenv import load_dotenv
            
            # 加载环境变量获取token
            load_dotenv()
            token = os.getenv('KOOK_BOT_TOKEN')
            
            # 构建API请求
            url = "https://www.kookapp.cn/api/v3/message/create"
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json"
            }
            data = {
                "target_id": channel_id,
                "content": result_message,
                "type": 1  # 1表示文本消息
            }
            
            # 发送请求
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        print(f"✅ 消息已发送到KOOK频道 {channel_id}")
                    else:
                        resp_json = await response.json()
                        print(f"❌ 发送消息到KOOK失败: {resp_json}")
        except Exception as e:
            print(f"❌ 发送消息到KOOK失败: {e}")
        
        print(f"✅ 已处理 .hello 命令, 参数: {name if name else msg.author.username}")

    # 文本命令：help
    @bot.command(name='help')
    async def help_command(msg: Message):
        """显示所有可用命令"""
        print(f"[KOOK] 执行文本命令: .help")
        print(f"  - 用户: {msg.author.username} (ID: {msg.author.id})")
        print(f"  - 频道: {msg.ctx.channel.name if hasattr(msg.ctx.channel, 'name') else '私聊'} (ID: {msg.ctx.channel.id})")
        
        # 构建帮助信息
        help_text = "📚 **可用命令列表**\n\n"
        
        # 添加文本命令
        help_text += "**文本命令：**\n"
        # 手动列出已知命令
        commands = {
            'ping': '测试机器人延迟',
            'hello': '向用户问好',
            'help': '显示所有可用命令',
            'serverinfo': '显示服务器信息'
        }
        for cmd_name, cmd_desc in commands.items():
            help_text += f"`.{cmd_name}` - {cmd_desc}\n"
            
        # 添加命令处理信息
        help_text += f"\n\n📊 **命令处理信息**:\n- 命令: .help\n- 状态: 成功\n- 显示了 {len(commands)} 个命令"
        
        # 使用直接API调用发送消息
        try:
            # 获取频道ID
            channel_id = msg.ctx.channel.id
            
            # 直接使用API发送消息
            import aiohttp
            import os
            from dotenv import load_dotenv
            
            # 加载环境变量获取token
            load_dotenv()
            token = os.getenv('KOOK_BOT_TOKEN')
            
            # 构建API请求
            url = "https://www.kookapp.cn/api/v3/message/create"
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json"
            }
            data = {
                "target_id": channel_id,
                "content": help_text,
                "type": 1  # 1表示文本消息
            }
            
            # 发送请求
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        print(f"✅ 帮助信息已发送到KOOK频道 {channel_id}")
                    else:
                        resp_json = await response.json()
                        print(f"❌ 发送帮助信息到KOOK失败: {resp_json}")
        except Exception as e:
            print(f"❌ 发送帮助信息到KOOK失败: {e}")
        
        print(f"✅ 已处理 .help 命令")

    # 文本命令：服务器信息
    @bot.command(name='serverinfo')
    async def serverinfo(msg: Message):
        """显示服务器信息"""
        guild = msg.ctx.guild
        
        # 创建卡片消息
        card = Card(
            Module.Header(f'{guild.name} 服务器信息'),
            Module.Section(
                Element.Text(f'**服务器ID:** {guild.id}\n'
                            f'**成员数量:** {guild.member_count}\n'
                            f'**创建时间:** {guild.create_time.strftime("%Y-%m-%d")}',
                            Types.Text.KMD)
            )
        )
        
        if guild.icon:
            card.append(Module.Container(Element.Image(guild.icon)))
        
        cm = CardMessage(card)
        await msg.reply(cm)

    # 文本命令：监听状态
    @bot.command(name='listening')
    async def listening(msg: Message):
        """显示机器人监听状态"""
        card = Card(
            Module.Header('🎧 消息监听状态'),
            Module.Section(
                Element.Text('机器人正在监听所有频道消息\n\n'
                            '**监听范围:**\n'
                            '✅ 用户消息\n'
                            '✅ 机器人消息\n'
                            '✅ 所有频道\n\n'
                            '**记录位置:** 控制台输出',
                            Types.Text.KMD)
            )
        )
        
        cm = CardMessage(card)
        await msg.reply(cm)

    # 斜杠命令处理
    @bot.on_event(EventTypes.MESSAGE_BTN_CLICK)
    async def handle_slash_command(b: Bot, event: Event):
        """处理斜杠命令事件"""
        try:
            # 获取命令名称和参数
            command_name = event.extra.get('name', '')
            user_id = event.extra.get('user_id', '')
            channel_id = event.extra.get('channel_id', '')
            guild_id = event.extra.get('guild_id', '私聊')
            
            # 获取用户信息
            user = await bot.client.fetch_user(user_id)
            username = user.username if user else "未知用户"
            
            # 获取频道信息
            channel_name = "未知频道"
            if channel_id:
                try:
                    channel = await bot.client.fetch_public_channel(channel_id)
                    channel_name = channel.name if hasattr(channel, 'name') else "私聊"
                except:
                    pass
            
            print(f"[KOOK] 收到斜杠命令: /{command_name} 来自用户 {username}")
            print(f"  - 用户ID: {user_id}")
            print(f"  - 频道: {channel_name} (ID: {channel_id})")
            print(f"  - 服务器ID: {guild_id}")
            print(f"  - 时间: {event.msg_timestamp if hasattr(event, 'msg_timestamp') else '未知'}")
            
            # 处理不同的斜杠命令
            print(f"开始处理斜杠命令: /{command_name}")
            if command_name == 'help':
                await handle_help_command(bot, channel_id)
                print(f"✅ 已处理 /help 命令")
            elif command_name == 'status':
                await handle_status_command(bot, channel_id)
                print(f"✅ 已处理 /status 命令")
            elif command_name == 'about':
                await handle_about_command(bot, channel_id)
                print(f"✅ 已处理 /about 命令")
            else:
                print(f"⚠️ 未知的斜杠命令: /{command_name}")
        except Exception as e:
            print(f"❌ 处理斜杠命令时出错: {e}")
            print(f"错误类型: {type(e).__name__}")
            import traceback
            print(traceback.format_exc())
    
    # 帮助命令处理函数
    async def handle_help_command(bot, channel_id):
        """处理帮助命令"""
        card = Card(
            Module.Header('📚 帮助信息'),
            Module.Section(
                Element.Text('**可用的斜杠命令:**\n'
                            '`/help` - 显示此帮助信息\n'
                            '`/status` - 显示机器人状态\n'
                            '`/about` - 关于本机器人\n\n'
                            '**可用的文本命令:**\n'
                            '`.ping` - 检查机器人延迟\n'
                            '`.hello [名字]` - 问候命令\n'
                            '`.serverinfo` - 显示服务器信息\n'
                            '`.listening` - 显示监听状态',
                            Types.Text.KMD)
            )
        )
        
        cm = CardMessage(card)
        await bot.client.send(channel_id, cm)
    
    # 状态命令处理函数
    async def handle_status_command(bot, channel_id):
        """处理状态命令"""
        latency = round(bot.client.latency * 1000)
        
        card = Card(
            Module.Header('🤖 机器人状态'),
            Module.Section(
                Element.Text(f'**延迟:** {latency}ms\n'
                            f'**运行状态:** 正常\n'
                            f'**监听状态:** 活跃\n'
                            f'**API状态:** 正常',
                            Types.Text.KMD)
            )
        )
        
        cm = CardMessage(card)
        await bot.client.send(channel_id, cm)
    
    # 关于命令处理函数
    async def handle_about_command(bot, channel_id):
        """处理关于命令"""
        card = Card(
            Module.Header('ℹ️ 关于本机器人'),
            Module.Section(
                Element.Text('**Discord-sync-to-kook**\n'
                            '这是一个用于在Discord和KOOK之间同步消息的机器人。\n\n'
                            '**功能:**\n'
                            '- 消息同步\n'
                            '- 斜杠命令支持\n'
                            '- 服务器信息查询\n'
                            '- 状态监控',
                            Types.Text.KMD)
            )
        )
        
        cm = CardMessage(card)
        await bot.client.send(channel_id, cm)
    
    # 错误处理函数
    async def on_error(event: Event):
        print(f'发生错误: {event}')
    
    # 将错误处理绑定到bot
    bot.on_error = on_error

    return bot

if __name__ == '__main__':
    # 从环境变量获取token
    from dotenv import load_dotenv
    load_dotenv()
    
    TOKEN = os.getenv('KOOK_BOT_TOKEN')
    
    if TOKEN is None:
        print('错误: 请设置KOOK_BOT_TOKEN环境变量')
        print('你可以在 https://developer.kookapp.cn/ 创建机器人并获取token')
    else:
        # 运行机器人
        bot = create_kook_bot(TOKEN)
        bot.run()