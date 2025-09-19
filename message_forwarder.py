import asyncio
import aiohttp
import os
import time
from pathlib import Path
from typing import Optional, List
import discord
from khl import Bot as KookBot
from forward_config import ForwardConfig
from translator import Translator

class MessageForwarder:
    """消息转发器类"""
    
    def __init__(self, kook_bot: KookBot):
        self.kook_bot = kook_bot
        self.config = ForwardConfig()
        self.download_dir = Path("downloads")
        self.download_dir.mkdir(exist_ok=True)
        
        # 确保子目录存在
        (self.download_dir / "images").mkdir(exist_ok=True)
        (self.download_dir / "videos").mkdir(exist_ok=True)
        
        # 初始化翻译器
        self.translator = Translator()
        
    async def forward_message(self, discord_message: discord.Message) -> bool:
        """转发Discord消息到KOOK
        
        Args:
            discord_message: Discord消息对象
            
        Returns:
            bool: 是否成功转发
        """
        try:
            # 检查是否应该转发此消息
            if not self.config.should_forward_message(discord_message.author.bot):
                return False
            
            # 获取目标KOOK频道ID
            kook_channel_id = self.config.get_kook_channel_id(str(discord_message.channel.id))
            if not kook_channel_id:
                return False
            
            print(f"🔄 正在转发消息到KOOK频道 {kook_channel_id}")
            
            # 构建转发消息
            forwarded_content = await self._build_forward_message(discord_message)
            
            # 尝试直接通过KOOK机器人发送消息
            success = False
            if forwarded_content:
                try:
                    # 尝试获取频道对象
                    channel = await self.kook_bot.client.fetch_public_channel(kook_channel_id)
                    if channel:
                        await channel.send(forwarded_content)
                        print(f"✅ 直接通过KOOK机器人发送消息成功: {forwarded_content[:50]}...")
                        success = True
                except Exception as e:
                    print(f"⚠️ 直接通过KOOK机器人发送消息失败，尝试API方法: {e}")
                    # 如果直接发送失败，使用API方法
                    await self._send_text_message(kook_channel_id, forwarded_content)
                    success = True
            
            # 处理附件（图片、视频等）
            if discord_message.attachments:
                await self._forward_attachments(discord_message, kook_channel_id)
                success = True
            
            return success
            
        except Exception as e:
            print(f"转发消息失败: {e}")
            return False
    
    async def _build_forward_message(self, discord_message: discord.Message) -> str:
        """构建转发消息内容
        
        Args:
            discord_message: Discord消息对象
            
        Returns:
            str: 格式化后的消息内容
        """
        author_name = discord_message.author.display_name
        content = discord_message.content
        
        # 构建消息前缀
        prefix = self.config.message_prefix
        
        # 如果消息为空但有附件，添加提示
        if not content and discord_message.attachments:
            content = "[发送了附件]"
        
        # 翻译消息内容（如果启用了翻译功能）
        translated_content = None
        if content and self.translator.is_enabled():
            try:
                original_content = content
                translated_content = await self.translator.translate_text(content)
                
                # 如果翻译结果与原文不同，则保存译文（稍后格式化）
                if translated_content and translated_content != original_content:
                    print(f"✅ 消息已翻译: {original_content} -> {translated_content}")
                else:
                    translated_content = None
            except Exception as e:
                print(f"❌ 翻译消息时出错: {e}")
                translated_content = None
        
        # 格式化消息
        if content:
            if translated_content:
                # 使用段落样式（先显示所有原文，然后显示所有译文）
                # 原文部分
                original_content = content.strip()
                
                # 译文部分（带表情符号）
                translated_content = translated_content.strip()
                if translated_content:
                    formatted_content = f"{original_content}\n\n🔤 译文:\n{translated_content}"
                else:
                    formatted_content = original_content
                
                return f"{prefix} {author_name}:\n{formatted_content}"
            else:
                # 没有翻译时的普通格式
                return f"{prefix} {author_name}: {content}"
        
        return ""
    
    async def _send_text_message(self, kook_channel_id: str, content: str):
        """发送文字消息到KOOK频道
        
        Args:
            kook_channel_id: KOOK频道ID
            content: 消息内容
        """
        try:
            # 尝试使用kook_bot对象发送消息
            try:
                channel = await self.kook_bot.client.fetch_public_channel(kook_channel_id)
                if channel:
                    await channel.send(content)
                    print(f"✅ 使用kook_bot对象发送消息成功: {content[:50]}...")
                    return
            except Exception as e:
                print(f"⚠️ 使用kook_bot对象发送消息失败，尝试直接API调用: {e}")
            
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
                "target_id": kook_channel_id,
                "content": content,
                "type": 1  # 1表示文本消息
            }
            
            # 发送请求并添加重试机制
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, headers=headers, json=data) as response:
                            resp_json = await response.json()
                            if response.status == 200:
                                print(f"✅ 消息已通过API转发到KOOK频道 {kook_channel_id}: {content[:50]}...")
                                print(f"✅ API响应: {resp_json}")
                                return
                            else:
                                print(f"⚠️ 尝试 {attempt+1}/{max_retries}: 发送文字消息到KOOK失败: {resp_json}")
                                if attempt < max_retries - 1:
                                    await asyncio.sleep(1)  # 等待1秒后重试
                except Exception as inner_e:
                    print(f"⚠️ 尝试 {attempt+1}/{max_retries}: API请求异常: {inner_e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)  # 等待1秒后重试
            
            print(f"❌ 所有尝试都失败，无法发送消息到KOOK频道 {kook_channel_id}")
        except Exception as e:
            print(f"❌ 发送文字消息到KOOK失败: {e}")
    
    async def _forward_attachments(self, discord_message: discord.Message, kook_channel_id: str):
        """转发附件到KOOK
        
        Args:
            discord_message: Discord消息对象
            kook_channel_id: KOOK频道ID
        """
        for attachment in discord_message.attachments:
            try:
                # 下载附件
                file_path = await self._download_attachment(attachment)
                if file_path:
                    # 发送到KOOK
                    await self._send_file_to_kook(kook_channel_id, file_path, attachment.filename)
                    
                    # 清理本地文件（可选，根据配置决定）
                    await self._schedule_file_cleanup(file_path, attachment.content_type)
                    
            except Exception as e:
                print(f"❌ 转发附件失败 {attachment.filename}: {e}")
    
    async def _download_attachment(self, attachment: discord.Attachment) -> Optional[Path]:
        """下载Discord附件到本地
        
        Args:
            attachment: Discord附件对象
            
        Returns:
            Optional[Path]: 下载的文件路径，失败返回None
        """
        try:
            # 根据文件类型选择存储目录
            content_type = attachment.content_type or ""
            if content_type.startswith("image/"):
                # 图片存储在images子目录
                target_dir = self.download_dir / "images"
            elif content_type.startswith("video/"):
                # 视频存储在videos子目录
                target_dir = self.download_dir / "videos"
            else:
                # 其他文件存储在下载根目录
                target_dir = self.download_dir
            
            # 确保目标目录存在
            target_dir.mkdir(exist_ok=True)
            
            # 生成本地文件路径
            file_path = target_dir / f"{attachment.id}_{attachment.filename}"
            
            # 下载文件
            timeout = aiohttp.ClientTimeout(total=30)  # 30秒超时
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(attachment.url) as response:
                    if response.status == 200:
                        with open(file_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                        
                        print(f"📥 已下载附件到 {target_dir}: {file_path.name}")
                        return file_path
                    else:
                        print(f"❌ 下载附件失败，HTTP状态码: {response.status}")
                        return None
                        
        except Exception as e:
            print(f"❌ 下载附件异常: {e}")
            return None
    
    async def _send_file_to_kook(self, kook_channel_id: str, file_path: Path, original_filename: str):
        """发送文件到KOOK频道
        
        Args:
            kook_channel_id: KOOK频道ID
            file_path: 本地文件路径
            original_filename: 原始文件名
        """
        try:
            # 尝试使用kook_bot对象发送文件
            try:
                channel = await self.kook_bot.client.fetch_public_channel(kook_channel_id)
                if channel:
                    with open(file_path, 'rb') as f:
                        await channel.send(file=f)
                    print(f"✅ 使用kook_bot对象发送文件成功: {original_filename}")
                    return
            except Exception as e:
                print(f"⚠️ 使用kook_bot对象发送文件失败，尝试直接API调用: {e}")
            
            # 使用aiohttp直接调用KOOK API上传文件
            import os
            from dotenv import load_dotenv
            import aiohttp
            import mimetypes
            import json
            
            # 检查文件扩展名
            file_ext = os.path.splitext(original_filename)[1].lower()
            
            # 如果是不支持的格式，直接发送文件名和提示
            unsupported_formats = ['.svg', '.webp', '.tiff', '.psd']
            if file_ext in unsupported_formats:
                await self._send_text_message(kook_channel_id, f"{self.config.message_prefix} 不支持的文件格式: {original_filename}")
                print(f"⚠️ 不支持的文件格式 {file_ext}，已发送文本通知")
                return
            
            # 加载环境变量获取token
            load_dotenv()
            token = os.getenv('KOOK_BOT_TOKEN')
            
            # 获取文件MIME类型
            content_type, _ = mimetypes.guess_type(file_path)
            if not content_type:
                content_type = 'application/octet-stream'
            
            # 检查文件大小，KOOK限制为20MB
            file_size = os.path.getsize(file_path)
            if file_size > 20 * 1024 * 1024:  # 20MB
                await self._send_text_message(kook_channel_id, f"{self.config.message_prefix} 文件过大(>20MB): {original_filename}")
                print(f"⚠️ 文件过大 {file_size/1024/1024:.2f}MB，已发送文本通知")
                return
                
            # 构建API请求上传文件
            upload_url = "https://www.kookapp.cn/api/v3/asset/create"
            headers = {
                "Authorization": f"Bot {token}"
            }
            
            # 判断文件类型
            file_type = 1  # 1表示图片
            is_video = self._is_video_file(file_path)
            if is_video:
                file_type = 2  # 2表示视频/音频
            else:
                # 如果不是图片也不是视频，则为其他文件
                if not content_type.startswith('image/'):
                    file_type = 3  # 3表示其他文件
            
            # 使用aiohttp上传文件
            async with aiohttp.ClientSession() as session:
                with open(file_path, 'rb') as f:
                    form = aiohttp.FormData()
                    form.add_field('file', f, filename=original_filename, content_type=content_type)
                    form.add_field('type', str(file_type))
                    
                    async with session.post(upload_url, headers=headers, data=form) as response:
                        if response.status == 200:
                            resp_json = await response.json()
                            if resp_json.get('code') == 0 and resp_json.get('data', {}).get('url'):
                                file_url = resp_json['data']['url']
                                
                                # 根据文件类型发送不同格式的消息
                                if self._is_image_file(file_path):
                                    # 图片卡片消息
                                    await self._send_image_card(kook_channel_id, file_url, original_filename)
                                elif self._is_video_file(file_path):
                                    # 视频卡片消息
                                    await self._send_video_card(kook_channel_id, file_url, original_filename)
                                else:
                                    # 普通文件消息
                                    await self._send_text_message(kook_channel_id, f"{self.config.message_prefix} 文件: {original_filename}\n{file_url}")
                                
                                print(f"✅ 文件已上传并发送: {original_filename}")
                            else:
                                # 如果上传失败，只发送文本消息
                                await self._send_text_message(kook_channel_id, f"{self.config.message_prefix} 文件上传失败: {original_filename}")
                                print(f"❌ 文件上传成功但未获取到URL: {resp_json}")
                        else:
                            # 如果上传失败，只发送文本消息
                            await self._send_text_message(kook_channel_id, f"{self.config.message_prefix} 文件上传失败: {original_filename}")
                            print(f"❌ 上传文件到KOOK失败，HTTP状态码: {response.status}")
            
        except Exception as e:
            print(f"❌ 上传文件到KOOK异常: {e}")
            await self._send_text_message(kook_channel_id, f"{self.config.message_prefix} 文件上传失败: {original_filename}")
    
    def _is_image_file(self, file_path: Path) -> bool:
        """判断是否为图片文件"""
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        return file_path.suffix.lower() in image_extensions
    
    def _is_video_file(self, file_path: Path) -> bool:
        """判断是否为视频文件"""
        video_extensions = {'.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv'}
        return file_path.suffix.lower() in video_extensions
    
    async def _send_image_card(self, kook_channel_id: str, image_url: str, original_filename: str):
        """发送图片卡片消息到KOOK
        
        Args:
            kook_channel_id: KOOK频道ID
            image_url: 图片URL
            original_filename: 原始文件名
        """
        try:
            # 使用KOOK的卡片消息API发送图片
            import os
            from dotenv import load_dotenv
            import aiohttp
            import json
            
            # 加载环境变量获取token
            load_dotenv()
            token = os.getenv('KOOK_BOT_TOKEN')
            
            # 构建卡片消息
            card = {
                "type": "card",
                "theme": "secondary",
                "size": "lg",
                "modules": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain-text",
                            "content": f"{self.config.message_prefix} 图片: {original_filename}"
                        }
                    },
                    {
                        "type": "container",
                        "elements": [
                            {
                                "type": "image",
                                "src": image_url
                            }
                        ]
                    }
                ]
            }
            
            # 将卡片消息转换为JSON字符串
            card_content = json.dumps([card])
            
            # 构建API请求
            url = "https://www.kookapp.cn/api/v3/message/create"
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json"
            }
            data = {
                "target_id": kook_channel_id,
                "content": card_content,
                "type": 10  # 10表示卡片消息
            }
            
            # 发送请求
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        resp_json = await response.json()
                        if resp_json.get('code') == 0:
                            print(f"✅ 图片卡片消息已发送: {original_filename}")
                        else:
                            print(f"❌ 发送图片卡片消息失败: {resp_json}")
                            # 失败时回退到普通文本消息
                            await self._send_text_message(kook_channel_id, f"{self.config.message_prefix} 图片: {original_filename}\n{image_url}")
                    else:
                        print(f"❌ 发送图片卡片消息失败，HTTP状态码: {response.status}")
                        # 失败时回退到普通文本消息
                        await self._send_text_message(kook_channel_id, f"{self.config.message_prefix} 图片: {original_filename}\n{image_url}")
        except Exception as e:
            print(f"❌ 发送图片卡片消息异常: {e}")
            # 异常时回退到普通文本消息
            await self._send_text_message(kook_channel_id, f"{self.config.message_prefix} 图片: {original_filename}\n{image_url}")
    
    async def _send_video_card(self, kook_channel_id: str, video_url: str, original_filename: str):
        """发送视频卡片消息到KOOK
        
        Args:
            kook_channel_id: KOOK频道ID
            video_url: 视频URL
            original_filename: 原始文件名
        """
        try:
            # 使用KOOK的卡片消息API发送视频
            import os
            from dotenv import load_dotenv
            import aiohttp
            import json
            
            # 加载环境变量获取token
            load_dotenv()
            token = os.getenv('KOOK_BOT_TOKEN')
            
            # 构建卡片消息
            card = {
                "type": "card",
                "theme": "secondary",
                "size": "lg",
                "modules": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain-text",
                            "content": f"{self.config.message_prefix} 视频: {original_filename}"
                        }
                    },
                    {
                        "type": "video",
                        "title": original_filename,
                        "src": video_url
                    }
                ]
            }
            
            # 将卡片消息转换为JSON字符串
            card_content = json.dumps([card])
            
            # 构建API请求
            url = "https://www.kookapp.cn/api/v3/message/create"
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json"
            }
            data = {
                "target_id": kook_channel_id,
                "content": card_content,
                "type": 10  # 10表示卡片消息
            }
            
            # 发送请求
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        resp_json = await response.json()
                        if resp_json.get('code') == 0:
                            print(f"✅ 视频卡片消息已发送: {original_filename}")
                        else:
                            print(f"❌ 发送视频卡片消息失败: {resp_json}")
                            # 失败时回退到普通文本消息
                            await self._send_text_message(kook_channel_id, f"{self.config.message_prefix} 视频: {original_filename}\n{video_url}")
                    else:
                        print(f"❌ 发送视频卡片消息失败，HTTP状态码: {response.status}")
                        # 失败时回退到普通文本消息
                        await self._send_text_message(kook_channel_id, f"{self.config.message_prefix} 视频: {original_filename}\n{video_url}")
        except Exception as e:
            print(f"❌ 发送视频卡片消息异常: {e}")
            # 异常时回退到普通文本消息
            await self._send_text_message(kook_channel_id, f"{self.config.message_prefix} 视频: {original_filename}\n{video_url}")
    
    async def _schedule_file_cleanup(self, file_path: Path, content_type: Optional[str]):
        """安排文件清理
        
        Args:
            file_path: 文件路径
            content_type: 文件MIME类型
        """
        try:
            # 根据文件类型确定清理时间
            if content_type and content_type.startswith('image/'):
                cleanup_hours = int(os.getenv('IMAGE_CLEANUP_HOURS', '24'))
            elif content_type and content_type.startswith('video/'):
                cleanup_hours = int(os.getenv('VIDEO_CLEANUP_HOURS', '12'))
            else:
                cleanup_hours = 6  # 其他文件默认6小时后清理
            
            # 安排异步清理任务
            asyncio.create_task(self._cleanup_file_after_delay(file_path, cleanup_hours * 3600))
            
        except Exception as e:
            print(f"❌ 安排文件清理失败: {e}")
    
    async def _cleanup_file_after_delay(self, file_path: Path, delay_seconds: int):
        """延迟清理文件
        
        Args:
            file_path: 文件路径
            delay_seconds: 延迟秒数
        """
        try:
            await asyncio.sleep(delay_seconds)
            if file_path.exists():
                file_path.unlink()
                print(f"🗑️ 已清理文件: {file_path}")
        except Exception as e:
            print(f"❌ 清理文件失败: {e}")
            
    def start_periodic_cleanup(self):
        """启动定期清理任务"""
        asyncio.create_task(self._run_periodic_cleanup())
        print("✅ 已启动定期清理任务")
        
    async def _run_periodic_cleanup(self):
        """运行定期清理任务"""
        while True:
            try:
                # 每天运行一次清理
                await asyncio.sleep(24 * 3600)  # 24小时
                await self._cleanup_old_files()
            except Exception as e:
                print(f"❌ 定期清理任务异常: {e}")
                # 出错后等待1小时再重试
                await asyncio.sleep(3600)
                
    async def _cleanup_old_files(self):
        """清理所有过期文件"""
        try:
            # 获取清理时间配置
            image_max_age = int(os.getenv('IMAGE_MAX_AGE_DAYS', '7')) * 24 * 3600  # 默认7天
            video_max_age = int(os.getenv('VIDEO_MAX_AGE_DAYS', '3')) * 24 * 3600  # 默认3天
            other_max_age = int(os.getenv('OTHER_MAX_AGE_DAYS', '1')) * 24 * 3600  # 默认1天
            
            # 当前时间
            now = time.time()
            
            # 清理图片目录
            await self._cleanup_directory(self.download_dir / "images", now, image_max_age)
            
            # 清理视频目录
            await self._cleanup_directory(self.download_dir / "videos", now, video_max_age)
            
            # 清理其他文件
            await self._cleanup_directory(self.download_dir, now, other_max_age, exclude_dirs=True)
            
            print(f"✅ 定期清理完成")
        except Exception as e:
            print(f"❌ 清理过期文件失败: {e}")
            
    async def _cleanup_directory(self, directory: Path, now: float, max_age: int, exclude_dirs: bool = False):
        """清理指定目录中的过期文件
        
        Args:
            directory: 目录路径
            now: 当前时间戳
            max_age: 最大保留时间（秒）
            exclude_dirs: 是否排除子目录
        """
        if not directory.exists() or not directory.is_dir():
            return
            
        try:
            deleted_count = 0
            for item in directory.iterdir():
                # 跳过目录（如果设置了exclude_dirs）
                if exclude_dirs and item.is_dir():
                    continue
                    
                # 只处理文件
                if item.is_file():
                    # 获取文件修改时间
                    mtime = item.stat().st_mtime
                    age = now - mtime
                    
                    # 如果文件超过最大保留时间，则删除
                    if age > max_age:
                        item.unlink()
                        deleted_count += 1
                        
            if deleted_count > 0:
                print(f"🗑️ 已从 {directory} 清理 {deleted_count} 个过期文件")
        except Exception as e:
            print(f"❌ 清理目录 {directory} 失败: {e}")
    
    def reload_config(self):
        """重新加载配置"""
        self.config.reload_config()