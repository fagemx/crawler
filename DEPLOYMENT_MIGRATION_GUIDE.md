# 🚀 部署更新指南 (終極簡化版)

## 📊 新功能概述

本次更新添加了兩個重要欄位：
- `post_published_at`: 真實貼文發布時間 (從DOM提取)
- `tags`: 主題標籤陣列 (從標籤連結提取)

## 🔄 **一鍵部署**

### 就這麼簡單：
```bash
docker compose up -d --build
```

✅ **完成！** 新欄位已經包含在 `scripts/init-db.sql` 中了

### 如果遇到資料庫衝突：
```bash
# 停止並移除容器
docker compose down

# 移除資料庫 volume (如果需要)
docker volume rm <your_db_volume_name>

# 重新啟動
docker compose up -d --build
```

### 第3步：驗證遷移
```sql
-- 連接到數據庫確認欄位已添加
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'posts' 
AND column_name IN ('post_published_at', 'tags')
ORDER BY column_name;
```

### 第4步：重啟服務
```bash
# 重啟應用服務
docker restart <container_name>
# 或
docker-compose restart app
```

## 🔍 遷移後確認

### 檢查新功能是否運作
1. **查看爬蟲日誌**，應該會看到類似：
   ```
   ✅ 混合策略成功補齊 natgeo_DM2oBhXqFcx: 讚=816, 內容=65字, 圖片=1個, 影片=0個, 發文時間=2025-07-30 15:22, 標籤=['動物攝影']
   ```

2. **查看數據庫數據**：
   ```sql
   SELECT url, post_published_at, tags, created_at 
   FROM posts 
   WHERE post_published_at IS NOT NULL 
   LIMIT 5;
   ```

## ⚠️ 回滾計劃

如果遇到問題，可以回滾：

```bash
# 回滾數據庫遷移
python run_new_migration.py rollback

# 回滾代碼 (如有需要)
git reset --hard <previous_commit_hash>
```

## 📝 注意事項

1. **向下兼容**：新欄位為可選，不會影響現有功能
2. **漸進填充**：現有貼文的新欄位會在下次爬蟲運行時自動填充
3. **零停機**：遷移過程不會中斷服務運行
4. **數據安全**：建議在遷移前備份數據庫

## 🆘 問題排除

### 常見問題

1. **DATABASE_URL 未設定**
   ```bash
   # 檢查環境變數
   echo $DATABASE_URL
   # 或在容器內檢查 .env 文件
   cat .env | grep DATABASE_URL
   ```

2. **權限問題**
   ```bash
   # 確認數據庫用戶有 ALTER TABLE 權限
   ```

3. **容器無法連接數據庫**
   ```bash
   # 檢查網絡連接
   docker network ls
   docker inspect <container_name>
   ```

## 📞 聯絡支援

如遇問題，請提供：
- 錯誤訊息完整日誌
- 部署環境資訊 (Docker版本、數據庫版本)
- 執行的具體命令