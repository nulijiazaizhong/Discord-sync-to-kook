import os
import abc
import aiohttp
from dotenv import load_dotenv
from typing import Dict, Optional, Type

# 翻译服务基类
class TranslationService(abc.ABC):
    def __init__(self, source_language: str, target_language: str):
        self.source_language = source_language
        self.target_language = target_language
        
    @abc.abstractmethod
    async def translate(self, text: str) -> str:
        """翻译文本的抽象方法，需要子类实现"""
        pass
        
    @classmethod
    @abc.abstractmethod
    def is_configured(cls) -> bool:
        """检查翻译服务是否配置正确的抽象方法，需要子类实现"""
        pass

# LibreTranslate服务实现
class LibreTranslateService(TranslationService):
    def __init__(self, source_language: str, target_language: str):
        super().__init__(source_language, target_language)
        self.api_url = os.getenv('LIBRE_TRANSLATION_API_URL', 'https://libretranslate.com/translate')
        self.api_key = os.getenv('LIBRE_TRANSLATION_API_KEY', '')
        
    @classmethod
    def is_configured(cls) -> bool:
        """检查LibreTranslate服务是否配置正确"""
        api_url = os.getenv('LIBRE_TRANSLATION_API_URL', '')
        return bool(api_url)
        
    async def translate(self, text: str) -> str:
        """使用LibreTranslate API翻译文本"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "q": text,
                    "source": self.source_language,
                    "target": self.target_language,
                    "format": "text"
                }
                
                # 如果有API密钥，添加到请求中
                if self.api_key:
                    payload["api_key"] = self.api_key
                
                async with session.post(self.api_url, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        translated_text = result.get("translatedText", text)
                        return translated_text
                    else:
                        print(f"❌ LibreTranslate翻译失败，状态码: {response.status}")
                        return text
        except Exception as e:
            print(f"❌ LibreTranslate翻译过程中出错: {e}")
            return text

# 腾讯云翻译服务实现
class TencentTranslateService(TranslationService):
    def __init__(self, source_language: str, target_language: str):
        super().__init__(source_language, target_language)
        self.secret_id = os.getenv('TENCENT_SECRET_ID', '')
        self.secret_key = os.getenv('TENCENT_SECRET_KEY', '')
        
    @classmethod
    def is_configured(cls) -> bool:
        """检查腾讯云翻译服务是否配置正确"""
        secret_id = os.getenv('TENCENT_SECRET_ID', '')
        secret_key = os.getenv('TENCENT_SECRET_KEY', '')
        return bool(secret_id and secret_key)
        
    async def translate(self, text: str) -> str:
        """使用腾讯云翻译API翻译文本"""
        try:
            # 检查是否配置了腾讯云API密钥
            if not self.secret_id or not self.secret_key:
                print("❌ 腾讯云翻译API密钥未配置")
                return text
                
            # 导入腾讯云SDK
            try:
                from tencentcloud.common import credential
                from tencentcloud.common.profile.client_profile import ClientProfile
                from tencentcloud.common.profile.http_profile import HttpProfile
                from tencentcloud.tmt.v20180321 import tmt_client, models
            except ImportError:
                print("❌ 腾讯云SDK未安装，请运行: pip install tencentcloud-sdk-python")
                return text
                
            # 设置腾讯云API认证信息
            cred = credential.Credential(self.secret_id, self.secret_key)
            httpProfile = HttpProfile()
            httpProfile.endpoint = "tmt.tencentcloudapi.com"
            clientProfile = ClientProfile()
            clientProfile.httpProfile = httpProfile
            client = tmt_client.TmtClient(cred, "ap-guangzhou", clientProfile)
            
            # 设置请求参数
            source_lang = "auto" if self.source_language == "auto" else self.source_language
            target_lang = self.target_language
            
            # 处理语言代码格式差异
            if target_lang == "zh-CN":
                target_lang = "zh"
                
            # 创建请求对象
            req = models.TextTranslateRequest()
            req.SourceText = text
            req.Source = source_lang
            req.Target = target_lang
            req.ProjectId = 0
            
            # 发送请求
            resp = client.TextTranslate(req)
            return resp.TargetText
        except Exception as e:
            print(f"❌ 腾讯云翻译过程中出错: {e}")
            return text

# Google翻译服务实现
class GoogleTranslateService(TranslationService):
    def __init__(self, source_language: str, target_language: str):
        super().__init__(source_language, target_language)
        self.api_key = os.getenv('GOOGLE_TRANSLATION_API_KEY', '')
        
    @classmethod
    def is_configured(cls) -> bool:
        """检查Google翻译服务是否配置正确"""
        api_key = os.getenv('GOOGLE_TRANSLATION_API_KEY', '')
        return bool(api_key)
        
    async def translate(self, text: str) -> str:
        """使用Google翻译API翻译文本"""
        try:
            # 检查是否配置了API密钥
            if not self.api_key:
                print("❌ Google翻译API密钥未配置")
                return text
                
            # 使用Google Cloud Translation API
            async with aiohttp.ClientSession() as session:
                url = f"https://translation.googleapis.com/language/translate/v2?key={self.api_key}"
                payload = {
                    "q": text,
                    "target": self.target_language,
                    "format": "text"
                }
                
                # 如果源语言不是auto，则添加到请求中
                if self.source_language != "auto":
                    payload["source"] = self.source_language
                
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        translations = result.get("data", {}).get("translations", [])
                        if translations:
                            return translations[0].get("translatedText", text)
                        return text
                    else:
                        print(f"❌ Google翻译失败，状态码: {response.status}")
                        return text
        except Exception as e:
            print(f"❌ Google翻译过程中出错: {e}")
            return text

# 百度翻译服务实现
class BaiduTranslateService(TranslationService):
    def __init__(self, source_language: str, target_language: str):
        super().__init__(source_language, target_language)
        self.app_id = os.getenv('BAIDU_APP_ID', '')
        self.app_key = os.getenv('BAIDU_APP_KEY', '')
        
    @classmethod
    def is_configured(cls) -> bool:
        """检查百度翻译服务是否配置正确"""
        app_id = os.getenv('BAIDU_APP_ID', '')
        app_key = os.getenv('BAIDU_APP_KEY', '')
        return bool(app_id and app_key)
        
    async def translate(self, text: str) -> str:
        """使用百度翻译API翻译文本"""
        try:
            # 检查是否配置了API密钥
            if not self.app_id or not self.app_key:
                print("❌ 百度翻译API密钥未配置")
                return text
                
            import random
            import hashlib
            
            # 构建请求参数
            salt = str(random.randint(32768, 65536))
            sign = hashlib.md5((self.app_id + text + salt + self.app_key).encode()).hexdigest()
            
            # 处理语言代码格式差异
            source_lang = "auto" if self.source_language == "auto" else self.source_language
            target_lang = self.target_language
            
            # 百度翻译API使用的语言代码可能与其他服务不同，需要转换
            lang_map = {
                "zh-CN": "zh",
                "en": "en",
                "ja": "jp",
                "ko": "kor",
                "fr": "fra",
                "es": "spa",
                "ru": "ru"
            }
            
            source_lang = lang_map.get(source_lang, source_lang)
            target_lang = lang_map.get(target_lang, target_lang)
            
            # 发送请求
            async with aiohttp.ClientSession() as session:
                url = "https://api.fanyi.baidu.com/api/trans/vip/translate"
                params = {
                    "q": text,
                    "from": source_lang,
                    "to": target_lang,
                    "appid": self.app_id,
                    "salt": salt,
                    "sign": sign
                }
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        result = await response.json()
                        trans_result = result.get("trans_result", [])
                        if trans_result:
                            return trans_result[0].get("dst", text)
                        return text
                    else:
                        print(f"❌ 百度翻译失败，状态码: {response.status}")
                        return text
        except Exception as e:
            print(f"❌ 百度翻译过程中出错: {e}")
            return text

# 有道翻译服务实现
class YoudaoTranslateService(TranslationService):
    def __init__(self, source_language: str, target_language: str):
        super().__init__(source_language, target_language)
        self.app_key = os.getenv('YOUDAO_APP_KEY', '')
        self.app_secret = os.getenv('YOUDAO_APP_SECRET', '')
        
    @classmethod
    def is_configured(cls) -> bool:
        """检查有道翻译服务是否配置正确"""
        app_key = os.getenv('YOUDAO_APP_KEY', '')
        app_secret = os.getenv('YOUDAO_APP_SECRET', '')
        return bool(app_key and app_secret)
        
    async def translate(self, text: str) -> str:
        """使用有道翻译API翻译文本"""
        try:
            # 检查是否配置了API密钥
            if not self.app_key or not self.app_secret:
                print("❌ 有道翻译API密钥未配置")
                return text
                
            import time
            import uuid
            import hashlib
            
            # 构建请求参数
            salt = str(uuid.uuid1())
            curtime = str(int(time.time()))
            sign_str = self.app_key + self._truncate(text) + salt + curtime + self.app_secret
            sign = hashlib.sha256(sign_str.encode()).hexdigest()
            
            # 处理语言代码格式差异
            source_lang = "auto" if self.source_language == "auto" else self.source_language
            target_lang = self.target_language
            
            # 有道翻译API使用的语言代码可能与其他服务不同，需要转换
            lang_map = {
                "zh-CN": "zh-CHS",
                "en": "en",
                "ja": "ja",
                "ko": "ko",
                "fr": "fr",
                "es": "es",
                "ru": "ru"
            }
            
            source_lang = lang_map.get(source_lang, source_lang)
            target_lang = lang_map.get(target_lang, target_lang)
            
            # 发送请求
            async with aiohttp.ClientSession() as session:
                url = "https://openapi.youdao.com/api"
                payload = {
                    "q": text,
                    "from": source_lang,
                    "to": target_lang,
                    "appKey": self.app_key,
                    "salt": salt,
                    "sign": sign,
                    "signType": "v3",
                    "curtime": curtime
                }
                
                async with session.post(url, data=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("errorCode") == "0":
                            translations = result.get("translation", [])
                            if translations:
                                return translations[0]
                        return text
                    else:
                        print(f"❌ 有道翻译失败，状态码: {response.status}")
                        return text
        except Exception as e:
            print(f"❌ 有道翻译过程中出错: {e}")
            return text
            
    def _truncate(self, q):
        """截断文本"""
        if q is None:
            return None
        size = len(q)
        return q if size <= 20 else q[0:10] + str(size) + q[size - 10:size]

# 主翻译器类
class Translator:
    # 支持的翻译服务映射
    SERVICES: Dict[str, Type[TranslationService]] = {
        'libre': LibreTranslateService,
        'tencent': TencentTranslateService,
        'google': GoogleTranslateService,
        'baidu': BaiduTranslateService,
        'youdao': YoudaoTranslateService
    }
    
    def __init__(self):
        """初始化翻译服务"""
        load_dotenv()
        self.enabled = os.getenv('TRANSLATION_ENABLED', 'false').lower() == 'true'
        self.service_type = os.getenv('TRANSLATION_SERVICE', 'libre').lower()
        self.target_language = os.getenv('TRANSLATION_TARGET_LANGUAGE', 'zh-CN')
        self.source_language = os.getenv('TRANSLATION_SOURCE_LANGUAGE', 'auto')
        
        # 初始化白名单
        whitelist_str = os.getenv('TRANSLATION_WHITELIST', '')
        self.whitelist = [item.strip() for item in whitelist_str.split(',') if item.strip()]
        
        # 初始化翻译服务
        self.service = self._create_service()
        
        # 打印翻译器状态
        if self.enabled:
            print(f"✅ 翻译功能已启用 - 服务类型: {self.service_type}, 目标语言: {self.target_language}")
            if self.whitelist:
                print(f"✅ 翻译白名单已设置: {', '.join(self.whitelist)}")
        else:
            print("❌ 翻译功能已禁用")
    
    def _create_service(self) -> Optional[TranslationService]:
        """创建翻译服务实例"""
        if not self.enabled:
            return None
            
        service_class = self.SERVICES.get(self.service_type)
        if not service_class:
            print(f"❌ 不支持的翻译服务类型: {self.service_type}")
            return None
            
        if not service_class.is_configured():
            print(f"❌ {self.service_type}翻译服务配置不正确")
            return None
            
        return service_class(self.source_language, self.target_language)
            
    def is_enabled(self) -> bool:
        """检查翻译功能是否启用
        
        Returns:
            bool: 翻译功能是否启用
        """
        return self.enabled and self.service is not None
        
    def _contains_code_block(self, text: str) -> bool:
        """检查文本是否包含代码块
        
        Args:
            text: 要检查的文本
            
        Returns:
            bool: 是否包含代码块
        """
        # 检查是否包含Markdown代码块标记 ```
        return "```" in text
        
    def _split_text_and_code_blocks(self, text: str):
        """将文本分割为普通文本和代码块
        
        Args:
            text: 要分割的文本
            
        Returns:
            list: 包含文本片段和类型的列表，类型为"text"或"code"
        """
        parts = []
        is_in_code_block = False
        current_part = ""
        
        # 按行分割文本
        lines = text.split('\n')
        
        for line in lines:
            # 检查是否是代码块开始或结束标记
            if line.strip().startswith("```") or line.strip() == "```":
                # 保存当前部分
                if current_part:
                    parts.append({
                        "type": "code" if is_in_code_block else "text",
                        "content": current_part
                    })
                    current_part = ""
                
                # 切换代码块状态
                is_in_code_block = not is_in_code_block
                
                # 添加当前行（代码块标记）
                current_part += line + "\n"
            else:
                # 添加普通行
                current_part += line + "\n"
        
        # 添加最后一部分
        if current_part:
            parts.append({
                "type": "code" if is_in_code_block else "text",
                "content": current_part
            })
        
        return parts
    
    def _should_skip_translation(self, text: str) -> bool:
        """检查文本是否应该跳过翻译（在白名单中）
        
        Args:
            text: 要检查的文本
            
        Returns:
            bool: 是否应该跳过翻译
        """
        if not self.whitelist:
            return False
            
        for whitelist_item in self.whitelist:
            if whitelist_item in text:
                return True
        return False
    
    async def translate_text(self, text: str) -> str:
        """翻译文本，跳过代码块和白名单内容
        
        Args:
            text: 要翻译的文本
            
        Returns:
            str: 翻译后的文本，如果翻译失败则返回原文本
        """
        if not self.is_enabled() or not text.strip():
            return text
            
        # 检查是否在白名单中
        if self._should_skip_translation(text):
            return text
        
        # 如果不包含代码块，直接翻译整个文本
        if not self._contains_code_block(text):
            try:
                return await self.service.translate(text)
            except Exception as e:
                print(f"❌ 翻译过程中出错: {e}")
                return text
        
        # 包含代码块，分割处理
        try:
            parts = self._split_text_and_code_blocks(text)
            result = ""
            
            for part in parts:
                if part["type"] == "text" and part["content"].strip():
                    # 检查文本部分是否在白名单中
                    if self._should_skip_translation(part["content"]):
                        result += part["content"]
                    else:
                        # 只翻译非代码块且不在白名单中的部分
                        translated = await self.service.translate(part["content"])
                        result += translated
                else:
                    # 代码块部分保持原样
                    result += part["content"]
            
            return result
        except Exception as e:
            print(f"❌ 处理代码块翻译过程中出错: {e}")
            return text