# 📋 Phase 2: Reader服務整合 - 部署指南

## 🎯 **已完成功能**

### **✅ Reader服務集群**
```yaml
reader-1          # 端口 8080 (內部)
reader-2          # 端口 8080 (內部) 
reader-lb         # 端口 8880 (對外負載平衡)
```

### **✅ Reader批量處理器**
```yaml
reader-processor  # 端口 8009
- 並行調用Reader集群
- 自動狀態更新到數據庫
- 支援重試和錯誤處理
```

### **✅ 統一爬蟲協調器**
```yaml
crawl-coordinator # 端口 8008
- fast模式：純Reader快速提取
- full模式：純Playwright完整爬取
- hybrid模式：先快後全並行處理
```

### **✅ 雙軌狀態追蹤**
```sql
-- 數據庫新欄位
reader_status       TEXT DEFAULT 'pending'     -- Reader處理狀態
dom_status          TEXT DEFAULT 'pending'     -- DOM爬取狀態  
reader_processed_at TIMESTAMPTZ               -- Reader處理時間
dom_processed_at    TIMESTAMPTZ               -- DOM處理時間
```

---

## 🚀 **部署步驟**

### **步驟1: 數據庫遷移**
```bash
# 方法A: 使用Python腳本（推薦）
python run_dual_track_migration.py

# 方法B: 直接執行SQL
psql -d your_database -f add_dual_track_status_columns.sql
```

### **步驟2: 服務部署**
```bash
# 完整重新部署（包含所有新服務）
docker compose down
docker compose up -d --build

# 檢查服務健康狀態
docker compose ps
```

### **步驟3: 服務驗證**
```bash
# 檢查各服務狀態
curl http://localhost:8880/health  # Reader LB
curl http://localhost:8009/health  # Reader Processor  
curl http://localhost:8008/health  # Crawl Coordinator
curl http://localhost:8006/health  # Playwright Crawler

# 執行完整系統測試
python test_dual_track_system.py
```

---

## 🎯 **API使用指南**

### **1. 快速模式（推薦用於內容預覽）**
```bash
curl -X POST "http://localhost:8008/crawl" \
     -H "Content-Type: application/json" \
     -d '{
       "username": "natgeo",
       "max_posts": 10,
       "mode": "fast"
     }'
```

**回應格式：**
```json
{
  "task_id": "uuid",
  "username": "natgeo",
  "mode": "fast",
  "status": "completed",
  "message": "Reader處理完成: 8/10 成功",
  "posts": [
    {
      "url": "https://www.threads.com/@natgeo/post/xxx",
      "post_id": "natgeo_xxx",
      "reader_status": "success",
      "dom_status": "pending", 
      "content": "LLM友好的內容..."
    }
  ],
  "summary": {
    "successful": 8,
    "failed": 2,
    "total_time": 12.5
  }
}
```

### **2. 混合模式（推薦用於完整分析）**
```bash
curl -X POST "http://localhost:8008/crawl" \
     -H "Content-Type: application/json" \
     -d '{
       "username": "natgeo", 
       "max_posts": 10,
       "mode": "hybrid",
       "also_slow": true,
       "auth_json_content": { /* 認證信息 */ }
     }'
```

**特點：**
- 立即返回Reader結果（秒級）
- 背景自動補充DOM數據（分鐘級）
- 前端可實時更新狀態

### **3. 狀態查詢**
```bash
# 查詢用戶貼文狀態
curl "http://localhost:8006/urls/natgeo?max_posts=20"

# 查詢處理統計
curl "http://localhost:8008/status/natgeo"
```

---

## 📊 **性能特點**

### **Reader模式性能**
```
處理速度：     ~40 URLs/分鐘 (2副本)
響應時間：     2-5秒/URL
資源使用：     2 CPU cores, 2GB RAM
數據完整度：   內容+基礎數據
```

### **混合模式優勢**
```
即時響應：     Reader結果立即返回（秒級）
完整補足：     DOM數據背景補充（分鐘級）
用戶體驗：     先看內容，後看完整數據
```

### **狀態追蹤**
```
Reader狀態：   success/failed/pending
DOM狀態：      success/failed/pending  
處理時間：     精確到毫秒
去重判斷：     自動避免重複處理
```

---

## 🔧 **常見問題排查**

### **問題1: Reader服務無法啟動**
```bash
# 檢查Docker映像
docker images | grep jinaai/reader

# 檢查端口衝突
netstat -tulpn | grep 8880

# 查看Reader容器日誌
docker logs social-media-reader-1 -f
docker logs social-media-reader-2 -f
```

### **問題2: 負載平衡器錯誤**
```bash
# 檢查nginx配置
docker exec social-media-reader-lb nginx -t

# 查看nginx日誌
docker logs social-media-reader-lb -f

# 測試上游服務
curl http://localhost:8880/health
```

### **問題3: 數據庫狀態異常**
```sql
-- 檢查新欄位
\d post_metrics_sql

-- 檢查狀態分布
SELECT reader_status, dom_status, COUNT(*) 
FROM post_metrics_sql 
GROUP BY reader_status, dom_status;

-- 重置狀態（如果需要）
UPDATE post_metrics_sql SET reader_status = 'pending', dom_status = 'pending';
```

### **問題4: 服務間通信失敗**
```bash
# 檢查Docker網絡
docker network ls
docker network inspect social-media-content-generator_social-media-network

# 檢查服務發現
docker exec social-media-crawl-coordinator nslookup reader-processor
docker exec social-media-reader-processor nslookup reader-lb
```

---

## 📈 **監控建議**

### **關鍵指標監控**
```
Reader集群：
- 健康檢查通過率
- 平均響應時間  
- 錯誤率
- 併發處理數

數據庫：
- Reader/DOM狀態分布
- 處理進度百分比
- 失敗任務數量

協調器：
- API調用量
- 模式分布統計
- 背景任務完成率
```

### **日誌監控**
```bash
# 關鍵服務日誌
docker logs social-media-reader-lb -f --tail 100
docker logs social-media-reader-processor -f --tail 100  
docker logs social-media-crawl-coordinator -f --tail 100

# 錯誤過濾
docker logs social-media-reader-processor 2>&1 | grep "ERROR\|FAILED"
```

---

## 🎉 **Phase 2 完成確認**

### **✅ 功能清單**
- [x] Reader服務集群部署
- [x] Nginx負載平衡配置
- [x] Reader批量處理器
- [x] 統一爬蟲協調器
- [x] 雙軌狀態追蹤
- [x] 數據庫自動更新
- [x] API統一接口
- [x] 測試腳本

### **✅ 部署驗證**
1. 所有Docker服務健康運行
2. API端點正常響應
3. 數據庫狀態正確更新
4. Reader處理功能正常
5. 雙軌狀態追蹤生效

### **🚀 下一步：Phase 3 UI整合**
- 前端狀態管理
- 實時更新（WebSocket/SSE）
- 批量操作界面
- 統計圖表和進度條

**🎊 恭喜！雙軌爬蟲系統 Phase 2 部署完成！**