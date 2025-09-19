import asyncio
import threading
import os
from dotenv import load_dotenv
from discord_bot import create_discord_bot
from kook import create_kook_bot
from forward_config import ForwardConfig
from cleanup import get_cleanup_service

# 加载环境变量
load_dotenv()

# 全局变量存储机器人实例
kook_bot_instance = None
discord_bot_instance = None

def run_discord_bot(kook_bot=None):
    """在单独线程中运行Discord机器人"""
    global discord_bot_instance
    try:
        discord_token = os.getenv('DISCORD_BOT_TOKEN')
        if discord_token:
            print('正在启动Discord机器人...')
            bot = create_discord_bot(discord_token)
            # 传递KOOK机器人实例以启用转发功能
            if kook_bot:
                from discord_bot import setup_discord_bot
                bot = setup_discord_bot(bot, discord_token, kook_bot)
                print('✅ Discord机器人已启用消息转发功能')
            else:
                from discord_bot import setup_discord_bot
                bot = setup_discord_bot(bot, discord_token)
            discord_bot_instance = bot
            bot.run(discord_token)
        else:
            print('警告: 未找到DISCORD_BOT_TOKEN，跳过Discord机器人启动')
    except Exception as e:
        print(f'Discord机器人启动失败: {e}')

def run_kook_bot():
    """在单独线程中运行KOOK机器人"""
    global kook_bot_instance
    
    async def start_kook():
        kook_token = os.getenv('KOOK_BOT_TOKEN')
        if kook_token:
            print('正在启动KOOK机器人...')
            bot = create_kook_bot(kook_token)
            global kook_bot_instance
            kook_bot_instance = bot
            await bot.start()
        else:
            print('警告: 未找到KOOK_BOT_TOKEN，跳过KOOK机器人启动')
    
    try:
        # 使用asyncio.run在新线程中运行异步函数
        asyncio.run(start_kook())
    except Exception as e:
        print(f'KOOK机器人启动失败: {e}')

def main():
    """主函数，同时启动两个机器人"""
    print('=== 多平台机器人启动器（带转发功能）===')
    print('正在检查配置...')
    
    # 加载转发配置
    config = ForwardConfig()
    forward_rules = config.get_forward_channels()
    if forward_rules:
        print(f'📋 已配置 {len(forward_rules)} 条转发规则:')
        for discord_id, kook_id in forward_rules:
            print(f'   Discord频道 {discord_id} -> KOOK频道 {kook_id}')
    else:
        print('⚠️ 未配置转发规则，消息转发功能将不可用')
        print('   请在.env文件中配置FORWARD_RULES')
    
    discord_token = os.getenv('DISCORD_BOT_TOKEN')
    kook_token = os.getenv('KOOK_BOT_TOKEN')
    
    if not discord_token and not kook_token:
        print('错误: 未找到任何机器人Token配置')
        print('请在.env文件中配置DISCORD_BOT_TOKEN和/或KOOK_BOT_TOKEN')
        return
    
    threads = []
    
    # 先启动KOOK机器人（为了获取实例）
    if kook_token:
        kook_thread = threading.Thread(target=run_kook_bot, daemon=True)
        kook_thread.start()
        threads.append(kook_thread)
        print('✅ KOOK机器人线程已启动')
        
        # 等待KOOK机器人初始化
        import time
        time.sleep(3)
        
        # 直接输出KOOK可用命令
        print('\n【KOOK可用文本命令】:')
        print('  .ping - 测试机器人是否在线')
        print('  .hello - 问候命令')
        print('------')
    
    # 启动Discord机器人（传递KOOK机器人实例）
    if discord_token:
        discord_thread = threading.Thread(target=lambda: run_discord_bot(kook_bot_instance), daemon=True)
        discord_thread.start()
        threads.append(discord_thread)
        print('✅ Discord机器人线程已启动')
    
    print('\n所有机器人已启动，按Ctrl+C退出...')
    if forward_rules:
        print('📤 消息转发功能已启用')
    
    # 启动定期清理服务
    cleanup_service = get_cleanup_service()
    cleanup_task = None
    
    try:
        # 创建并启动清理任务
        loop = asyncio.get_event_loop()
        cleanup_task = loop.create_task(cleanup_service.start_cleanup_task())
        print(f'🧹 定期清理功能已启用 (间隔: {cleanup_service.cleanup_interval}小时, 最大保留: {cleanup_service.max_age}小时)')
        
        # 保持主线程运行
        while True:
            # 检查线程状态
            alive_threads = [t for t in threads if t.is_alive()]
            if not alive_threads:
                print('所有机器人线程已停止')
                break
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print('\n正在关闭机器人...')
    except Exception as e:
        print(f'运行时错误: {e}')

if __name__ == '__main__':
    main()