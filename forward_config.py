import os
from dotenv import load_dotenv
from typing import Dict, List, Tuple

class ForwardConfig:
    """转发配置管理类"""
    
    def __init__(self):
        load_dotenv()
        self.forward_rules = self._parse_forward_rules()
        self.forward_bot_messages = os.getenv('FORWARD_BOT_MESSAGES', 'false').lower() == 'true'
        self.message_prefix = os.getenv('MESSAGE_PREFIX', '[Discord]')
    
    def _parse_forward_rules(self) -> Dict[str, str]:
        """解析转发规则
        
        Returns:
            Dict[str, str]: Discord频道ID -> KOOK频道ID的映射
        """
        rules_str = os.getenv('FORWARD_RULES', '')
        rules = {}
        
        if not rules_str.strip():
            return rules
        
        try:
            # 解析格式: discord_id1:kook_id1,discord_id2:kook_id2
            pairs = rules_str.split(',')
            for pair in pairs:
                if ':' in pair:
                    discord_id, kook_id = pair.strip().split(':', 1)
                    rules[discord_id.strip()] = kook_id.strip()
        except Exception as e:
            print(f"解析转发规则失败: {e}")
            print(f"规则格式应为: discord_id1:kook_id1,discord_id2:kook_id2")
        
        return rules
    
    def get_kook_channel_id(self, discord_channel_id: str) -> str:
        """根据Discord频道ID获取对应的KOOK频道ID
        
        Args:
            discord_channel_id: Discord频道ID
            
        Returns:
            str: 对应的KOOK频道ID，如果没有配置则返回None
        """
        return self.forward_rules.get(str(discord_channel_id))
    
    def should_forward_message(self, is_bot: bool) -> bool:
        """判断是否应该转发消息
        
        Args:
            is_bot: 消息是否来自机器人
            
        Returns:
            bool: 是否应该转发
        """
        if is_bot and not self.forward_bot_messages:
            return False
        return True
    
    def get_forward_channels(self) -> List[Tuple[str, str]]:
        """获取所有转发规则
        
        Returns:
            List[Tuple[str, str]]: (Discord频道ID, KOOK频道ID)的列表
        """
        return list(self.forward_rules.items())
    
    def reload_config(self):
        """重新加载配置"""
        load_dotenv(override=True)
        self.forward_rules = self._parse_forward_rules()
        self.forward_bot_messages = os.getenv('FORWARD_BOT_MESSAGES', 'false').lower() == 'true'
        self.message_prefix = os.getenv('MESSAGE_PREFIX', '[Discord]')
        print(f"配置已重新加载，转发规则数量: {len(self.forward_rules)}")