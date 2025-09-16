from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image, Video, At, AtAll, File
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_session import MessageSesion
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.filter.platform_adapter_type import PlatformAdapterType
from pathlib import Path
import asyncio
import json
import aiohttp
import os
from .translation_service import TranslationService
from .translation_commands import TranslationCommandHandler

@register("discord_to_kook_forwarder", "AstrBot Community", "Discord消息转发到Kook插件", "1.0.0", "https://github.com/AstrBotDevs/AstrBot")
class DiscordToKookForwarder(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 从插件元数据获取配置实例
        self.plugin_config = None
        self.config = {}
        
        # 查找当前插件的配置
        try:
            # 尝试多种方式获取plugin_config
            all_stars = context.get_all_stars()
            logger.info(f"🔍 搜索插件配置，总共有 {len(all_stars)} 个插件")
            
            for plugin_md in all_stars:
                logger.debug(f"检查插件: {plugin_md.name}")
                if plugin_md.name in ["discord_to_kook_forwarder", "Discord_sync_to_kook", "astrbot_plugin_Discord_sync_to_kook"]:
                    logger.info(f"🎯 找到匹配的插件: {plugin_md.name}")
                    if hasattr(plugin_md, 'config') and plugin_md.config:
                        try:
                            self.plugin_config = plugin_md.config
                            # 尝试转换为字典
                            if hasattr(plugin_md.config, 'keys'):
                                self.config = dict(plugin_md.config)
                            logger.info(f"✅ 成功获取插件配置对象: {type(self.plugin_config)}")
                            break
                        except Exception as e:
                            logger.warning(f"❌ 配置转换失败: {e}")
            
            # 如果没有找到配置对象，尝试从context直接获取
            if not self.plugin_config:
                logger.info("🔄 尝试从context直接获取配置")
                if hasattr(context, 'config'):
                    self.plugin_config = context.config
                    logger.info(f"✅ 从context获取配置对象: {type(self.plugin_config)}")
                    
        except Exception as e:
            logger.warning(f"❌ 获取插件配置对象失败: {e}")
            self.plugin_config = None
        
        # 如果没有配置文件，使用默认值
        if not self.config:
            self.config = {
                "enabled": True,
                "discord_platform_id": "",  # Discord平台适配器ID
                "kook_platform_id": "",     # Kook平台适配器ID
                "forward_channels": {},      # Discord频道ID -> Kook频道ID的映射
                "forward_all_channels": True,  # 是否转发所有频道
                "default_discord_channel": "",  # 默认Discord频道ID
                "default_kook_channel": "",  # 默认Kook频道ID
                "include_bot_messages": False,  # 是否包含机器人消息
                "message_prefix": "[Discord] ",  # 消息前缀
                "image_cleanup_hours": 24,  # 图片文件自动清理时间（小时），设置为0表示不自动清理
                "video_cleanup_hours": 24,  # 视频文件自动清理时间（小时），设置为0表示不自动清理
                "channel_mappings": [],  # 多频道映射配置（数组格式）
                # 翻译功能配置
                "translation_enabled": False,  # 是否启用翻译功能
                "translation_platform": "google",  # 翻译平台: google, baidu, youdao, deepl
                "translation_source_lang": "auto",  # 源语言，auto表示自动检测
                "translation_target_lang": "zh",  # 目标语言
                "translation_api_key": "",  # API密钥
                "translation_api_secret": "",  # API密钥（某些平台需要）
                "translation_api_url": "",  # 自定义API地址（可选）
                "translation_only_text": True,  # 是否只翻译纯文本消息
                "translation_min_length": 10,  # 最小翻译长度（字符数）
            }
        
        self.discord_platform = None
        self.kook_platform = None
        self.translation_service = None
        self.translation_command_handler = None

    async def initialize(self):
        """初始化插件，获取Discord和Kook平台实例"""
        try:
            # 加载配置
            await self._load_config()
            
            # 重新初始化翻译服务
            self.translation_service = TranslationService(self.config)
            logger.info(f"✅ 翻译服务重新初始化完成，启用状态: {self.translation_service.is_enabled()}")
            
            # 更新翻译命令处理器的配置
            if self.translation_command_handler:
                self.translation_command_handler.translation_service = self.translation_service
            
            # 初始化翻译命令处理器
            self.translation_command_handler = TranslationCommandHandler(self, self.translation_service)
            logger.info("✅ 翻译命令处理器初始化完成")
            
            # 尝试获取平台实例（如果失败不影响插件加载）
            try:
                await self._get_platform_instances()
                
                if self.discord_platform and self.kook_platform:
                    logger.info("✅ Discord到Kook转发插件初始化成功")
                else:
                    logger.warning("⚠️ 部分平台适配器未找到，插件将在运行时动态获取")
            except Exception as platform_error:
                logger.warning(f"⚠️ 初始化时获取平台实例失败: {platform_error}，插件将在运行时动态获取")
            
            logger.info("✅ Discord到Kook转发插件加载完成")
        except Exception as e:
            logger.error(f"❌ Discord到Kook转发插件初始化失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _load_config(self):
        """加载插件配置（优先使用WebUI配置）"""
        try:
            # 首先从config.json文件加载基础配置
            from pathlib import Path
            
            plugin_dir = Path(__file__).parent
            config_file = plugin_dir / "config.json"
            
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                
                # 合并配置作为基础
                self.config.update(file_config)
                logger.info(f"📄 从config.json加载基础配置: {list(file_config.keys())}")
            else:
                logger.info("📄 config.json不存在，创建默认配置文件")
                # 创建默认配置文件
                self._create_default_config_file()
                
            # 优先使用WebUI配置并同步到文件
            await self._sync_webui_config()
                
        except Exception as e:
            logger.warning(f"⚠️ 加载配置文件失败: {e}，使用默认配置")
            # 即使加载失败也要尝试同步WebUI配置
            try:
                await self._sync_webui_config()
            except Exception as sync_e:
                logger.warning(f"⚠️ 同步WebUI配置也失败: {sync_e}")
    
    def _create_default_config_file(self):
        """创建默认的config.json配置文件"""
        try:
            from pathlib import Path
            
            plugin_dir = Path(__file__).parent
            config_file = plugin_dir / "config.json"
            
            # 使用当前内存中的默认配置
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 已创建默认配置文件: {config_file}")
            
        except Exception as e:
            logger.error(f"❌ 创建默认配置文件失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _sync_webui_config(self):
        """同步WebUI配置到内存和config.json文件（WebUI配置优先）"""
        try:
            # 如果有plugin_config对象，从中读取最新配置
            if self.plugin_config:
                webui_config = {}
                
                # WebUI配置字段名映射（WebUI字段名 -> config.json字段名）
                webui_field_mapping = {
                    # 基础配置
                    'enabled': 'enabled',
                    'discord_platform_id': 'discord_platform_id', 
                    'kook_platform_id': 'kook_platform_id',
                    'forward_channels': 'forward_channels',
                    'forward_all_channels': 'forward_all_channels',
                    'default_discord_channel': 'default_discord_channel',
                    'default_kook_channel': 'default_kook_channel',
                    'include_bot_messages': 'include_bot_messages',
                    'message_prefix': 'message_prefix',
                    'image_cleanup_hours': 'image_cleanup_hours',
                    'video_cleanup_hours': 'video_cleanup_hours',
                    'channel_mappings': 'channel_mappings',
                    # 翻译功能配置
                    'translation_enabled': 'translation_enabled',
                    'translation_platform': 'translation_platform',
                    'translation_source_lang': 'translation_source_lang',
                    'translation_target_lang': 'translation_target_lang',
                    'translation_api_key': 'translation_api_key',
                    'translation_api_secret': 'translation_api_secret',
                    'translation_api_url': 'translation_api_url',
                    'translation_only_text': 'translation_only_text',
                    'translation_min_length': 'translation_min_length',
                    # 可能的WebUI字段名变体
                    'enable': 'enabled',
                    'is_enabled': 'enabled',
                    'forward_all': 'forward_all_channels',
                    'all_channels': 'forward_all_channels',
                    'default_discord': 'default_discord_channel',
                    'discord_channel': 'default_discord_channel',
                    'default_channel': 'default_kook_channel',
                    'kook_channel': 'default_kook_channel',
                    'bot_messages': 'include_bot_messages',
                    'include_bots': 'include_bot_messages',
                    'prefix': 'message_prefix',
                    'msg_prefix': 'message_prefix'
                }
                
                logger.info("🔍 开始读取WebUI配置...")
                
                # 尝试读取所有可能的WebUI字段
                for webui_key, config_key in webui_field_mapping.items():
                    try:
                        value = None
                        
                        # 尝试多种方式读取配置值
                        if hasattr(self.plugin_config, '__getitem__'):
                            try:
                                value = self.plugin_config[webui_key]
                            except (KeyError, TypeError):
                                pass
                        
                        if value is None and hasattr(self.plugin_config, 'get'):
                            try:
                                value = self.plugin_config.get(webui_key)
                            except Exception:
                                pass
                        
                        if value is None and hasattr(self.plugin_config, webui_key):
                            try:
                                value = getattr(self.plugin_config, webui_key)
                            except Exception:
                                pass
                        
                        # 如果读取到有效值，添加到webui_config
                        if value is not None:
                            webui_config[config_key] = value
                            logger.info(f"📋 WebUI配置 {webui_key} -> {config_key}: {value}")
                            
                    except Exception as e:
                        logger.debug(f"⚠️ 读取WebUI配置项 {webui_key} 失败: {e}")
                        continue
                
                # 强制使用WebUI配置更新内存配置
                if webui_config:
                    logger.info(f"🔄 使用WebUI配置更新内存配置: {list(webui_config.keys())}")
                    
                    # 特殊处理channel_mappings字段 - 转换为forward_channels
                    if 'channel_mappings' in webui_config:
                        channel_mappings_text = webui_config['channel_mappings']
                        logger.info(f"📋 解析频道映射配置: {channel_mappings_text}")
                        
                        # 根据配置类型选择解析方法
                        if isinstance(channel_mappings_text, str):
                            # 新的文本格式："Discord频道ID 空格 Kook频道ID"
                            parsed_mappings = self._parse_channel_mappings_text(channel_mappings_text)
                        elif isinstance(channel_mappings_text, list):
                            # 旧的数组格式（向下兼容）
                            parsed_mappings = self._parse_channel_mappings_array(channel_mappings_text)
                        else:
                            logger.warning(f"⚠️ 不支持的channel_mappings格式: {type(channel_mappings_text)}")
                            parsed_mappings = {}
                        
                        # 更新forward_channels配置
                        webui_config['forward_channels'] = parsed_mappings
                        logger.info(f"✅ 解析后的频道映射: {parsed_mappings}")
                        
                        # 移除channel_mappings，避免重复存储
                        del webui_config['channel_mappings']
                    
                    # 如果WebUI直接提供了forward_channels，也要处理
                    elif 'forward_channels' in webui_config:
                        forward_channels = webui_config['forward_channels']
                        if isinstance(forward_channels, dict):
                            logger.info(f"📋 直接使用WebUI的forward_channels配置: {forward_channels}")
                        else:
                            logger.warning(f"⚠️ WebUI的forward_channels格式不正确: {type(forward_channels)}")
                            webui_config['forward_channels'] = {}
                    
                    self.config.update(webui_config)
                    
                    # 强制同步到config.json（确保WebUI配置持久化）
                    logger.info("💾 强制同步WebUI配置到config.json")
                    self._save_config()
                else:
                    logger.warning("⚠️ 未能从WebUI读取到任何配置，使用现有配置")
                    # 即使没有读取到WebUI配置，也创建config.json文件
                    logger.info("📝 创建基础config.json文件")
                    self._save_config()
            else:
                logger.warning("⚠️ plugin_config对象不存在，无法读取WebUI配置")
                # 没有plugin_config时也要确保config.json存在
                logger.info("📝 确保config.json文件存在")
                self._save_config()
                        
        except Exception as e:
            logger.error(f"❌ 同步WebUI配置失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # 即使同步失败，也要确保config.json存在
            try:
                self._save_config()
            except Exception as save_e:
                logger.error(f"❌ 保存配置文件也失败: {save_e}")
    
    def _parse_channel_mappings_array(self, mappings_array: list) -> dict:
        """解析数组格式的频道映射配置
        
        Args:
            mappings_array: 数组格式的映射配置，如：
                [{"discord_channel": "123456789", "kook_channel": "987654321"}]
        
        Returns:
            dict: 解析后的频道映射字典
        """
        mappings = {}
        
        if not mappings_array:
            logger.info("📋 频道映射配置为空")
            return mappings
        
        try:
            for index, mapping in enumerate(mappings_array):
                if not isinstance(mapping, dict):
                    logger.warning(f"⚠️ 第{index+1}个映射不是字典格式: {mapping}")
                    continue
                
                discord_id = mapping.get('discord_channel', '').strip()
                kook_id = mapping.get('kook_channel', '').strip()
                
                if discord_id and kook_id:
                    mappings[discord_id] = kook_id
                    logger.info(f"📝 解析映射 {index+1}: {discord_id} -> {kook_id}")
                else:
                    logger.warning(f"⚠️ 第{index+1}个映射ID为空: discord='{discord_id}', kook='{kook_id}'")
            
            logger.info(f"✅ 成功解析 {len(mappings)} 个频道映射")
            
        except Exception as e:
            logger.error(f"❌ 解析频道映射配置失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        return mappings
    
    def _parse_channel_mappings_text(self, mappings_text: str) -> dict:
        """解析新的文本格式的频道映射配置
        
        Args:
            mappings_text: 文本格式的映射配置，如：
                "1416029491796381806 3467992097213849\n1234567890123456 9876543210987654"
        
        Returns:
            dict: 解析后的频道映射字典
        """
        mappings = {}
        
        if not mappings_text or not mappings_text.strip():
            logger.info("📋 频道映射配置为空")
            return mappings
        
        try:
            # 按行分割
            lines = mappings_text.strip().split('\n')
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue  # 跳过空行
                
                # 按空格分割
                parts = line.split()
                if len(parts) == 2:
                    discord_id = parts[0].strip()
                    kook_id = parts[1].strip()
                    
                    if discord_id and kook_id:
                        mappings[discord_id] = kook_id
                        logger.info(f"📝 解析映射 {line_num}: {discord_id} -> {kook_id}")
                    else:
                        logger.warning(f"⚠️ 第{line_num}行映射格式错误（ID为空）: {line}")
                elif len(parts) > 2:
                    # 如果有多个空格，取第一个和最后一个作为频道ID
                    discord_id = parts[0].strip()
                    kook_id = parts[-1].strip()
                    
                    if discord_id and kook_id:
                        mappings[discord_id] = kook_id
                        logger.info(f"📝 解析映射 {line_num}: {discord_id} -> {kook_id}")
                        logger.warning(f"⚠️ 第{line_num}行包含多个空格，已取首尾作为频道ID: {line}")
                    else:
                        logger.warning(f"⚠️ 第{line_num}行映射格式错误（ID为空）: {line}")
                else:
                    logger.warning(f"⚠️ 第{line_num}行缺少空格分隔符: {line}")
            
            logger.info(f"✅ 成功解析 {len(mappings)} 个频道映射")
            
        except Exception as e:
            logger.error(f"❌ 解析频道映射配置失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        return mappings
    
    def _parse_channel_mappings(self, mappings_text: str) -> dict:
        """解析文本格式的频道映射配置（向下兼容旧格式）
        
        Args:
            mappings_text: 文本格式的映射配置，如：
                "1234567891112 -> 123456789\n9876543210000 -> 987654321"
        
        Returns:
            dict: 解析后的频道映射字典
        """
        mappings = {}
        
        if not mappings_text or not mappings_text.strip():
            logger.info("📋 频道映射配置为空")
            return mappings
        
        try:
            # 按行分割
            lines = mappings_text.strip().split('\n')
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue  # 跳过空行
                
                # 查找箭头分隔符
                if '->' in line:
                    parts = line.split('->', 1)
                    if len(parts) == 2:
                        discord_id = parts[0].strip()
                        kook_id = parts[1].strip()
                        
                        if discord_id and kook_id:
                            mappings[discord_id] = kook_id
                            logger.info(f"📝 解析映射 {line_num}: {discord_id} -> {kook_id}")
                        else:
                            logger.warning(f"⚠️ 第{line_num}行映射格式错误（ID为空）: {line}")
                    else:
                        logger.warning(f"⚠️ 第{line_num}行映射格式错误（分割失败）: {line}")
                else:
                    logger.warning(f"⚠️ 第{line_num}行缺少箭头分隔符: {line}")
            
            logger.info(f"✅ 成功解析 {len(mappings)} 个频道映射")
            
        except Exception as e:
            logger.error(f"❌ 解析频道映射配置失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        return mappings
    
    def _save_config(self):
        """保存插件配置到文件"""
        try:
            # 尝试多种方式保存配置
            saved = False
            
            # 方式1：使用plugin_config对象（确保WebUI配置能够正确保存）
            if self.plugin_config:
                try:
                    # 更新配置对象，特别处理channel_mappings
                    for key, value in self.config.items():
                        # 跳过forward_channels，因为它是内部使用的
                        if key == 'forward_channels':
                            continue
                            
                        if hasattr(self.plugin_config, '__setitem__'):
                            self.plugin_config[key] = value
                        elif hasattr(self.plugin_config, key):
                            setattr(self.plugin_config, key, value)
                    
                    # 特别处理channel_mappings - 确保WebUI能够编辑（文本格式）
                    if 'forward_channels' in self.config and self.config['forward_channels']:
                        mappings_lines = []
                        for discord_id, kook_id in self.config['forward_channels'].items():
                            mappings_lines.append(f"{discord_id} {kook_id}")
                        
                        mappings_text = '\n'.join(mappings_lines)
                        
                        # 保存到plugin_config的channel_mappings字段
                        if hasattr(self.plugin_config, '__setitem__'):
                            self.plugin_config['channel_mappings'] = mappings_text
                        elif hasattr(self.plugin_config, 'channel_mappings'):
                            setattr(self.plugin_config, 'channel_mappings', mappings_text)
                        
                        logger.info(f"📝 更新WebUI的channel_mappings配置: {len(mappings_lines)} 个映射")
                    else:
                        # 如果没有映射，设置为空字符串
                        if hasattr(self.plugin_config, '__setitem__'):
                            self.plugin_config['channel_mappings'] = ""
                        elif hasattr(self.plugin_config, 'channel_mappings'):
                            setattr(self.plugin_config, 'channel_mappings', "")
                    
                    # 检查save方法是否存在且可调用
                    if hasattr(self.plugin_config, 'save') and callable(getattr(self.plugin_config, 'save', None)):
                        self.plugin_config.save()
                        saved = True
                        logger.info("✅ 插件配置已保存到WebUI（方式1）")
                    else:
                        logger.debug("📋 plugin_config对象没有可调用的save方法，跳过方式1")
                except Exception as e:
                    logger.warning(f"⚠️ 方式1保存失败: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
            
            # 方式2：直接写入配置文件（始终执行，确保WebUI配置同步）
            try:
                import os
                from pathlib import Path
                
                plugin_dir = Path(__file__).parent
                config_file = plugin_dir / "config.json"
                
                # 准备保存的配置，包含转换后的channel_mappings
                save_config = self.config.copy()
                
                # 将forward_channels字典转换为channel_mappings文本格式
                if 'forward_channels' in save_config and save_config['forward_channels']:
                    mappings_lines = []
                    for discord_id, kook_id in save_config['forward_channels'].items():
                        mappings_lines.append(f"{discord_id} {kook_id}")
                    save_config['channel_mappings'] = '\n'.join(mappings_lines)
                    logger.info(f"📝 转换频道映射为文本格式: {len(mappings_lines)} 个映射")
                else:
                    save_config['channel_mappings'] = ""
                
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(save_config, f, ensure_ascii=False, indent=2)
                
                saved = True
                logger.info("✅ 插件配置已同步到config.json")
            except Exception as e:
                logger.warning(f"⚠️ 同步config.json失败: {e}")
            
            if not saved:
                logger.warning("❌ 所有配置保存方式都失败，配置未保存")
        except Exception as e:
            logger.error(f"❌ 保存插件配置失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _get_platform_instances(self):
        """获取Discord和Kook平台实例"""
        platform_manager = self.context.platform_manager
        
        # 调试信息：显示所有可用的平台适配器
        logger.info("=== 当前系统中的所有平台适配器 ===")
        for i, platform in enumerate(platform_manager.platform_insts):
            platform_meta = platform.meta()
            logger.info(f"平台 {i+1}: 名称='{platform_meta.name}', ID='{platform_meta.id}', 描述='{platform_meta.description}'")
        logger.info("=== 平台适配器列表结束 ===")
        
        # 查找Discord平台
        for platform in platform_manager.platform_insts:
            platform_meta = platform.meta()
            if platform_meta.name == "discord":
                self.discord_platform = platform
                self.config["discord_platform_id"] = platform_meta.id
                logger.info(f"✅ 找到Discord平台: {platform_meta.id}")
                break
        else:
            logger.warning("❌ 未找到Discord平台适配器")
        
        # 查找Kook平台（通过插件提供的适配器）
        # 尝试多种可能的名称匹配
        kook_names = ["kook", "kaiheila", "开黑啦"]
        for platform in platform_manager.platform_insts:
            platform_meta = platform.meta()
            platform_name_lower = platform_meta.name.lower()
            
            # 检查是否匹配任何Kook相关的名称
            if any(name.lower() in platform_name_lower for name in kook_names):
                self.kook_platform = platform
                self.config["kook_platform_id"] = platform_meta.id
                logger.info(f"✅ 找到Kook平台: 名称='{platform_meta.name}', ID='{platform_meta.id}'")
                break
        else:
            logger.warning(f"❌ 未找到Kook平台适配器。尝试匹配的名称: {kook_names}")
            logger.warning("请确保Kook适配器插件已正确安装并启用")

    @filter.platform_adapter_type(PlatformAdapterType.DISCORD)
    async def on_discord_message(self, event: AstrMessageEvent):
        """监听Discord消息并转发到Kook"""
        try:
            logger.info(f"🔔 接收到Discord消息: 发送者={event.get_sender_name()}, 内容='{event.message_str}', 平台={event.get_platform_name()}")
            
            # 每次处理消息前同步WebUI配置（确保实时响应WebUI配置变更）
            await self._sync_webui_config()
            
            if not self.config["enabled"]:
                logger.info("❌ 转发功能已禁用，跳过消息")
                return
            
            # 动态检查和获取平台实例（解决重启后需要重载的问题）
            if not self.kook_platform:
                logger.info("🔄 Kook平台实例未找到，尝试重新获取...")
                await self._get_platform_instances()
                
            if not self.kook_platform:
                logger.warning("❌ Kook平台未找到，无法转发消息")
                return
            
            # 检查是否应该转发此消息
            should_forward = await self._should_forward_message(event)
            logger.info(f"📋 消息转发检查结果: {should_forward}")
            if not should_forward:
                return
            
            # 转换消息格式
            forwarded_message = await self._convert_message_for_kook(event)
            logger.info(f"🔄 消息格式转换完成，消息链长度: {len(forwarded_message.chain)}")
            
            # 确定目标Kook频道
            target_channel = await self._get_target_kook_channel(event)
            logger.info(f"🎯 目标Kook频道: {target_channel}")
            
            if target_channel:
                # 发送到Kook
                await self._send_to_kook(target_channel, forwarded_message)
                logger.info(f"✅ 已转发Discord消息到Kook频道: {target_channel}")
            else:
                logger.warning("❌ 未找到对应的Kook频道，消息未转发")
                
        except Exception as e:
            logger.error(f"❌ 转发Discord消息到Kook时发生错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def on_config_changed(self):
        """配置变更回调 - 当WebUI配置发生变化时触发"""
        try:
            logger.info("🔄 检测到配置变更，重新加载配置...")
            await self._sync_webui_config()
            logger.info("✅ 配置重新加载完成")
        except Exception as e:
            logger.error(f"❌ 配置重新加载失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _should_forward_message(self, event: AstrMessageEvent) -> bool:
        """判断是否应该转发此消息"""
        # 检查是否包含机器人消息
        # 优先使用is_bot属性，如果没有则回退到原来的逻辑
        is_bot_message = False
        if hasattr(event.message_obj.sender, 'is_bot'):
            is_bot_message = event.message_obj.sender.is_bot
            logger.info(f"🤖 机器人消息检查(使用is_bot属性): 发送者={event.message_obj.sender.nickname}, is_bot={is_bot_message}")
        else:
            # 回退到原来的逻辑：检查是否是自己发送的消息
            is_bot_message = event.message_obj.sender.user_id == event.message_obj.self_id
            logger.info(f"🤖 机器人消息检查(回退逻辑): 发送者ID={event.message_obj.sender.user_id}, 机器人ID={event.message_obj.self_id}, 是否机器人消息={is_bot_message}")
        
        if not self.config["include_bot_messages"] and is_bot_message:
            logger.info("❌ 跳过机器人消息（配置不包含机器人消息）")
            return False
        
        # 获取Discord频道ID
        discord_channel_id = event.message_obj.group_id or event.session_id
        logger.info(f"📍 Discord频道ID: {discord_channel_id}")
        
        # 检查频道配置
        if self.config["forward_all_channels"]:
            logger.info("✅ 转发所有频道已启用，允许转发")
            return True
        
        # 多频道映射检查 - 优先级最高
        if discord_channel_id in self.config["forward_channels"]:
            logger.info(f"✅ 频道在多频道映射列表中: {discord_channel_id} -> {self.config['forward_channels'][discord_channel_id]}")
            return True
        
        # 默认频道检查 - 向下兼容
        default_discord_channel = self.config.get("default_discord_channel")
        default_kook_channel = self.config.get("default_kook_channel")
        
        # 如果是默认Discord频道且有默认Kook频道
        if default_discord_channel and discord_channel_id == default_discord_channel and default_kook_channel:
            logger.info(f"✅ 匹配默认Discord频道: {discord_channel_id} -> {default_kook_channel}")
            return True
        
        # 如果没有配置默认Discord频道，但有默认Kook频道（向下兼容旧配置）
        if not default_discord_channel and default_kook_channel:
            logger.info(f"✅ 使用默认Kook频道（向下兼容）: {discord_channel_id} -> {default_kook_channel}")
            return True
        
        logger.info(f"❌ 频道不在转发范围内: {discord_channel_id}")
        logger.info(f"   - 多频道映射: {list(self.config['forward_channels'].keys())}")
        logger.info(f"   - 默认Discord频道: {default_discord_channel}")
        logger.info(f"   - 默认Kook频道: {default_kook_channel}")
        
        return False

    async def _convert_message_for_kook(self, event: AstrMessageEvent) -> MessageChain:
        """将Discord消息转换为Kook格式"""
        message_chain = MessageChain()
        
        # 添加消息前缀和发送者信息
        sender_name = event.get_sender_name()
        prefix_text = f"{self.config['message_prefix']}{sender_name}: "
        message_chain.chain.append(Plain(prefix_text))
        
        # 处理消息内容
        for component in event.get_messages():
            if isinstance(component, Plain):
                # 处理文本消息，可能需要翻译
                text = component.text
                if self.translation_service and self.translation_service.should_translate(text):
                    try:
                        translated_text = await self.translation_service.translate(text)
                        if translated_text and translated_text != text:
                            # 添加原文和翻译（紧凑格式）
                            combined_text = f"{text}\n🌐 翻译: {translated_text}"
                            message_chain.chain.append(Plain(combined_text))
                            logger.info(f"✅ 文本翻译成功: {text[:50]}... -> {translated_text[:50]}...")
                        else:
                            message_chain.chain.append(Plain(text))
                    except Exception as e:
                        logger.error(f"❌ 文本翻译失败: {e}")
                        message_chain.chain.append(Plain(text))
                else:
                    message_chain.chain.append(Plain(text))
            elif isinstance(component, Image):
                # 保留图片
                message_chain.chain.append(component)
            elif isinstance(component, Video):
                # 保留视频
                message_chain.chain.append(component)
            elif isinstance(component, File):
                # 保留文件
                message_chain.chain.append(component)
            elif isinstance(component, At):
                # 转换@提及为文本
                message_chain.chain.append(Plain(f"@{component.qq}"))
            elif isinstance(component, AtAll):
                # 转换@全体为文本
                message_chain.chain.append(Plain("@全体成员"))
        
        return message_chain

    async def _get_target_kook_channel(self, event: AstrMessageEvent) -> str:
        """获取目标Kook频道ID - 支持多频道映射"""
        discord_channel_id = event.message_obj.group_id or event.session_id
        logger.info(f"🔍 查找目标Kook频道，Discord频道ID: {discord_channel_id}")
        
        # 优先级1: 检查多频道映射配置
        forward_channels = self.config.get("forward_channels", {})
        if discord_channel_id in forward_channels:
            target = forward_channels[discord_channel_id]
            logger.info(f"✅ 找到多频道映射: {discord_channel_id} -> {target}")
            return target
        
        # 优先级2: 检查是否是默认Discord频道
        default_discord_channel = self.config.get("default_discord_channel")
        default_kook_channel = self.config.get("default_kook_channel")
        
        if default_discord_channel and discord_channel_id == default_discord_channel and default_kook_channel:
            logger.info(f"✅ 匹配默认Discord频道映射: {discord_channel_id} -> {default_kook_channel}")
            return default_kook_channel
        
        # 优先级3: 向下兼容 - 如果没有配置默认Discord频道，使用默认Kook频道
        if not default_discord_channel and default_kook_channel:
            logger.info(f"📌 使用默认Kook频道（向下兼容）: {default_kook_channel}")
            return default_kook_channel
        
        # 调试信息
        logger.warning(f"❌ 未找到目标Kook频道: {discord_channel_id}")
        logger.info(f"   - 多频道映射数量: {len(forward_channels)}")
        logger.info(f"   - 映射列表: {list(forward_channels.keys())}")
        logger.info(f"   - 默认Discord频道: {default_discord_channel}")
        logger.info(f"   - 默认Kook频道: {default_kook_channel}")
        
        return None

    async def _send_to_kook(self, channel_id: str, message_chain: MessageChain):
        """发送消息到Kook频道"""
        try:
            if not self.kook_platform:
                logger.error("❌ Kook平台实例未找到，无法发送消息")
                return
            
            # 直接使用Kook适配器的客户端发送消息
            kook_client = getattr(self.kook_platform, 'client', None)
            if not kook_client:
                logger.error("❌ Kook客户端未找到，无法发送消息")
                return
                
            logger.info(f"📤 准备直接通过Kook客户端发送消息到频道: {channel_id}")
            
            # 遍历消息链中的每个组件
            for component in message_chain.chain:
                if isinstance(component, Plain):
                    await kook_client.send_text(channel_id, component.text)
                    logger.info(f"✅ 发送文本消息成功: {component.text[:50]}...")
                elif isinstance(component, Image):
                    # 处理图片消息
                    image_url = component.file
                    filename = getattr(component, 'filename', '未知文件名')
                    
                    # 从URL中提取实际文件名
                    from urllib.parse import urlparse
                    from pathlib import Path
                    parsed_url = urlparse(image_url)
                    url_filename = Path(parsed_url.path).name
                    
                    # 优先使用URL中的文件名
                    if url_filename and '.' in url_filename:
                        display_filename = url_filename
                    elif filename and filename != '未知文件名':
                        display_filename = filename
                    else:
                        display_filename = 'image.png'
                    
                    logger.info(f"🖼️ 检测到图片组件: URL={image_url}, 文件名={display_filename}")
                    
                    if image_url:
                        try:
                            # 下载Discord图片到本地
                            local_image_path = await self._download_image(image_url, filename)
                            if local_image_path:
                                # 上传图片到Kook并发送
                                logger.info(f"📤 准备上传并发送图片到Kook: {local_image_path}")
                                success = await self._upload_and_send_image_to_kook(channel_id, local_image_path, display_filename)
                                if success:
                                    logger.info(f"✅ 发送图片消息成功: {display_filename}")
                                else:
                                    logger.error(f"❌ 发送图片到Kook失败: {display_filename}")
                                    await kook_client.send_text(channel_id, f"[图片发送失败: {display_filename}]")
                            else:
                                logger.error("❌ 图片下载失败")
                                await kook_client.send_text(channel_id, f"[图片下载失败: {display_filename}]")
                        except Exception as img_error:
                            logger.error(f"❌ 发送图片失败: {img_error}")
                            import traceback
                            logger.error(traceback.format_exc())
                            # 如果图片发送失败，发送一个文本提示
                            await kook_client.send_text(channel_id, f"[图片转发失败: {display_filename}]")
                    else:
                        logger.warning("⚠️ 图片组件没有有效的文件URL")
                        await kook_client.send_text(channel_id, "[图片信息缺失]")
                elif isinstance(component, Video):
                    # 处理视频消息
                    video_url = component.file
                    filename = getattr(component, 'filename', '未知文件名')
                    
                    # 从URL中提取实际文件名
                    from urllib.parse import urlparse
                    from pathlib import Path
                    parsed_url = urlparse(video_url)
                    url_filename = Path(parsed_url.path).name
                    
                    # 优先使用URL中的文件名
                    if url_filename and '.' in url_filename:
                        display_filename = url_filename
                    elif filename and filename != '未知文件名':
                        display_filename = filename
                    else:
                        display_filename = 'video.mp4'
                    
                    logger.info(f"🎬 检测到视频组件: URL={video_url}, 文件名={display_filename}")
                    
                    if video_url:
                        try:
                            # 下载Discord视频到本地
                            local_video_path = await self._download_video(video_url, filename)
                            if local_video_path:
                                # 使用本地视频路径发送到Kook
                                logger.info(f"📤 准备发送本地视频到Kook: {local_video_path}")
                                success = await kook_client.send_image(channel_id, local_video_path)
                                if success:
                                    logger.info(f"✅ 发送视频消息成功: {display_filename}")
                                else:
                                    logger.error(f"❌ 发送视频到Kook失败: {display_filename}")
                                    await kook_client.send_text(channel_id, f"[视频发送失败: {display_filename}]")
                            else:
                                logger.error("❌ 视频下载失败")
                                await kook_client.send_text(channel_id, f"[视频下载失败: {display_filename}]")
                        except Exception as video_error:
                            logger.error(f"❌ 发送视频失败: {video_error}")
                            import traceback
                            logger.error(traceback.format_exc())
                            # 如果视频发送失败，发送一个文本提示
                            await kook_client.send_text(channel_id, f"[视频转发失败: {display_filename}]")
                    else:
                        logger.warning("⚠️ 视频组件没有有效的文件URL")
                        await kook_client.send_text(channel_id, "[视频信息缺失]")
                elif isinstance(component, File):
                    # 处理文件消息（可能是图片或视频）
                    file_url = component.url if component.url else component.file
                    filename = getattr(component, 'name', '未知文件名')
                    
                    logger.info(f"📁 检测到文件组件: URL={file_url}, 文件名={filename}")
                    
                    if file_url:
                        # 根据文件扩展名判断文件类型
                        from pathlib import Path
                        file_ext = Path(filename).suffix.lower() if filename else ''
                        
                        # 图片文件扩展名
                        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'}
                        # 视频文件扩展名
                        video_extensions = {'.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv', '.m4v'}
                        
                        if file_ext in image_extensions:
                            # 作为图片处理
                            logger.info(f"🖼️ 文件识别为图片: {filename}")
                            try:
                                # 下载Discord图片到本地
                                local_image_path = await self._download_image(file_url, filename)
                                if local_image_path:
                                    # 上传图片到Kook并发送
                                    logger.info(f"📤 准备上传并发送图片到Kook: {local_image_path}")
                                    success = await self._upload_and_send_image_to_kook(channel_id, local_image_path, filename)
                                    if success:
                                        logger.info(f"✅ 发送图片文件成功: {filename}")
                                    else:
                                        logger.error(f"❌ 发送图片文件到Kook失败: {filename}")
                                        await kook_client.send_text(channel_id, f"[图片文件发送失败: {filename}]")
                                else:
                                    logger.error("❌ 图片文件下载失败")
                                    await kook_client.send_text(channel_id, f"[图片文件下载失败: {filename}]")
                            except Exception as file_error:
                                logger.error(f"❌ 发送图片文件失败: {file_error}")
                                import traceback
                                logger.error(traceback.format_exc())
                                await kook_client.send_text(channel_id, f"[图片文件转发失败: {filename}]")
                        
                        elif file_ext in video_extensions:
                            # 作为视频处理
                            logger.info(f"🎬 文件识别为视频: {filename}")
                            try:
                                # 下载Discord视频到本地
                                local_video_path = await self._download_video(file_url, filename)
                                if local_video_path:
                                    # 使用直接的HTTP API调用发送视频到Kook
                                    logger.info(f"📤 准备发送本地视频到Kook: {local_video_path}")
                                    success = await self._send_video_to_kook_direct(channel_id, local_video_path, filename)
                                    
                                    if success:
                                        logger.info(f"✅ 发送视频文件成功: {filename}")
                                    else:
                                        logger.error(f"❌ 发送视频文件到Kook失败: {filename}")
                                        await kook_client.send_text(channel_id, f"[视频文件发送失败: {filename}]")
                                else:
                                    logger.error("❌ 视频文件下载失败")
                                    await kook_client.send_text(channel_id, f"[视频文件下载失败: {filename}]")
                            except Exception as file_error:
                                logger.error(f"❌ 发送视频文件失败: {file_error}")
                                import traceback
                                logger.error(traceback.format_exc())
                                await kook_client.send_text(channel_id, f"[视频文件转发失败: {filename}]")
                        
                        else:
                            # 不支持的文件类型
                            logger.warning(f"⚠️ 不支持的文件类型: {filename} (扩展名: {file_ext})")
                            await kook_client.send_text(channel_id, f"[不支持的文件类型: {filename}]")
                    else:
                        logger.warning("⚠️ 文件组件没有有效的文件URL")
                        await kook_client.send_text(channel_id, "[文件信息缺失]")
                else:
                    logger.warning(f"⚠️ 不支持的消息组件类型: {type(component)}")
                    
        except Exception as e:
            logger.error(f"❌ 发送消息到Kook时发生错误: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _download_video(self, video_url: str, filename: str) -> str:
        """下载Discord视频到本地public/video文件夹"""
        import aiohttp
        import os
        import uuid
        from pathlib import Path
        from urllib.parse import urlparse
        
        try:
            # 创建public/video目录
            plugin_dir = Path(__file__).parent
            video_dir = plugin_dir / "public" / "video"
            video_dir.mkdir(parents=True, exist_ok=True)
            
            # 从URL中提取文件名
            parsed_url = urlparse(video_url)
            url_filename = Path(parsed_url.path).name  # 获取路径中的文件名
            
            # 如果URL中有文件名，使用它；否则使用传入的filename
            if url_filename and '.' in url_filename:
                actual_filename = url_filename
            elif filename and filename != '未知文件名':
                actual_filename = filename
            else:
                actual_filename = 'video.mp4'
            
            logger.info(f"📝 提取的视频文件名: {actual_filename}")
            
            # 生成唯一的文件名，保留原始扩展名
            file_ext = Path(actual_filename).suffix if actual_filename else '.mp4'
            unique_filename = f"{uuid.uuid4().hex}{file_ext}"
            local_path = video_dir / unique_filename
            
            logger.info(f"📥 开始下载视频: {video_url} -> {local_path}")
            
            # 下载视频
            async with aiohttp.ClientSession() as session:
                async with session.get(video_url) as response:
                    if response.status == 200:
                        with open(local_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                        
                        logger.info(f"✅ 视频下载成功: {local_path}")
                        
                        # 下载完成后进行清理
                        await self._cleanup_old_videos()
                        
                        return str(local_path)
                    else:
                        logger.error(f"❌ 下载视频HTTP错误: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ 下载视频异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def _cleanup_old_videos(self):
        """根据配置清理旧视频文件"""
        import os
        import time
        from pathlib import Path
        
        try:
            # 获取清理时间配置（小时）
            cleanup_hours = self.config.get('video_cleanup_hours', 24)
            
            # 如果设置为0，则不清理
            if cleanup_hours <= 0:
                return
                
            plugin_dir = Path(__file__).parent
            video_dir = plugin_dir / "public" / "video"
            
            if not video_dir.exists():
                return
                
            current_time = time.time()
            cleanup_count = 0
            cleanup_seconds = cleanup_hours * 3600  # 转换为秒
            
            # 清理超过配置时间的视频文件
            for video_file in video_dir.glob("*"):
                if video_file.is_file() and video_file.name != ".gitkeep":
                    file_age = current_time - video_file.stat().st_mtime
                    if file_age > cleanup_seconds:
                        try:
                            video_file.unlink()
                            cleanup_count += 1
                        except Exception as e:
                            logger.warning(f"⚠️ 删除旧视频文件失败: {video_file} - {e}")
            
            if cleanup_count > 0:
                logger.info(f"🧹 清理了 {cleanup_count} 个超过 {cleanup_hours} 小时的旧视频文件")
                
        except Exception as e:
            logger.error(f"❌ 清理旧视频文件异常: {e}")
    
    async def _send_video_to_kook_direct(self, channel_id: str, video_path: str, filename: str) -> bool:
        """直接使用HTTP API发送视频到Kook"""
        try:
            # 获取Kook客户端和token
            if not self.kook_platform:
                logger.error("❌ Kook平台实例未找到，无法发送视频")
                return False
            
            kook_client = getattr(self.kook_platform, 'client', None)
            if not kook_client:
                logger.error("❌ 无法获取Kook客户端")
                return False
            
            token = getattr(kook_client, 'token', None)
            if not token:
                logger.error("❌ 无法获取Kook认证token")
                return False
            
            # 第一步：上传视频文件到Kook
            logger.info(f"📤 开始上传视频文件: {video_path}")
            video_url = await self._upload_video_to_kook(video_path, token)
            if not video_url:
                logger.error(f"❌ 视频上传失败: {filename}")
                return False
            
            # 第二步：发送视频消息到频道
            logger.info(f"📡 开始发送视频消息到频道: {channel_id}")
            success = await self._send_video_message_to_kook(channel_id, video_url, filename, token)
            
            return success
            
        except Exception as e:
            logger.error(f"❌ 发送视频到Kook异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def _upload_video_to_kook(self, video_path: str, token: str) -> str:
        """上传视频到Kook并返回URL"""
        try:
            # 检查文件是否存在
            if not os.path.exists(video_path):
                logger.error(f"❌ 视频文件不存在: {video_path}")
                return None
            
            # 获取文件大小
            file_size = os.path.getsize(video_path)
            logger.info(f"📁 视频文件大小: {file_size} 字节 ({file_size / (1024 * 1024):.2f} MB)")
            
            # 构建上传URL和请求头
            upload_url = "https://www.kookapp.cn/api/v3/asset/create"
            headers = {'Authorization': f'Bot {token}'}
            
            logger.info(f"📡 发送上传请求到: {upload_url}")
            
            # 使用aiohttp上传文件
            async with aiohttp.ClientSession() as session:
                with open(video_path, 'rb') as f:
                    data = aiohttp.FormData()
                    data.add_field('file', f, filename=Path(video_path).name)
                    
                    async with session.post(upload_url, data=data, headers=headers) as response:
                        logger.info(f"📥 收到上传响应，状态码: {response.status}")
                        
                        if response.status == 200:
                            result = await response.json()
                            logger.info(f"📄 Kook视频上传响应: {result}")
                            
                            # 解析Kook返回的数据结构
                            if result.get('code') == 0 and 'data' in result:
                                data = result['data']
                                
                                # 提取URL - Kook可能返回不同的字段名
                                asset_url = None
                                if 'url' in data:
                                    asset_url = data['url']
                                elif 'file_url' in data:
                                    asset_url = data['file_url']
                                elif 'link' in data:
                                    asset_url = data['link']
                                elif 'asset_url' in data:
                                    asset_url = data['asset_url']
                                
                                if asset_url:
                                    logger.info(f"✅ 视频上传成功，获得URL: {asset_url}")
                                    
                                    # 记录完整的返回数据用于调试
                                    logger.debug(f"🔍 完整的Kook返回数据: {data}")
                                    
                                    # 等待服务器处理视频文件
                                    logger.info(f"⏳ 等待服务器处理视频文件...")
                                    import asyncio
                                    await asyncio.sleep(5.0)  # 等待5秒让服务器处理视频
                                    logger.info(f"✅ 服务器处理完成，准备发送消息")
                                    
                                    return asset_url
                                else:
                                    logger.error(f"❌ 无法从Kook响应中提取URL，数据结构: {data}")
                                    return None
                            else:
                                error_msg = result.get('message', '未知错误')
                                error_code = result.get('code', 'N/A')
                                logger.error(f"❌ 视频上传失败 (代码: {error_code}): {error_msg}")
                                return None
                        else:
                            response_text = await response.text()
                            logger.error(f"❌ 视频上传HTTP错误: {response.status}")
                            logger.error(f"📄 错误详情: {response_text}")
                            return None
                            
        except Exception as e:
            logger.error(f"❌ 上传视频异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def _send_video_message_to_kook(self, channel_id: str, video_url: str, filename: str, token: str) -> bool:
        """发送视频消息到Kook频道"""
        try:
            # 构建消息发送URL和请求头
            url = "https://www.kookapp.cn/api/v3/message/create"
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json"
            }
            payload = {
                "target_id": channel_id,
                "content": video_url,
                "type": 3  # 使用type=3发送视频消息
            }
            
            logger.info(f"📡 发送视频消息到频道 {channel_id}")
            logger.info(f"📄 消息内容: {payload}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    logger.info(f"📥 收到发送响应，状态码: {resp.status}")
                    
                    if resp.status == 200:
                        result = await resp.json()
                        logger.info(f"📄 发送响应内容: {result}")
                        
                        if result.get('code') == 0:
                            logger.info(f"✅ 发送视频消息成功: {filename}")
                            return True
                        else:
                            error_msg = result.get('message', '未知错误')
                            logger.error(f"❌ 发送视频消息失败: {error_msg}")
                            return False
                    else:
                        response_text = await resp.text()
                        logger.error(f"❌ 发送视频消息HTTP错误: {resp.status}")
                        logger.error(f"📄 错误详情: {response_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ 发送视频消息异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def _upload_and_send_image_to_kook(self, channel_id: str, image_path: str, filename: str) -> bool:
        """上传图片到Kook并发送消息"""
        try:
            # 获取Kook客户端和token
            if not self.kook_platform:
                logger.error("❌ Kook平台实例未找到，无法发送图片")
                return False
            
            kook_client = getattr(self.kook_platform, 'client', None)
            if not kook_client:
                logger.error("❌ 无法获取Kook客户端")
                return False
            
            token = getattr(kook_client, 'token', None)
            if not token:
                logger.error("❌ 无法获取Kook认证token")
                return False
            
            # 第一步：上传图片文件到Kook
            logger.info(f"📤 开始上传图片文件: {image_path}")
            image_url = await self._upload_image_to_kook_api(image_path, token)
            if not image_url:
                logger.error(f"❌ 图片上传失败: {filename}")
                return False
            
            # 第二步：发送图片消息到频道
            logger.info(f"📡 开始发送图片消息到频道: {channel_id}")
            success = await self._send_image_message_to_kook(channel_id, image_url, filename, token)
            
            return success
            
        except Exception as e:
            logger.error(f"❌ 发送图片到Kook异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def _upload_image_to_kook_api(self, image_path: str, token: str) -> str:
        """上传图片到Kook并返回URL"""
        try:
            # 检查文件是否存在
            if not os.path.exists(image_path):
                logger.error(f"❌ 图片文件不存在: {image_path}")
                return None
            
            # 获取文件大小
            file_size = os.path.getsize(image_path)
            logger.info(f"📁 图片文件大小: {file_size} 字节 ({file_size / (1024 * 1024):.2f} MB)")
            
            # 构建上传URL和请求头
            upload_url = "https://www.kookapp.cn/api/v3/asset/create"
            headers = {'Authorization': f'Bot {token}'}
            
            logger.info(f"📡 发送图片上传请求到: {upload_url}")
            
            # 使用aiohttp上传文件
            async with aiohttp.ClientSession() as session:
                with open(image_path, 'rb') as f:
                    data = aiohttp.FormData()
                    data.add_field('file', f, filename=Path(image_path).name)
                    
                    async with session.post(upload_url, data=data, headers=headers) as response:
                        logger.info(f"📥 收到图片上传响应，状态码: {response.status}")
                        
                        if response.status == 200:
                            result = await response.json()
                            logger.info(f"📄 Kook图片上传响应: {result}")
                            
                            # 解析Kook返回的数据结构
                            if result.get('code') == 0 and 'data' in result:
                                data = result['data']
                                
                                # 提取URL - Kook可能返回不同的字段名
                                asset_url = None
                                if 'url' in data:
                                    asset_url = data['url']
                                elif 'file_url' in data:
                                    asset_url = data['file_url']
                                elif 'link' in data:
                                    asset_url = data['link']
                                elif 'asset_url' in data:
                                    asset_url = data['asset_url']
                                
                                if asset_url:
                                    logger.info(f"✅ 图片上传成功，获得URL: {asset_url}")
                                    
                                    # 记录完整的返回数据用于调试
                                    logger.debug(f"🔍 完整的Kook图片返回数据: {data}")
                                    
                                    return asset_url
                                else:
                                    logger.error(f"❌ 无法从Kook响应中提取图片URL，数据结构: {data}")
                                    return None
                            else:
                                error_msg = result.get('message', '未知错误')
                                error_code = result.get('code', 'N/A')
                                logger.error(f"❌ 图片上传失败 (代码: {error_code}): {error_msg}")
                                return None
                        else:
                            response_text = await response.text()
                            logger.error(f"❌ 图片上传HTTP错误: {response.status}")
                            logger.error(f"📄 错误详情: {response_text}")
                            return None
                            
        except Exception as e:
            logger.error(f"❌ 上传图片异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def _send_image_message_to_kook(self, channel_id: str, image_url: str, filename: str, token: str) -> bool:
        """发送图片消息到Kook频道"""
        try:
            # 构建消息发送URL和请求头
            url = "https://www.kookapp.cn/api/v3/message/create"
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json"
            }
            payload = {
                "target_id": channel_id,
                "content": image_url,
                "type": 2  # 使用type=2发送图片消息
            }
            
            logger.info(f"📡 发送图片消息到频道 {channel_id}")
            logger.info(f"📄 消息内容: {payload}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    logger.info(f"📥 收到图片发送响应，状态码: {resp.status}")
                    
                    if resp.status == 200:
                        result = await resp.json()
                        logger.info(f"📄 图片发送响应内容: {result}")
                        
                        if result.get('code') == 0:
                            logger.info(f"✅ 发送图片消息成功: {filename}")
                            return True
                        else:
                            error_msg = result.get('message', '未知错误')
                            logger.error(f"❌ 发送图片消息失败: {error_msg}")
                            return False
                    else:
                        response_text = await resp.text()
                        logger.error(f"❌ 发送图片消息HTTP错误: {resp.status}")
                        logger.error(f"📄 错误详情: {response_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ 发送图片消息异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def _download_image(self, image_url: str, filename: str) -> str:
        """下载Discord图片到本地public/image文件夹"""
        import aiohttp
        import os
        import uuid
        from pathlib import Path
        from urllib.parse import urlparse
        
        try:
            # 创建public/image目录
            plugin_dir = Path(__file__).parent
            image_dir = plugin_dir / "public" / "image"
            image_dir.mkdir(parents=True, exist_ok=True)
            
            # 从URL中提取文件名
            parsed_url = urlparse(image_url)
            url_filename = Path(parsed_url.path).name  # 获取路径中的文件名
            
            # 如果URL中有文件名，使用它；否则使用传入的filename
            if url_filename and '.' in url_filename:
                actual_filename = url_filename
            elif filename and filename != '未知文件名':
                actual_filename = filename
            else:
                actual_filename = 'image.png'
            
            logger.info(f"📝 提取的文件名: {actual_filename}")
            
            # 生成唯一的文件名，保留原始扩展名
            file_ext = Path(actual_filename).suffix if actual_filename else '.png'
            unique_filename = f"{uuid.uuid4().hex}{file_ext}"
            local_path = image_dir / unique_filename
            
            logger.info(f"📥 开始下载图片: {image_url} -> {local_path}")
            
            # 下载图片
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        with open(local_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                        
                        logger.info(f"✅ 图片下载成功: {local_path}")
                        
                        # 下载完成后进行清理
                        await self._cleanup_old_images()
                        
                        return str(local_path)
                    else:
                        logger.error(f"❌ 下载图片HTTP错误: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ 下载图片异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def _cleanup_old_images(self):
        """根据配置清理旧图片文件"""
        import os
        import time
        from pathlib import Path
        
        try:
            # 获取清理时间配置（小时）
            cleanup_hours = self.config.get('image_cleanup_hours', 24)
            
            # 如果设置为0，则不清理
            if cleanup_hours <= 0:
                return
                
            plugin_dir = Path(__file__).parent
            image_dir = plugin_dir / "public" / "image"
            
            if not image_dir.exists():
                return
                
            current_time = time.time()
            cleanup_count = 0
            cleanup_seconds = cleanup_hours * 3600  # 转换为秒
            
            # 清理超过配置时间的图片文件
            for image_file in image_dir.glob("*"):
                if image_file.is_file() and image_file.name != ".gitkeep":
                    file_age = current_time - image_file.stat().st_mtime
                    if file_age > cleanup_seconds:
                        try:
                            image_file.unlink()
                            cleanup_count += 1
                        except Exception as e:
                            logger.warning(f"⚠️ 删除旧图片文件失败: {image_file} - {e}")
            
            if cleanup_count > 0:
                logger.info(f"🧹 清理了 {cleanup_count} 个超过 {cleanup_hours} 小时的旧图片文件")
                
        except Exception as e:
            logger.error(f"❌ 清理旧图片文件异常: {e}")

    @filter.command("translation_config")
    async def translation_config_command(self, event: AstrMessageEvent):
        """配置翻译功能"""
        if not self.translation_command_handler:
            yield event.plain_result("❌ 翻译命令处理器未初始化")
            return
        
        args = event.message_str.split()[1:] if len(event.message_str.split()) > 1 else []
        
        async for result in self.translation_command_handler.handle_translation_command(event, args):
            yield result
    
    @filter.command("discord_kook_config")
    async def config_command(self, event: AstrMessageEvent):
        """配置Discord到Kook转发"""
        if event.role != "admin":
            yield event.plain_result("只有管理员可以配置转发设置")
            return
        
        args = event.message_str.split()[1:] if len(event.message_str.split()) > 1 else []
        
        if not args:
            # 显示当前配置
            platform_status = "✅ 已连接" if self.kook_platform else "❌ 未连接"
            config_text = f"""Discord到Kook转发配置:
启用状态: {self.config['enabled']}
Discord平台ID: {self.config['discord_platform_id']}
Kook平台ID: {self.config['kook_platform_id']}
Kook平台状态: {platform_status}
转发所有频道: {self.config['forward_all_channels']}
默认Kook频道: {self.config['default_kook_channel']}
包含机器人消息: {self.config['include_bot_messages']}
消息前缀: {self.config['message_prefix']}
频道映射: {json.dumps(self.config['forward_channels'], indent=2, ensure_ascii=False)}

使用方法:
/discord_kook_config enable/disable - 启用/禁用转发
/discord_kook_config set_kook_platform <platform_id> - 手动设置Kook平台ID
/discord_kook_config refresh_platforms - 重新检测平台适配器
/discord_kook_config set_default_channel <kook_channel_id> - 设置默认Kook频道
/discord_kook_config add_mapping <discord_channel_id> <kook_channel_id> - 添加频道映射
                /discord_kook_config remove_mapping <discord_channel_id> - 移除频道映射
                /discord_kook_config toggle_all_channels - 切换是否转发所有频道
                /discord_kook_config quick_test <kook_channel_id> - 快速测试（启用转发所有频道到指定Kook频道）
                /discord_kook_config cleanup_images - 立即清理旧图片文件
                /discord_kook_config cleanup_videos - 立即清理旧视频文件
                /discord_kook_config set_cleanup_hours <hours> - 设置图片清理时间（小时，0表示不自动清理）
                /discord_kook_config set_video_cleanup_hours <hours> - 设置视频清理时间（小时，0表示不自动清理）"""
            yield event.plain_result(config_text)
            return
        
        command = args[0].lower()
        
        if command == "enable":
            self.config["enabled"] = True
            self._save_config()
            yield event.plain_result("Discord到Kook转发已启用")
        elif command == "disable":
            self.config["enabled"] = False
            self._save_config()
            yield event.plain_result("Discord到Kook转发已禁用")
        elif command == "set_kook_platform" and len(args) > 1:
            platform_id = args[1]
            # 尝试根据ID找到平台
            found_platform = self.context.get_platform_inst(platform_id)
            if found_platform:
                self.kook_platform = found_platform
                self.config["kook_platform_id"] = platform_id
                self._save_config()
                yield event.plain_result(f"✅ 已手动设置Kook平台: {platform_id}")
            else:
                yield event.plain_result(f"❌ 未找到ID为 {platform_id} 的平台适配器")
        elif command == "refresh_platforms":
            await self._get_platform_instances()
            if self.kook_platform:
                yield event.plain_result("✅ 平台检测完成，已找到Kook平台")
            else:
                yield event.plain_result("❌ 平台检测完成，但仍未找到Kook平台。请检查日志获取详细信息")
        elif command == "set_default_channel" and len(args) > 1:
            self.config["default_kook_channel"] = args[1]
            self._save_config()
            yield event.plain_result(f"默认Kook频道已设置为: {args[1]}")
        elif command == "add_mapping" and len(args) > 2:
            self.config["forward_channels"][args[1]] = args[2]
            self._save_config()
            yield event.plain_result(f"已添加频道映射: {args[1]} -> {args[2]}")
        elif command == "remove_mapping" and len(args) > 1:
            if args[1] in self.config["forward_channels"]:
                del self.config["forward_channels"][args[1]]
                self._save_config()
                yield event.plain_result(f"已移除频道映射: {args[1]}")
            else:
                yield event.plain_result(f"未找到频道映射: {args[1]}")
        elif command == "toggle_all_channels":
            self.config["forward_all_channels"] = not self.config["forward_all_channels"]
            self._save_config()
            status = "启用" if self.config["forward_all_channels"] else "禁用"
            yield event.plain_result(f"转发所有频道已{status}")
        elif command == "quick_test" and len(args) > 1:
            # 快速测试配置
            kook_channel_id = args[1]
            self.config["enabled"] = True
            self.config["forward_all_channels"] = True
            self.config["default_kook_channel"] = kook_channel_id
            self.config["include_bot_messages"] = False
            self._save_config()
            yield event.plain_result(f"🚀 快速测试配置已启用！\n- 转发功能：已启用\n- 转发所有频道：已启用\n- 默认Kook频道：{kook_channel_id}\n- 包含机器人消息：已禁用\n\n现在可以在Discord发送消息进行测试！")
        elif command == "cleanup_images":
            # 立即清理旧图片文件
            await self._cleanup_old_images()
            yield event.plain_result("🧹 图片清理完成")
        elif command == "cleanup_videos":
            # 立即清理旧视频文件
            await self._cleanup_old_videos()
            yield event.plain_result("🧹 视频清理完成")
        elif command == "set_cleanup_hours" and len(args) > 1:
            try:
                hours = int(args[1])
                if hours < 0:
                    yield event.plain_result("❌ 清理时间不能为负数")
                else:
                    self.config["image_cleanup_hours"] = hours
                    self._save_config()
                    if hours == 0:
                        yield event.plain_result("✅ 已禁用自动图片清理")
                    else:
                        yield event.plain_result(f"✅ 图片清理时间已设置为 {hours} 小时")
            except ValueError:
                yield event.plain_result("❌ 请输入有效的小时数")
        elif command == "set_video_cleanup_hours" and len(args) > 1:
            try:
                hours = int(args[1])
                if hours < 0:
                    yield event.plain_result("❌ 清理时间不能为负数")
                else:
                    self.config["video_cleanup_hours"] = hours
                    self._save_config()
                    if hours == 0:
                        yield event.plain_result("✅ 已禁用自动视频清理")
                    else:
                        yield event.plain_result(f"✅ 视频清理时间已设置为 {hours} 小时")
            except ValueError:
                yield event.plain_result("❌ 请输入有效的小时数")
        else:
            yield event.plain_result("无效的配置命令，请使用 /discord_kook_config 查看帮助")

    async def terminate(self):
        """插件销毁时的清理工作"""
        logger.info("Discord到Kook转发插件已停止")
