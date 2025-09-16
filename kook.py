import asyncio
import json
import aiohttp
from khl import Bot, Message, Event, EventTypes
from khl.card import CardMessage, Card, Module, Element, Types, Struct
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
    
    return setup_kook_bot(bot)

def setup_kook_bot(bot):
    """设置KOOK机器人的事件和命令"""
    
    # 机器人启动事件处理函数
    async def on_startup():
        print(f'KOOK机器人已成功启动！')
        print('------')
    
    # 将启动事件绑定到bot
    bot.on_startup = on_startup

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
        latency = round(bot.client.latency * 1000)
        await msg.reply(f'pong! 延迟: {latency}ms')

    # 文本命令：hello
    @bot.command(name='hello')
    async def hello(msg: Message, name: str = None):
        """问候命令"""
        if name is None:
            name = msg.author.username
        await msg.reply(f'你好, {name}！欢迎使用KOOK机器人！')

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