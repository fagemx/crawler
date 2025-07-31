"""
爬蟲結果持久化存儲管理器
用於保存和讀取爬蟲結果，供分析agent使用
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

class CrawlerStorageManager:
    def __init__(self, storage_dir: str = "storage/crawler_results"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.storage_dir / "index.json"
        self._ensure_index_exists()
    
    def _ensure_index_exists(self):
        """確保索引文件存在"""
        if not self.index_file.exists():
            self._save_index([])
    
    def _load_index(self) -> List[Dict[str, Any]]:
        """載入索引"""
        try:
            with open(self.index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    
    def _save_index(self, index: List[Dict[str, Any]]):
        """保存索引"""
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2, default=str)
    
    def save_crawler_result(self, 
                          username: str, 
                          posts_data: List[Dict[str, Any]], 
                          batch_id: str,
                          metadata: Optional[Dict[str, Any]] = None) -> str:
        """保存爬蟲結果"""
        timestamp = datetime.now()
        
        # 創建結果記錄
        result_record = {
            "batch_id": batch_id,
            "username": username,
            "crawled_at": timestamp.isoformat(),
            "posts_count": len(posts_data),
            "metadata": metadata or {},
            "file_path": f"{batch_id}.json"
        }
        
        # 保存實際數據
        data_file = self.storage_dir / f"{batch_id}.json"
        result_data = {
            "batch_id": batch_id,
            "username": username,
            "crawled_at": timestamp.isoformat(),
            "posts_data": posts_data,
            "metadata": metadata or {}
        }
        
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2, default=str)
        
        # 更新索引
        index = self._load_index()
        # 檢查是否已存在該batch_id的記錄
        existing_index = None
        for i, record in enumerate(index):
            if record["batch_id"] == batch_id:
                existing_index = i
                break
        
        if existing_index is not None:
            index[existing_index] = result_record
        else:
            index.append(result_record)
        
        # 按時間倒序排列（最新的在前）
        index.sort(key=lambda x: x["crawled_at"], reverse=True)
        self._save_index(index)
        
        return batch_id
    
    def get_crawler_results_list(self) -> List[Dict[str, Any]]:
        """獲取爬蟲結果列表（用於UI顯示）"""
        return self._load_index()
    
    def get_crawler_result(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """獲取特定的爬蟲結果"""
        data_file = self.storage_dir / f"{batch_id}.json"
        if not data_file.exists():
            return None
        
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    
    def get_latest_result_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """獲取特定用戶的最新爬蟲結果"""
        index = self._load_index()
        for record in index:
            if record["username"] == username:
                return self.get_crawler_result(record["batch_id"])
        return None
    
    def delete_crawler_result(self, batch_id: str) -> bool:
        """刪除爬蟲結果"""
        data_file = self.storage_dir / f"{batch_id}.json"
        
        # 從索引中移除
        index = self._load_index()
        index = [record for record in index if record["batch_id"] != batch_id]
        self._save_index(index)
        
        # 刪除數據文件
        if data_file.exists():
            data_file.unlink()
            return True
        return False
    
    def cleanup_old_results(self, keep_count: int = 50):
        """清理舊的爬蟲結果，只保留最新的 keep_count 條"""
        index = self._load_index()
        if len(index) <= keep_count:
            return
        
        # 獲取要刪除的記錄
        to_delete = index[keep_count:]
        
        # 刪除文件
        for record in to_delete:
            data_file = self.storage_dir / record["file_path"]
            if data_file.exists():
                data_file.unlink()
        
        # 更新索引
        index = index[:keep_count]
        self._save_index(index)

# 全局實例
_crawler_storage = None

def get_crawler_storage() -> CrawlerStorageManager:
    """獲取爬蟲存儲管理器實例"""
    global _crawler_storage
    if _crawler_storage is None:
        _crawler_storage = CrawlerStorageManager()
    return _crawler_storage