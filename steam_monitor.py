import aiohttp
import json
import asyncio
import os
from pathlib import Path
from rapidfuzz import process, fuzz
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import aiofiles

logger = logging.getLogger("steam_monitor")

class SteamMonitor:
    def __init__(self, config=None):
        self.config = config or {}
        self.data_dir = Path("./data/steam")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.json1_path = self.data_dir / "game_list.json"  # 存储所有Steam游戏英文名与id对应的字典
        self.json2_path = self.data_dir / "monitor_list.json"  # 存储用户或群组的监控列表

        # 确保数据文件存在，如果不存在则创建空文件
        if not self.json1_path.exists():
            with open(self.json1_path, "w", encoding="utf-8") as f:
                json.dump({}, f)
        if not self.json2_path.exists():
            with open(self.json2_path, "w", encoding="utf-8") as f:
                json.dump({}, f)

        # 从配置中获取价格检查间隔时间，默认为 30 分钟
        self.interval_minutes = self.config.get("interval_minutes", 30)
        logger.info("正在初始化Steam游戏价格监控")

        self.scheduler = AsyncIOScheduler()
        # 添加定时任务，每隔 interval_minutes 运行 run_monitor_prices 方法
        self.scheduler.add_job(
            self.run_monitor_prices, "interval", minutes=self.interval_minutes
        )
        
        self.monitor_list_lock = asyncio.Lock()  # 用于保护 monitor_list 文件的读写
        self.data_initialized = asyncio.Event()  # 添加一个Event来标记数据是否初始化完成
        
        # 初始化数据
        self.app_dict_all = {}
        self.app_dict_all_reverse = {}
        self.monitor_list = {}

    async def initialize(self):
        """异步初始化数据，获取游戏列表和加载用户监控列表"""
        await self.get_app_list()  # 获取Steam全量游戏列表
        await self.load_user_monitors()  # 加载用户监控列表
        self.scheduler.start()  # 启动调度器
        
    async def get_game_name_by_id(self, game_id):
        """根据游戏ID获取游戏名称
        
        Args:
            game_id: Steam游戏ID
            
        Returns:
            str: 游戏名称，如果未找到则返回None
        """
        # 确保游戏列表已加载
        if not self.app_dict_all:
            await self.get_app_list()
            
        # 从反向字典中查找游戏名称
        game_id = str(game_id)  # 确保ID是字符串
        if game_id in self.app_dict_all_reverse:
            return self.app_dict_all_reverse[game_id]
            
        # 如果本地缓存中没有，尝试从Steam API获取
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://store.steampowered.com/api/appdetails?appids={game_id}"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data and data.get(game_id, {}).get('success', False):
                            game_name = data[game_id]['data']['name']
                            # 更新本地缓存
                            self.app_dict_all_reverse[game_id] = game_name
                            self.app_dict_all[game_name] = game_id
                            return game_name
        except Exception as e:
            logger.error(f"获取游戏名称失败: {e}")
            
        return None
        
    async def initialize(self):
        """异步初始化数据，获取游戏列表和加载用户监控列表"""
        await self.get_app_list()  # 获取Steam全量游戏列表
        await self.load_user_monitors()  # 加载用户监控列表
        self.scheduler.start()  # 启动调度器
        self.data_initialized.set()  # 设置Event，表示数据初始化完成
        logger.info("Steam监控初始化完成")
        
    async def add_game(self, game_input):
        """添加游戏到监控列表
        
        Args:
            game_input: 游戏名称或ID
            
        Returns:
            bool: 添加成功返回True，否则返回False
        """
        # 确保数据已初始化
        if not self.data_initialized.is_set():
            await self.initialize()
            
        # 检查是否为游戏ID
        if str(game_input).isdigit():
            game_id = str(game_input)
            game_name = await self.get_game_name_by_id(game_id)
            if not game_name:
                logger.error(f"未找到ID为 {game_id} 的游戏")
                return False
        else:
            # 尝试查找游戏名称
            game_name = game_input
            if game_name not in self.app_dict_all:
                # 尝试模糊匹配
                matches = process.extract(game_name, self.app_dict_all.keys(), scorer=fuzz.token_sort_ratio, limit=1)
                if matches and matches[0][1] > 80:  # 匹配度大于80%
                    game_name = matches[0][0]
                else:
                    logger.error(f"未找到名称为 {game_name} 的游戏")
                    return False
            game_id = self.app_dict_all[game_name]
            
        # 添加到监控列表
        async with self.monitor_list_lock:
            # 创建默认用户ID
            default_user_id = "default"
            if default_user_id not in self.monitor_list:
                self.monitor_list[default_user_id] = []
                
            # 检查是否已在监控列表中
            for game in self.monitor_list[default_user_id]:
                if game['id'] == game_id:
                    logger.info(f"游戏 {game_name} 已在监控列表中")
                    return False
                    
            # 添加游戏到监控列表
            self.monitor_list[default_user_id].append({
                'id': game_id,
                'name': game_name,
                'price': None,  # 初始价格为空，将在下次检查时更新
                'currency': 'CNY'
            })
            
            # 保存监控列表
            await self.save_monitor_list()
            logger.info(f"已添加游戏 {game_name} (ID: {game_id}) 到监控列表")
            return True
            
    async def remove_game(self, game_input):
        """从监控列表中移除游戏
        
        Args:
            game_input: 游戏名称或ID
            
        Returns:
            bool: 移除成功返回True，否则返回False
        """
        # 确保数据已初始化
        if not self.data_initialized.is_set():
            await self.initialize()
            
        # 检查是否为游戏ID
        if str(game_input).isdigit():
            game_id = str(game_input)
            game_name = await self.get_game_name_by_id(game_id)
            if not game_name:
                logger.error(f"未找到ID为 {game_id} 的游戏")
                return False
        else:
            # 尝试查找游戏名称
            game_name = game_input
            if game_name not in self.app_dict_all:
                # 尝试模糊匹配
                matches = process.extract(game_name, self.app_dict_all.keys(), scorer=fuzz.token_sort_ratio, limit=1)
                if matches and matches[0][1] > 80:  # 匹配度大于80%
                    game_name = matches[0][0]
                else:
                    logger.error(f"未找到名称为 {game_name} 的游戏")
                    return False
            game_id = self.app_dict_all[game_name]
            
        # 从监控列表中移除
        async with self.monitor_list_lock:
            # 创建默认用户ID
            default_user_id = "default"
            if default_user_id not in self.monitor_list:
                logger.error("监控列表为空")
                return False
                
            # 查找并移除游戏
            removed = False
            for i, game in enumerate(self.monitor_list[default_user_id]):
                if game['id'] == game_id:
                    self.monitor_list[default_user_id].pop(i)
                    removed = True
                    break
                    
            if not removed:
                logger.error(f"游戏 {game_name} 不在监控列表中")
                return False
                
            # 保存监控列表
            await self.save_monitor_list()
            logger.info(f"已从监控列表中移除游戏 {game_name} (ID: {game_id})")
            return True
            
    async def get_monitored_games(self):
        """获取当前监控的游戏列表
        
        Returns:
            list: 监控的游戏列表，每个游戏包含id、name、price、currency等信息
        """
        # 确保数据已初始化
        if not self.data_initialized.is_set():
            await self.initialize()
            
        # 获取默认用户的监控列表
        default_user_id = "default"
        if default_user_id not in self.monitor_list:
            return []
            
        return self.monitor_list[default_user_id]
        
    async def save_monitor_list(self):
        """保存监控列表到文件"""
        # 确保数据目录存在
        os.makedirs(self.data_dir, exist_ok=True)
        
        # 保存监控列表到文件
        monitor_file = os.path.join(self.data_dir, 'monitor_list.json')
        async with aiofiles.open(monitor_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(self.monitor_list, ensure_ascii=False, indent=2))
        
        logger.info("监控列表已保存")

    async def get_app_list(self):
        """获取Steam全量游戏列表（AppID + 名称），并缓存到 game_list.json"""
        try:
            url = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    res = await response.json()
            self.app_dict_all = {
                app["name"]: app["appid"] for app in res["applist"]["apps"]
            }
            self.app_dict_all_reverse = {v: k for k, v in self.app_dict_all.items()}
            with open(self.json1_path, "w", encoding="utf-8") as f:
                json.dump(self.app_dict_all, f, ensure_ascii=False, indent=4)
            logger.info("Steam游戏列表更新成功")
        except Exception as e:
            logger.error(f"获取游戏列表失败：{e}")
            self.app_dict_all = {}  # 确保即使失败也初始化为空字典
        finally:  # 无论成功失败，都尝试从文件中加载，避免空字典
            if not self.app_dict_all:  # 如果上面失败了，尝试从本地文件加载
                try:
                    with open(self.json1_path, "r", encoding="utf-8") as f:
                        self.app_dict_all = json.load(f)
                    self.app_dict_all_reverse = {
                        v: k for k, v in self.app_dict_all.items()
                    }
                    logger.info("从本地文件加载Steam游戏列表成功")
                except Exception as e:
                    logger.error(f"从本地文件加载游戏列表失败：{e}")
                    self.app_dict_all = {}  # 彻底失败则设置为空
                    self.app_dict_all_reverse = {}

    async def load_user_monitors(self):
        """加载用户监控列表（从 monitor_list.json 文件）"""
        try:
            async with self.monitor_list_lock:  # 加锁读取，防止文件被其他操作同时修改
                with open(self.json2_path, "r", encoding="utf-8") as f:
                    self.monitor_list = json.load(f)
            logger.info("监控列表加载成功")
        except (FileNotFoundError, json.JSONDecodeError) as e:  # 组合异常捕获
            self.monitor_list = {}  # 文件不存在或者文件损坏时初始化为空字典
            logger.info(f"监控列表文件不存在或损坏，已创建空列表: {e}")
            with open(self.json2_path, "w", encoding="utf-8") as f:
                json.dump({}, f)

    async def get_appid_by_name(self, user_input):
        """
        模糊匹配游戏名到AppID。
        Args:
            user_input (str): 用户输入的待匹配游戏名。
        Returns:
            list or None: 如果找到匹配项，返回 [AppID, 匹配的游戏名]，否则返回 None。
        """
        logger.info(f"正在模糊匹配游戏名: {user_input}")
        # 等待数据初始化完成
        await self.data_initialized.wait()
        
        if not self.app_dict_all:  # 检查字典是否为空
            logger.warning("游戏列表为空，无法进行模糊匹配")
            return None

        matched_result = process.extractOne(
            user_input, self.app_dict_all.keys(), scorer=fuzz.token_set_ratio
        )
        if matched_result and matched_result[1] >= 70:
            matched_name = matched_result[0]
            return [self.app_dict_all[matched_name], matched_name]
        else:
            return None

    async def get_steam_price(self, appid, region="cn"):
        """
        获取游戏价格信息。
        Args:
            appid (str or int): Steam 游戏的 AppID。
            region (str): 区域代码，默认为 "cn" (中国)。
        Returns:
            dict or None: 包含价格信息的字典，或 None（如果获取失败或游戏不存在）。
        """
        try:
            url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc={region}&l=zh-cn"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    res = await response.json()

            data = res.get(str(appid))
            if not data or not data.get("success"):
                logger.warning(f"获取游戏 {appid} 价格失败或游戏不存在，data: {data}")
                return None

            game_data = data["data"]
            if game_data.get("is_free"):  # 免费游戏
                return {
                    "is_free": True,
                    "current_price": 0,
                    "original_price": 0,
                    "discount": 100,
                    "currency": "FREE",
                }

            price_info = game_data.get("price_overview")
            if not price_info:
                logger.info(
                    f"游戏 {game_data.get('name', appid)} 没有价格信息 (可能即将发售或未在 {region} 区域上架)。"
                )
                return None

            return {
                "is_free": False,
                "current_price": price_info["final"] / 100,  # 单位转换为元
                "original_price": price_info["initial"] / 100,
                "discount": price_info["discount_percent"],
                "currency": price_info["currency"],  # 货币类型
            }
        except Exception as e:
            logger.error(f"获取游戏 {appid} 价格时发生异常：{e}")
            return None

    async def add_monitor(self, user_id, channel_id, game_name):
        """
        添加游戏监控。
        Args:
            user_id (str): 用户ID
            channel_id (str): 频道ID
            game_name (str): 游戏名称
        Returns:
            tuple: (成功标志, 消息, 游戏信息)
        """
        # 等待数据初始化完成
        await self.data_initialized.wait()
        
        # 模糊匹配游戏名称
        match_result = await self.get_appid_by_name(game_name)
        if not match_result:
            return False, f"未找到与 '{game_name}' 匹配的游戏，请尝试更准确的名称", None
        
        appid, matched_name = match_result
        
        # 获取游戏价格信息
        price_info = await self.get_steam_price(appid)
        if not price_info:
            return False, f"无法获取游戏 '{matched_name}' 的价格信息", None
        
        # 构建监控信息
        monitor_info = {
            "appid": appid,
            "name": matched_name,
            "last_price": price_info.get("current_price", 0),
            "last_discount": price_info.get("discount", 0),
            "currency": price_info.get("currency", "CNY"),
            "added_time": asyncio.get_event_loop().time(),  # 使用当前时间作为添加时间
        }
        
        # 更新监控列表
        key = f"{user_id}_{channel_id}"
        async with self.monitor_list_lock:
            if key not in self.monitor_list:
                self.monitor_list[key] = {}
            
            # 检查是否已经在监控
            if str(appid) in self.monitor_list[key]:
                return False, f"游戏 '{matched_name}' 已在监控列表中", monitor_info
            
            # 添加到监控列表
            self.monitor_list[key][str(appid)] = monitor_info
            
            # 保存到文件
            with open(self.json2_path, "w", encoding="utf-8") as f:
                json.dump(self.monitor_list, f, ensure_ascii=False, indent=4)
        
        return True, f"已添加游戏 '{matched_name}' 到监控列表", monitor_info

    async def remove_monitor(self, user_id, channel_id, game_name):
        """
        移除游戏监控。
        Args:
            user_id (str): 用户ID
            channel_id (str): 频道ID
            game_name (str): 游戏名称
        Returns:
            tuple: (成功标志, 消息)
        """
        # 等待数据初始化完成
        await self.data_initialized.wait()
        
        key = f"{user_id}_{channel_id}"
        
        # 检查是否有监控列表
        if key not in self.monitor_list:
            return False, "您没有任何监控游戏"
        
        # 如果输入为空，则移除所有监控
        if not game_name:
            async with self.monitor_list_lock:
                del self.monitor_list[key]
                with open(self.json2_path, "w", encoding="utf-8") as f:
                    json.dump(self.monitor_list, f, ensure_ascii=False, indent=4)
            return True, "已移除所有监控游戏"
        
        # 模糊匹配游戏名称
        match_result = await self.get_appid_by_name(game_name)
        if not match_result:
            # 尝试在用户的监控列表中匹配
            user_games = {
                self.app_dict_all_reverse.get(int(appid), appid): appid
                for appid in self.monitor_list[key].keys()
            }
            match_in_user_list = process.extractOne(
                game_name, user_games.keys(), scorer=fuzz.token_set_ratio
            )
            
            if match_in_user_list and match_in_user_list[1] >= 70:
                matched_name = match_in_user_list[0]
                appid = user_games[matched_name]
            else:
                return False, f"未找到与 '{game_name}' 匹配的游戏，请尝试更准确的名称"
        else:
            appid, matched_name = match_result
            appid = str(appid)
        
        # 检查游戏是否在监控列表中
        if appid not in self.monitor_list[key]:
            return False, f"游戏 '{matched_name}' 不在监控列表中"
        
        # 移除监控
        async with self.monitor_list_lock:
            del self.monitor_list[key][appid]
            
            # 如果用户没有监控任何游戏，则移除用户
            if not self.monitor_list[key]:
                del self.monitor_list[key]
            
            # 保存到文件
            with open(self.json2_path, "w", encoding="utf-8") as f:
                json.dump(self.monitor_list, f, ensure_ascii=False, indent=4)
        
        return True, f"已移除游戏 '{matched_name}' 的监控"

    async def list_monitors(self, user_id, channel_id):
        """
        列出用户监控的游戏。
        Args:
            user_id (str): 用户ID
            channel_id (str): 频道ID
        Returns:
            list: 监控游戏列表
        """
        # 等待数据初始化完成
        await self.data_initialized.wait()
        
        key = f"{user_id}_{channel_id}"
        
        # 检查是否有监控列表
        if key not in self.monitor_list or not self.monitor_list[key]:
            return []
        
        # 返回监控列表
        return list(self.monitor_list[key].values())

    async def run_monitor_prices(self):
        """定时检查价格变动并发送通知"""
        logger.info("开始检查游戏价格变动")
        
        # 等待数据初始化完成
        if not self.data_initialized.is_set():
            logger.warning("数据尚未初始化完成，跳过本次价格检查")
            return
        
        # 检查是否有监控列表
        if not self.monitor_list:
            logger.info("没有监控列表，跳过本次价格检查")
            return
        
        price_changes = []  # 存储价格变动信息
        
        # 遍历所有监控列表
        for key, games in self.monitor_list.items():
            user_id, channel_id = key.split("_")
            
            for appid, game_info in games.items():
                # 获取最新价格
                price_info = await self.get_steam_price(appid)
                if not price_info:
                    logger.warning(f"无法获取游戏 {game_info['name']} 的价格信息，跳过")
                    continue
                
                # 检查价格是否变动
                last_price = game_info["last_price"]
                last_discount = game_info["last_discount"]
                current_price = price_info["current_price"]
                current_discount = price_info["discount"]
                
                # 价格下降或折扣增加
                if current_price < last_price or current_discount > last_discount:
                    # 更新监控信息
                    game_info["last_price"] = current_price
                    game_info["last_discount"] = current_discount
                    
                    # 添加到价格变动列表
                    price_changes.append({
                        "user_id": user_id,
                        "channel_id": channel_id,
                        "game_name": game_info["name"],
                        "appid": appid,
                        "old_price": last_price,
                        "new_price": current_price,
                        "old_discount": last_discount,
                        "new_discount": current_discount,
                        "currency": price_info["currency"],
                    })
        
        # 保存更新后的监控列表
        if price_changes:
            async with self.monitor_list_lock:
                with open(self.json2_path, "w", encoding="utf-8") as f:
                    json.dump(self.monitor_list, f, ensure_ascii=False, indent=4)
        
        # 返回价格变动列表，由调用者处理通知
        return price_changes

    def format_price_message(self, change_info):
        """
        格式化价格变动消息。
        Args:
            change_info (dict): 价格变动信息
        Returns:
            str: 格式化后的消息
        """
        game_name = change_info["game_name"]
        appid = change_info["appid"]
        old_price = change_info["old_price"]
        new_price = change_info["new_price"]
        old_discount = change_info["old_discount"]
        new_discount = change_info["new_discount"]
        currency = change_info["currency"]
        
        # 构建消息
        message = f"🎮 **{game_name}** 价格变动通知！\n\n"
        
        # 价格变动
        if new_price < old_price:
            message += f"💰 价格: ~~{old_price} {currency}~~ → **{new_price} {currency}**\n"
            message += f"📉 降价: **{old_price - new_price} {currency}** (-{((old_price - new_price) / old_price * 100):.1f}%)\n"
        
        # 折扣变动
        if new_discount > old_discount:
            message += f"🏷️ 折扣: ~~{old_discount}%~~ → **{new_discount}%**\n"
        
        # 添加商店链接
        message += f"\n🔗 商店链接: https://store.steampowered.com/app/{appid}\n"
        
        return message