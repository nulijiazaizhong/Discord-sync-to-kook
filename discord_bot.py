import discord
from discord.ext import commands
from discord import app_commands
import os
from message_forwarder import MessageForwarder

def create_discord_bot(token):
    """创建Discord机器人实例"""
    # 创建机器人实例，设置命令前缀和权限
    intents = discord.Intents.default()
    intents.message_content = True  # 启用消息内容权限
    bot = commands.Bot(command_prefix='/', intents=intents)
    
    return bot

def setup_discord_bot(bot, token, kook_bot=None):
    """设置Discord机器人的事件和命令"""
    
    # 初始化消息转发器
    forwarder = None
    if kook_bot:
        forwarder = MessageForwarder(kook_bot)
        print("✅ 消息转发器已初始化")
    
    # 当机器人准备就绪时触发
    @bot.event
    async def on_ready():
        print(f'{bot.user} 已成功登录！')
        print(f'机器人ID: {bot.user.id}')
        try:
            synced = await bot.tree.sync()
            print(f'同步了 {len(synced)} 个斜杠命令')
            # 启动定期清理任务
            if forwarder:
                bot.loop.create_task(forwarder._run_periodic_cleanup())
                print('📤 定期清理任务已启动')
        except Exception as e:
            print('Discord机器人启动时发生错误')
            print(f'错误: {e}')
        print('------')

    # 当有新消息时触发
    @bot.event
    async def on_message(message):
        # 记录所有消息（包括机器人消息），携带平台标识和频道ID
        author_type = "机器人" if message.author.bot else "用户"
        print(f"[Discord] [频道ID: {message.channel.id}] [{message.channel.name}] {author_type} {message.author.display_name}: {message.content}")
        
        # 避免机器人回复自己的消息，但仍然监听
        if message.author == bot.user:
            # 处理命令后直接返回，不执行其他响应逻辑
            await bot.process_commands(message)
            return
        
        # 尝试转发消息到KOOK
        if forwarder:
            try:
                success = await forwarder.forward_message(message)
                if success:
                    print(f"📤 消息已转发: {message.content[:30]}...")
            except Exception as e:
                print(f"❌ 转发消息时出错: {e}")
        
        # 如果消息内容是"hello"，机器人回复（只对非机器人用户）
        if message.content.lower() == 'hello' and not message.author.bot:
            await message.channel.send(f'你好, {message.author.mention}！')
        
        # 处理命令
        await bot.process_commands(message)

    # 斜杠命令：ping
    @bot.tree.command(name='ping', description='检查机器人延迟')
    async def ping(interaction: discord.Interaction):
        """检查机器人延迟"""
        latency = round(bot.latency * 1000)
        await interaction.response.send_message(f'pong! in {latency}ms')

    # 传统命令：ping（保留兼容性）
    @bot.command(name='ping')
    async def ping_legacy(ctx):
        """检查机器人延迟（传统命令）"""
        latency = round(bot.latency * 1000)
        await ctx.send(f'pong! in {latency}ms')

    # 斜杠命令：greet
    @bot.tree.command(name='greet', description='问候指定用户')
    @app_commands.describe(name='要问候的用户名（可选）')
    async def greet(interaction: discord.Interaction, name: str = None):
        """问候指定用户"""
        if name is None:
            name = interaction.user.display_name
        await interaction.response.send_message(f'你好, {name}！欢迎使用Discord机器人！')

    # 传统命令：greet（保留兼容性）
    @bot.command(name='greet')
    async def greet_legacy(ctx, *, name=None):
        """问候指定用户（传统命令）"""
        if name is None:
            name = ctx.author.display_name
        await ctx.send(f'你好, {name}！欢迎使用Discord机器人！')

    # 斜杠命令：serverinfo
    @bot.tree.command(name='serverinfo', description='显示服务器信息')
    async def serverinfo(interaction: discord.Interaction):
        """显示服务器信息"""
        guild = interaction.guild
        embed = discord.Embed(
            title=f'{guild.name} 服务器信息',
            color=discord.Color.blue()
        )
        embed.add_field(name='服务器ID', value=guild.id, inline=True)
        embed.add_field(name='成员数量', value=guild.member_count, inline=True)
        embed.add_field(name='创建时间', value=guild.created_at.strftime('%Y-%m-%d'), inline=True)
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        
        await interaction.response.send_message(embed=embed)

    # 传统命令：serverinfo（保留兼容性）
    @bot.command(name='serverinfo')
    async def serverinfo_legacy(ctx):
        """显示服务器信息（传统命令）"""
        guild = ctx.guild
        embed = discord.Embed(
            title=f'{guild.name} 服务器信息',
            color=discord.Color.blue()
        )
        embed.add_field(name='服务器ID', value=guild.id, inline=True)
        embed.add_field(name='成员数量', value=guild.member_count, inline=True)
        embed.add_field(name='创建时间', value=guild.created_at.strftime('%Y-%m-%d'), inline=True)
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        
        await ctx.send(embed=embed)

    # 斜杠命令：listening
    @bot.tree.command(name='listening', description='显示机器人监听状态')
    async def listening(interaction: discord.Interaction):
        """显示机器人监听状态"""
        embed = discord.Embed(
            title='🎧 消息监听状态',
            description='机器人正在监听所有频道消息',
            color=discord.Color.green()
        )
        embed.add_field(
            name='监听范围',
            value='✅ 用户消息\n✅ 机器人消息\n✅ 所有频道',
            inline=False
        )
        embed.add_field(
            name='记录位置',
            value='控制台输出',
            inline=False
        )
        await interaction.response.send_message(embed=embed)

    # 传统命令：listening（保留兼容性）
    @bot.command(name='listening')
    async def listening_legacy(ctx):
        """显示机器人监听状态（传统命令）"""
        embed = discord.Embed(
            title='🎧 消息监听状态',
            description='机器人正在监听所有频道消息',
            color=discord.Color.green()
        )
        embed.add_field(
            name='监听范围',
            value='✅ 用户消息\n✅ 机器人消息\n✅ 所有频道',
            inline=False
        )
        embed.add_field(
            name='记录位置',
            value='控制台输出',
            inline=False
        )
        await ctx.send(embed=embed)

    # 错误处理
    @bot.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send('未找到该命令！使用 `/help` 查看可用命令。')
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send('缺少必需的参数！')
        else:
            print(f'发生错误: {error}')

    return bot

if __name__ == '__main__':
    # 从环境变量获取token，或者直接在这里填入你的机器人token
    from dotenv import load_dotenv
    load_dotenv()
    
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    
    if TOKEN is None:
        print('错误: 请设置DISCORD_BOT_TOKEN环境变量或在代码中直接填入token')
        print('你可以在 https://discord.com/developers/applications 创建机器人并获取token')
    else:
        bot, token = create_discord_bot(TOKEN)
        bot.run(token)