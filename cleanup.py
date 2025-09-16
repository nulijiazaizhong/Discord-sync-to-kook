import os
import time
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta

class CleanupService:
    def __init__(self, download_dir="downloads", cleanup_interval=24, max_age=72):
        """
        初始化清理服务
        
        Args:
            download_dir: 下载目录路径
            cleanup_interval: 清理间隔，单位为小时
            max_age: 文件最大保留时间，单位为小时
        """
        self.download_dir = Path(download_dir)
        self.cleanup_interval = cleanup_interval
        self.max_age = max_age
        self.logger = logging.getLogger("CleanupService")
        
        # 确保下载目录存在
        self.ensure_directories()
        
    def ensure_directories(self):
        """确保下载目录及子目录存在"""
        for subdir in ["images", "videos"]:
            dir_path = self.download_dir / subdir
            if not dir_path.exists():
                dir_path.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"创建目录: {dir_path}")
    
    async def start_cleanup_task(self):
        """启动定期清理任务"""
        self.logger.info(f"启动定期清理任务，间隔: {self.cleanup_interval}小时，最大保留时间: {self.max_age}小时")
        while True:
            try:
                await self.cleanup_old_files()
                # 转换小时为秒
                await asyncio.sleep(self.cleanup_interval * 3600)
            except Exception as e:
                self.logger.error(f"清理任务出错: {e}")
                # 出错后等待10分钟再重试
                await asyncio.sleep(600)
    
    async def cleanup_old_files(self):
        """清理过期文件"""
        now = time.time()
        max_age_seconds = self.max_age * 3600
        deleted_count = 0
        
        self.logger.info(f"开始清理过期文件，最大保留时间: {self.max_age}小时")
        
        # 遍历下载目录的所有子目录
        for subdir in ["images", "videos"]:
            dir_path = self.download_dir / subdir
            if not dir_path.exists():
                continue
                
            for file_path in dir_path.glob("*"):
                if not file_path.is_file():
                    continue
                    
                # 获取文件修改时间
                file_mtime = file_path.stat().st_mtime
                file_age = now - file_mtime
                
                # 如果文件超过最大保留时间，则删除
                if file_age > max_age_seconds:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                        self.logger.debug(f"已删除过期文件: {file_path}")
                    except Exception as e:
                        self.logger.error(f"删除文件失败 {file_path}: {e}")
        
        self.logger.info(f"清理完成，共删除 {deleted_count} 个过期文件")
        return deleted_count

def get_cleanup_service():
    """
    从环境变量获取配置并创建清理服务实例
    """
    from dotenv import load_dotenv
    load_dotenv()
    
    # 从环境变量获取配置，如果不存在则使用默认值
    cleanup_interval = int(os.getenv("CLEANUP_INTERVAL", "24"))
    max_age = int(os.getenv("CLEANUP_MAX_AGE", "72"))
    download_dir = os.getenv("DOWNLOAD_DIR", "downloads")
    
    return CleanupService(
        download_dir=download_dir,
        cleanup_interval=cleanup_interval,
        max_age=max_age
    )