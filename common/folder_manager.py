"""
文件夹自动管理模块 - 自动清理超过限制的旧文件
"""
from pathlib import Path
from typing import List, Optional
import logging

class FolderManager:
    """文件夹自动管理器"""
    
    @staticmethod
    def cleanup_old_files(
        folder_path: Path, 
        max_files: int = 50, 
        pattern: str = "*",
        exclude_patterns: Optional[List[str]] = None
    ) -> int:
        """
        清理文件夹中的旧文件，保留最新的 max_files 个
        
        Args:
            folder_path: 文件夹路径
            max_files: 最大保留文件数
            pattern: 文件匹配模式（如 "*.json"）
            exclude_patterns: 排除的文件模式列表
            
        Returns:
            int: 删除的文件数量
        """
        try:
            if not folder_path.exists():
                return 0
                
            # 获取所有匹配的文件
            all_files = list(folder_path.glob(pattern))
            
            # 排除指定模式的文件
            if exclude_patterns:
                filtered_files = []
                for file in all_files:
                    should_exclude = False
                    for exclude_pattern in exclude_patterns:
                        if file.match(exclude_pattern):
                            should_exclude = True
                            break
                    if not should_exclude:
                        filtered_files.append(file)
                all_files = filtered_files
            
            # 按修改时间排序，最新的在前
            all_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            
            # 如果文件数量超过限制，删除最旧的
            if len(all_files) > max_files:
                files_to_delete = all_files[max_files:]
                deleted_count = 0
                
                for file in files_to_delete:
                    try:
                        file.unlink()
                        deleted_count += 1
                        logging.debug(f"📂 删除旧文件: {file.name}")
                    except Exception as e:
                        logging.warning(f"⚠️ 删除文件失败 {file.name}: {e}")
                
                if deleted_count > 0:
                    logging.info(f"🧹 文件夹 {folder_path.name} 清理完成: 删除 {deleted_count} 个旧文件，保留最新 {len(all_files) - deleted_count} 个")
                
                return deleted_count
            
            return 0
            
        except Exception as e:
            logging.error(f"❌ 文件夹清理失败 {folder_path}: {e}")
            return 0
    
    @staticmethod
    def ensure_folder_and_cleanup(
        folder_path: Path,
        max_files: int = 50,
        pattern: str = "*",
        exclude_patterns: Optional[List[str]] = None
    ) -> Path:
        """
        确保文件夹存在并执行清理
        
        Args:
            folder_path: 文件夹路径
            max_files: 最大保留文件数
            pattern: 文件匹配模式
            exclude_patterns: 排除的文件模式列表
            
        Returns:
            Path: 文件夹路径
        """
        # 创建文件夹
        folder_path.mkdir(exist_ok=True)
        
        # 执行清理
        FolderManager.cleanup_old_files(
            folder_path, 
            max_files=max_files, 
            pattern=pattern,
            exclude_patterns=exclude_patterns
        )
        
        return folder_path

    @staticmethod
    def setup_project_folders():
        """
        設置專案所需的資料夾結構並執行清理
        """
        from pathlib import Path
        
        project_root = Path.cwd()
        
        # 定義需要管理的資料夾配置
        folders_config = {
            "temp_progress": {
                "path": project_root / "temp_progress",
                "max_files": 50,
                "pattern": "*.json"
            },
            "extraction_results": {
                "path": project_root / "extraction_results", 
                "max_files": 50,
                "pattern": "*.json"
            },
            "playwright_results": {
                "path": project_root / "playwright_results",
                "max_files": 50, 
                "pattern": "*"
            },
            "playwright_debug": {
                "path": project_root / "agents" / "playwright_crawler" / "debug",
                "max_files": 50,
                "pattern": "*"
            }
        }
        
        # 創建並清理各個資料夾
        for folder_name, config in folders_config.items():
            folder_path = FolderManager.ensure_folder_and_cleanup(
                config["path"],
                max_files=config["max_files"],
                pattern=config["pattern"]
            )
            logging.info(f"✅ 資料夾已設置: {folder_path}")
        
        return folders_config