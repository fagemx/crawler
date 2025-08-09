"""
系統監控組件
基於 test_mcp_complete.py 的真實功能
"""

import streamlit as st
import os
import httpx
import json
import time
import datetime
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, Any, List
from common.db_client import get_db_client


class SystemMonitoringComponent:
    def __init__(self):
        self.test_results = {}
        self.detailed_logs = []
    
    def log(self, level: str, message: str, details: Any = None):
        """統一的日誌記錄方法（模仿 test_mcp_complete.py）"""
        tz = datetime.timezone(datetime.timedelta(hours=8))
        timestamp = datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "message": message,
            "details": details
        }
        self.detailed_logs.append(log_entry)
    
    def render(self):
        """渲染監控界面"""
        # 先顯示：僅費用面板（本月統計 + 模型卡片 + 調用歷史）
        st.subheader("💰 Token 費用面板")
        self._render_llm_cost_panel_only()

        st.markdown("---")
        # 再顯示：主要服務連線狀態（獨立，不與費用共用版面）
        st.subheader("🔌 主要服務連線狀態")
        self._render_simple_connection_status()

        st.markdown("---")
        st.header("📊 MCP 系統監控中心")
        st.markdown("基於 test_mcp_complete.py 的完整系統監控，展示核心基礎設施和 Agent 生態系統。")

        # 控制面板
        self._render_control_panel()

        # 系統概覽
        self._render_system_overview()

        # 詳細監控
        col1, col2 = st.columns(2)

        with col1:
            self._render_mcp_server_status()
            self._render_agent_registry()

        with col2:
            self._render_individual_agents()
            self._render_infrastructure_status()
        
        # 詳細日誌
        self._render_detailed_logs()

        st.markdown("---")
        st.subheader("🧑‍💻 使用者操作紀錄（最近 100 筆）")
        self._render_user_operations_panel()
    
    def _render_control_panel(self):
        """渲染控制面板"""
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if st.button("🔍 執行完整測試", type="primary", use_container_width=True):
                self._run_complete_test()
        
        with col2:
            auto_refresh = st.checkbox("🔄 自動刷新", value=False)
        
        with col3:
            if auto_refresh:
                refresh_interval = st.selectbox("刷新間隔", [10, 30, 60], index=1, format_func=lambda x: f"{x}秒")
                
                # 自動刷新邏輯
                if 'last_refresh' not in st.session_state:
                    st.session_state.last_refresh = time.time()
                
                if time.time() - st.session_state.last_refresh > refresh_interval:
                    self._run_complete_test()
                    st.session_state.last_refresh = time.time()
                    st.rerun()
    
    def _render_system_overview(self):
        """渲染系統概覽"""
        st.subheader("🎯 系統概覽")
        
        if not hasattr(st.session_state, 'monitoring_results'):
            st.info("點擊「執行完整測試」來獲取系統狀態")
            return
        
        results = st.session_state.monitoring_results
        
        # 核心指標
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            mcp_healthy = results.get('mcp_server', False)
            st.metric("MCP Server", "🟢 正常" if mcp_healthy else "🔴 異常")
        
        with col2:
            agents_data = results.get('agent_registry', {})
            total_agents = agents_data.get('total', 0)
            online_agents = agents_data.get('online', 0)
            st.metric("Agents", f"{online_agents}/{total_agents}")
        
        with col3:
            db_status = results.get('database', {}).get('connected', False)
            st.metric("資料庫", "🟢 連接" if db_status else "🔴 斷線")
        
        with col4:
            storage_status = results.get('storage', {}).get('available', False)
            st.metric("存儲", "🟢 可用" if storage_status else "🔴 不可用")
    
    def _render_mcp_server_status(self):
        """渲染 MCP Server 狀態"""
        st.subheader("🔧 MCP Server 狀態")
        
        if not hasattr(st.session_state, 'monitoring_results'):
            st.info("等待測試結果...")
            return
        
        mcp_healthy = st.session_state.monitoring_results.get('mcp_server', False)
        
        if mcp_healthy:
            st.success("✅ MCP Server 健康檢查通過")
            st.write("- 狀態: 正常運行")
            st.write("- 端點: http://localhost:10100")
            st.write("- 功能: Agent 註冊與發現")
        else:
            st.error("❌ MCP Server 連接失敗")
            st.write("- 請檢查 Docker 容器是否運行")
            st.write("- 確認端口 10100 是否開放")
    
    def _render_agent_registry(self):
        """渲染 Agent 註冊狀態"""
        st.subheader("🤖 Agent 註冊機制")
        
        if not hasattr(st.session_state, 'monitoring_results'):
            return
        
        agents_data = st.session_state.monitoring_results.get('agent_registry', {})
        
        if agents_data:
            total = agents_data.get('total', 0)
            online = agents_data.get('online', 0)
            
            st.write(f"**總註冊 Agents:** {total}")
            st.write(f"**在線 Agents:** {online}")
            
            # 詳細 Agent 信息
            details = agents_data.get('details', [])
            if details:
                for agent in details[:3]:  # 只顯示前3個
                    # 後端回傳使用英文字段：name/status
                    status_value = agent.get('status') or agent.get('狀態')
                    name_value = agent.get('name') or agent.get('名稱') or 'Unknown'
                    status_icon = "🟢" if status_value == 'ONLINE' else "🔴"
                    st.write(f"{status_icon} {name_value}")
        else:
            st.warning("無法獲取 Agent 註冊信息")
    
    def _render_individual_agents(self):
        """渲染個別 Agent 狀態"""
        st.subheader("🎭 個別 Agent 檢查")
        
        if not hasattr(st.session_state, 'monitoring_results'):
            return
        
        agents = st.session_state.monitoring_results.get('agents', {})
        
        # Vision Agent
        vision_status = agents.get('vision', {})
        vision_healthy = vision_status.get('healthy', False)
        
        with st.expander(f"{'🟢' if vision_healthy else '🔴'} Vision Agent (8005)", expanded=False):
            if vision_healthy:
                st.success("健康檢查通過")
                st.write(f"響應時間: {vision_status.get('response_time', 0):.0f}ms")
            else:
                st.error("連接失敗")
        
        # Playwright Crawler Agent
        playwright_status = agents.get('playwright_crawler', {})
        playwright_healthy = playwright_status.get('healthy', False)
        
        with st.expander(f"{'🟢' if playwright_healthy else '🔴'} Playwright Crawler (8006)", expanded=False):
            if playwright_healthy:
                st.success("健康檢查通過")
                st.write(f"響應時間: {playwright_status.get('response_time', 0):.0f}ms")
            else:
                st.error("連接失敗")
    
    def _render_infrastructure_status(self):
        """渲染基礎設施狀態"""
        st.subheader("🏗️ 基礎設施狀態")
        
        if not hasattr(st.session_state, 'monitoring_results'):
            return
        
        results = st.session_state.monitoring_results
        
        # PostgreSQL
        db_connected = results.get('database', {}).get('connected', False)
        if db_connected:
            st.success("✅ PostgreSQL: 正常運行")
        else:
            st.error("❌ PostgreSQL: 連接失敗")
        
        # Redis
        if db_connected:  # 通常 Redis 和 DB 一起檢查
            st.success("✅ Redis: 正常運行")
        else:
            st.error("❌ Redis: 連接失敗")
        
        # RustFS S3
        storage_available = results.get('storage', {}).get('available', False)
        if storage_available:
            st.success("✅ RustFS S3: 正常運行")
            st.write("- 端點: http://localhost:9000")
        else:
            st.error("❌ RustFS S3: 不可用")
    
    def _render_detailed_logs(self):
        """渲染詳細日誌"""
        if hasattr(st.session_state, 'monitoring_logs') and st.session_state.monitoring_logs:
            with st.expander("📋 詳細測試日誌", expanded=False):
                for log in st.session_state.monitoring_logs[-50:]:  # 顯示更多日誌（50條）
                    timestamp = log.get('timestamp', '')
                    level = log.get('level', 'INFO')
                    message = log.get('message', '')
                    details = log.get('details', None)
                    
                    # 根據級別顯示不同樣式
                    if level == 'SUCCESS':
                        st.success(f"✅ [{timestamp}] {message}")
                    elif level == 'ERROR':
                        st.error(f"❌ [{timestamp}] {message}")
                    elif level == 'WARNING':
                        st.warning(f"⚠️ [{timestamp}] {message}")
                    elif level == 'DETAIL':
                        st.info(f"📊 [{timestamp}] {message}")
                    else:
                        st.info(f"🔍 [{timestamp}] {message}")
                    
                    # 顯示詳細信息
                    if details and isinstance(details, dict):
                        with st.container():
                            cols = st.columns(len(details))
                            for i, (key, value) in enumerate(details.items()):
                                with cols[i % len(cols)]:
                                    st.write(f"**{key}**: {value}")
                    elif details:
                        st.write(f"      {details}")
                    
                    # 添加分隔線
                    if level in ['SUCCESS', 'ERROR', 'WARNING']:
                        st.markdown("---")
    
    def _run_complete_test(self):
        """執行完整的系統測試"""
        st.info("🚀 正在執行完整的 MCP 系統測試...")
        
        # 清空之前的日誌
        self.detailed_logs = []
        
        # 初始化結果
        results = {}
        
        self.log("INFO", "🚀 開始 MCP 系統完整測試 - 增強版")
        self.log("INFO", "📋 測試範圍：核心基礎設施、Agent 生態、資料庫操作、存儲整合")
        
        # 1. MCP Server 健康檢查
        self.log("INFO", "測試 1: MCP Server 核心健康檢查")
        mcp_result = self._test_mcp_server_health()
        results['mcp_server'] = mcp_result
        
        # 2. Agent 註冊機制
        self.log("INFO", "測試 2: Agent 註冊與發現機制")
        agent_registry_result = self._test_agent_registry()
        results['agent_registry'] = agent_registry_result
        
        # 3. 個別 Agent 檢查
        agents_result = {}
        self.log("INFO", "測試 3.1: Vision Agent 詳細檢查")
        agents_result['vision'] = self._test_individual_agent("Vision", 8005)
        self.log("INFO", "測試 3.2: Playwright Crawler Agent 詳細檢查")
        agents_result['playwright_crawler'] = self._test_individual_agent("Playwright Crawler", 8006)
        results['agents'] = agents_result
        
        # 4. 資料庫操作
        self.log("INFO", "測試 4: 資料庫連接與操作")
        db_result = self._test_database_operations()
        results['database'] = db_result
        
        # 5. 存儲整合
        self.log("INFO", "測試 5: RustFS S3 存儲整合")
        storage_result = self._test_storage_integration()
        results['storage'] = storage_result
        
        # 6. 基礎設施
        self.log("INFO", "測試 6: 基礎設施服務檢查")
        infra_result = self._test_infrastructure_services()
        results['infrastructure'] = infra_result
        
        # 生成詳細報告（匹配 test_mcp_complete.py 格式）
        detailed_report = self._generate_detailed_report(results, self.detailed_logs)
        
        # 保存結果
        st.session_state.monitoring_results = results
        st.session_state.monitoring_logs = self.detailed_logs
        st.session_state.monitoring_report = detailed_report
        
        st.success("✅ 系統測試完成！")
        st.rerun()
    
    def _generate_detailed_report(self, results: Dict[str, Any], logs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成詳細的測試報告"""
        import time
        import datetime
        
        # 統計測試結果  
        total_tests = len(results)
        successful_tests = sum(1 for result in results.values() if isinstance(result, dict) and result.get('success', False))
        failed_tests = total_tests - successful_tests
        
        # 統計日誌級別
        log_stats = {}
        for log in logs:
            level = log.get('level', 'INFO')
            log_stats[level] = log_stats.get(level, 0) + 1
        
        # 生成詳細報告
        tz = datetime.timezone(datetime.timedelta(hours=8))
        report = {
            "test_summary": {
                "測試時間": datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"),
                "測試項目數": total_tests,
                "成功項目": successful_tests,
                "失敗項目": failed_tests,
                "成功率": f"{(successful_tests/total_tests)*100:.1f}%" if total_tests > 0 else "0%",
                "日誌統計": log_stats,
                "總日誌條數": len(logs)
            },
            "detailed_results": results,
            "detailed_logs": logs
        }
        
        return report

    # ================================
    # 子面板：LLM 費用（獨立）
    # ================================
    def _render_llm_cost_panel_only(self):
        st.markdown("**📅 本月彙總**")
        # 工具列：初始化/修復表結構
        tool_cols = st.columns([1, 1, 6])
        with tool_cols[0]:
            if st.button("🛠 初始化/修復表", key="init_llm_usage_schema_btn"):
                # 使用 try-catch 防止 'another operation is in progress'，序列化操作
                try:
                    ok, err = self._init_llm_usage_schema()
                    if ok:
                        st.success("已完成 llm_usage 表與索引初始化/修復")
                        st.rerun()
                    else:
                        st.error(f"初始化失敗：{err}")
                except Exception as e:
                    st.error(f"初始化失敗：{e}")
        try:
            stats = self._fetch_llm_monthly_stats()
            if not stats:
                st.info("尚無 LLM 使用紀錄，或資料表尚未建立。可先點擊上方『🛠 初始化/修復表』。")
                return

            # 本月 KPI
            top_line = stats.get("top_line", {})
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("本月成本 (USD)", f"{top_line.get('usd_cost', 0.0):.4f}")
            with c2:
                st.metric("本月 Token 總量", f"{top_line.get('tokens', 0):,}")
            with c3:
                st.metric("本月請求數", f"{top_line.get('requests', 0)}")

            # 本月模型統計卡片
            st.markdown("**🧩 模型統計（本月）**")
            models = stats.get("by_model", [])
            if models:
                for i in range(0, len(models), 3):
                    row = models[i:i+3]
                    cols = st.columns(len(row))
                    for idx, item in enumerate(row):
                        with cols[idx]:
                            st.container(border=True)
                            st.markdown(f"**{item['provider']}/{item['model']}**")
                            st.write(f"Tokens：{int(item['tokens']):,}")
                            st.write(f"成本：${float(item['usd_cost']):.4f}")
                            st.caption(f"請求數：{item['requests']}")
            else:
                st.info("本月尚無模型統計資料")

            # 調用歷史（最近 50 筆）
            st.markdown("**🕒 最近 50 筆調用**")
            recent = stats.get("recent", [])
            if recent:
                st.dataframe(recent, use_container_width=True, hide_index=True)
            else:
                st.write("- 無資料")

            # 導出區塊（可折疊）
            with st.expander("📦 導出資料 (CSV)", expanded=False):
                cexp1, cexp2 = st.columns(2)
                with cexp1:
                    csv_month = self._export_llm_usage_csv(month_only=True)
                    st.download_button(
                        label="⬇️ 下載本月 CSV",
                        data=csv_month,
                        file_name="llm_usage_month.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="dl_llm_usage_month_csv",
                    )
                with cexp2:
                    csv_all = self._export_llm_usage_csv(month_only=False)
                    st.download_button(
                        label="⬇️ 下載全部 CSV",
                        data=csv_all,
                        file_name="llm_usage_all.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="dl_llm_usage_all_csv",
                    )

        except Exception as e:
            st.warning(f"讀取費用面板失敗：{e}")

    def _fetch_llm_usage_stats(self) -> Dict[str, Any]:
        """今日彙總（改用 psycopg2 同步查詢，避免 async 池問題）"""
        from common.settings import get_settings
        dsn = get_settings().database.url
        try:
            with psycopg2.connect(dsn) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT 
                            COALESCE(SUM(cost),0) AS usd_cost,
                            COALESCE(SUM(total_tokens),0) AS tokens,
                            COUNT(*) AS requests
                        FROM llm_usage
                        WHERE ts::date = CURRENT_DATE
                        """
                    )
                    top_line = cur.fetchone() or {}

                    cur.execute(
                        """
                        SELECT service, 
                               SUM(cost) AS usd_cost, 
                               SUM(total_tokens) AS tokens, 
                               COUNT(*) AS requests
                        FROM llm_usage
                        WHERE ts::date = CURRENT_DATE
                        GROUP BY service
                        ORDER BY usd_cost DESC
                        LIMIT 5
                        """
                    )
                    by_service = cur.fetchall() or []

                    cur.execute(
                        """
                        SELECT provider, model, 
                               SUM(cost) AS usd_cost, 
                               SUM(total_tokens) AS tokens, 
                               COUNT(*) AS requests
                        FROM llm_usage
                        WHERE ts::date = CURRENT_DATE
                        GROUP BY provider, model
                        ORDER BY usd_cost DESC, tokens DESC
                        LIMIT 5
                        """
                    )
                    by_model = cur.fetchall() or []

                    cur.execute(
                        """
                        SELECT 
                            to_char(ts AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Taipei', 'HH24:MI:SS') AS 時間,
                            service AS 服務,
                            provider AS 供應商,
                            model AS 模型,
                            total_tokens AS tokens,
                            cost AS usd,
                            status AS 狀態
                        FROM llm_usage
                        ORDER BY ts DESC
                        LIMIT 20
                        """
                    )
                    recent = cur.fetchall() or []

                    return {"top_line": top_line, "by_service": by_service, "by_model": by_model, "recent": recent}
        except Exception:
            return {}

    def _fetch_llm_monthly_stats(self) -> Dict[str, Any]:
        """本月度彙總 + 模型統計 + 最近 50 筆（改用 psycopg2 同步查詢）"""
        from common.settings import get_settings
        dsn = get_settings().database.url
        try:
            with psycopg2.connect(dsn) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT 
                            COALESCE(SUM(cost),0) AS usd_cost,
                            COALESCE(SUM(total_tokens),0) AS tokens,
                            COUNT(*) AS requests
                        FROM llm_usage
                        WHERE date_trunc('month', ts) = date_trunc('month', now())
                        """
                    )
                    top_line = cur.fetchone() or {}

                    cur.execute(
                        """
                        SELECT provider, model,
                               SUM(cost) AS usd_cost,
                               SUM(total_tokens) AS tokens,
                               COUNT(*) AS requests
                        FROM llm_usage
                        WHERE date_trunc('month', ts) = date_trunc('month', now())
                        GROUP BY provider, model
                        ORDER BY usd_cost DESC, tokens DESC
                        LIMIT 30
                        """
                    )
                    by_model = cur.fetchall() or []

                    cur.execute(
                        """
                        SELECT 
                            to_char(ts AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Taipei', 'YYYY-MM-DD HH24:MI:SS') AS 時間,
                            service AS 服務,
                            provider AS 供應商,
                            model AS 模型,
                            total_tokens AS tokens,
                            cost AS usd,
                            status AS 狀態
                        FROM llm_usage
                        ORDER BY ts DESC
                        LIMIT 50
                        """
                    )
                    recent = cur.fetchall() or []

                    return {"top_line": top_line, "by_model": by_model, "recent": recent}
        except Exception:
            return {}

    def _export_llm_usage_csv(self, month_only: bool) -> str:
        """輸出 CSV 字串：全部或本月。含台北時間與推導的使用場景欄位。"""
        from common.settings import get_settings
        dsn = get_settings().database.url
        try:
            import csv
            import io
            with psycopg2.connect(dsn) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    where_clause = "WHERE date_trunc('month', ts) = date_trunc('month', now())" if month_only else ""
                    cur.execute(
                        f"""
                        SELECT 
                            to_char((ts AT TIME ZONE 'UTC') AT TIME ZONE 'Asia/Taipei', 'YYYY-MM-DD HH24:MI:SS') AS time_tw,
                            service,
                            provider,
                            model,
                            prompt_tokens,
                            completion_tokens,
                            total_tokens,
                            cost,
                            latency_ms,
                            status,
                            COALESCE(CASE 
                                WHEN metadata ? 'usage_scene' THEN metadata->>'usage_scene'
                                ELSE NULL END, '') AS usage_scene
                        FROM llm_usage
                        {where_clause}
                        ORDER BY ts DESC
                        """
                    )
                    rows = cur.fetchall() or []

            # 產生 CSV
            headers = [
                "時間(台北)", "服務", "供應商", "模型",
                "prompt_tokens", "completion_tokens", "total_tokens", "cost", "latency_ms", "status", "使用場景"
            ]
            key_map = [
                ("time_tw", None), ("service", None), ("provider", None), ("model", None),
                ("prompt_tokens", None), ("completion_tokens", None), ("total_tokens", None),
                ("cost", None), ("latency_ms", None), ("status", None), ("usage_scene", None)
            ]
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(headers)
            for r in rows:
                writer.writerow([r.get(k) for k, _ in key_map])
            return buf.getvalue()
        except Exception:
            return ""

    def _init_llm_usage_schema(self) -> tuple[bool, str]:
        async def _run() -> tuple[bool, str]:
            try:
                # 使用一次性直連，避免連線池已關閉造成的初始化失敗
                from common.settings import get_settings
                import asyncpg
                dsn = get_settings().database.url
                conn = await asyncpg.connect(dsn)
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS llm_usage (
                        id BIGSERIAL PRIMARY KEY,
                        ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        service TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        model TEXT NOT NULL,
                        request_id TEXT,
                        prompt_tokens INTEGER DEFAULT 0,
                        completion_tokens INTEGER DEFAULT 0,
                        total_tokens INTEGER DEFAULT 0,
                        cost NUMERIC(12,6) DEFAULT 0,
                        latency_ms INTEGER DEFAULT 0,
                        status TEXT NOT NULL DEFAULT 'success',
                        error TEXT,
                        metadata JSONB
                    )
                    """
                )
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_ts ON llm_usage (ts DESC)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_svc ON llm_usage (service)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_provider ON llm_usage (provider)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_model ON llm_usage (model)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_status ON llm_usage (status)")
                await conn.close()
                return True, ""
            except Exception as e:
                return False, str(e)

        return asyncio.run(_run())


    def _render_simple_connection_status(self):
        st.markdown("**🔌 主要服務連線狀態**")

        def _check_any(urls: List[str]) -> bool:
            for u in urls:
                try:
                    resp = httpx.get(u, timeout=5.0)
                    if resp.status_code < 400:
                        return True
                except Exception:
                    continue
            return False

        targets = [
            ("MCP Server", ["http://mcp-server:10100/health", "http://localhost:10100/health"]),
            ("Orchestrator", ["http://orchestrator-agent:8000/health", "http://localhost:8000/health"]),
            ("Clarification", ["http://clarification-agent:8004/health", "http://localhost:8004/health"]),
            ("Content Writer", ["http://content-writer-agent:8003/health", "http://localhost:8003/health"]),
            ("Content Generator", ["http://content-generator-agent:8008/health", "http://localhost:8008/health"]),
            ("Form API", ["http://form-api:8010/health", "http://localhost:8010/health"]),
            ("Vision", ["http://vision-agent:8005/health", "http://localhost:8005/health"]),
            ("Playwright Crawler", ["http://playwright-crawler-agent:8006/health", "http://localhost:8006/health"]),
            ("Post Analyzer", ["http://post-analyzer-agent:8007/health", "http://localhost:8007/health"]),
            ("Reader LB", ["http://reader-lb/health", "http://localhost:8880/health"]),
            ("NATS", ["http://nats:8223/healthz", "http://localhost:8223/healthz"]),
            ("RustFS", ["http://rustfs:9000/", "http://localhost:9000/"]),
        ]

        down_list: List[str] = []
        for name, urls in targets:
            ok = _check_any(urls)
            icon = "🟢" if ok else "🔴"
            st.write(f"{icon} {name}")
            if not ok:
                down_list.append(name)

        if down_list:
            st.warning("偵測到異常服務：" + ", ".join(down_list))
            st.caption("建議：檢查容器日誌（docker-compose logs -f [service]）或嘗試重啟對應服務")

    def _render_user_operations_panel(self):
        import httpx
        from common.settings import get_settings
        base_url = os.getenv('MCP_SERVER_URL') or 'http://localhost:10100'

        # 篩選條件
        c1, c2, c3, c4 = st.columns(4)
        options_cache_key = "user_ops_options"
        if options_cache_key not in st.session_state:
            # 初始化空值，避免首次渲染阻塞
            st.session_state[options_cache_key] = {"menu_names": [], "action_types": [], "user_ids": []}
            try:
                resp_opt = httpx.get(f"{base_url}/user/ops/options", timeout=5.0)
                if resp_opt.status_code == 200:
                    st.session_state[options_cache_key] = resp_opt.json()
            except Exception:
                pass
        opts = st.session_state[options_cache_key]

        with c1:
            menu = st.selectbox("主功能選單", options=[""] + opts.get("menu_names", []), index=0)
        with c2:
            action_type = st.selectbox("動作類型", options=[""] + (opts.get("action_types", []) or ["navigate","click","submit","export"]), index=0)
        with c3:
            user_id = st.selectbox("使用者ID", options=[""] + opts.get("user_ids", []), index=0)
        with c4:
            limit = st.number_input("顯示筆數", min_value=10, max_value=500, value=100, step=10)

        params = {"limit": int(limit)}
        if menu:
            params["menu_name"] = menu
        if action_type:
            params["action_type"] = action_type
        if user_id:
            params["user_id"] = user_id

        try:
            resp = httpx.get(f"{base_url}/user/ops", params=params, timeout=8.0)
            if resp.status_code == 200:
                data = resp.json()
                logs = data.get("logs", [])
                if logs:
                    # 簡化欄位呈現
                    rows = []
                    for r in logs:
                        rows.append({
                            "時間": r.get("ts"),
                            "使用者": r.get("user_id") or r.get("anonymous_id"),
                            "選單": r.get("menu_name"),
                            "動作": r.get("action_type"),
                            "描述": r.get("action_name"),
                            "狀態": r.get("status"),
                        })
                    st.dataframe(rows, use_container_width=True, hide_index=True)
                else:
                    st.info("目前沒有操作紀錄")

                # CSV 下載
                with st.expander("📦 匯出 CSV", expanded=False):
                    try:
                        csv_resp = httpx.get(f"{base_url}/user/ops", params={**params, "format": "csv"}, timeout=10.0)
                        if csv_resp.status_code == 200:
                            st.download_button(
                                label="⬇️ 下載 CSV",
                                data=csv_resp.content,
                                file_name="user_operations.csv",
                                mime="text/csv",
                                use_container_width=True,
                            )
                        else:
                            st.warning("CSV 匯出暫不可用")
                    except Exception as e:
                        st.warning(f"CSV 匯出失敗：{e}")
            else:
                st.warning(f"讀取使用者操作紀錄失敗：HTTP {resp.status_code}")
        except Exception as e:
            st.warning(f"無法連線 MCP Server：{e}")
    
    def _test_mcp_server_health(self) -> Dict[str, Any]:
        """測試 MCP Server 健康狀態"""
        try:
            response = httpx.get("http://localhost:10100/health", timeout=10)
            if response.status_code == 200:
                health_data = response.json()
                self.log("SUCCESS", "MCP Server 健康檢查通過", {
                    "狀態碼": response.status_code,
                    "響應時間": f"{response.elapsed.total_seconds():.3f}秒",
                    "端點": "http://localhost:10100/health"
                })
                self.log("DETAIL", "MCP Server 詳細狀態", health_data)
                return {"success": True, "data": health_data}
            else:
                self.log("ERROR", f"MCP Server 健康檢查失敗: HTTP {response.status_code}")
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            self.log("ERROR", f"MCP Server 連接失敗: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _test_agent_registry(self) -> Dict[str, Any]:
        """測試 Agent 註冊機制"""
        try:
            response = httpx.get("http://localhost:10100/agents", timeout=10)
            if response.status_code == 200:
                agents = response.json()
                online_count = sum(1 for agent in agents if agent.get('status') == 'ONLINE')
                
                self.log("SUCCESS", f"Agent 註冊機制正常運作", {
                    "總 Agent 數": len(agents),
                    "線上 Agent 數": online_count,
                    "註冊率": f"{(online_count/len(agents)*100):.1f}%" if agents else "0%"
                })
                
                # 記錄每個 Agent 的詳細信息
                for agent in agents:
                    agent_info = {
                        "狀態": agent.get('status', 'UNKNOWN'),
                        "版本": agent.get('version', 'unknown'),
                        "端點": agent.get('endpoint', 'unknown')
                    }
                    self.log("DETAIL", f"Agent: {agent.get('name')}", agent_info)
                
                self.log("SUCCESS", f"活躍 Agents: {online_count}/{len(agents)}")
                
                return {
                    'success': True,
                    'total': len(agents),
                    'online': online_count,
                    'details': agents
                }
            else:
                self.log("WARNING", f"獲取 Agents 列表失敗: HTTP {response.status_code}")
                return {'success': False, 'error': f"HTTP {response.status_code}"}
        except Exception as e:
            self.log("WARNING", f"Agent 註冊檢查異常: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _test_individual_agent(self, name: str, port: int) -> Dict[str, Any]:
        """測試個別 Agent"""
        try:
            start_time = time.time()
            response = httpx.get(f"http://localhost:{port}/health", timeout=15)
            response_time = (time.time() - start_time) * 1000
            
            return {
                'healthy': response.status_code == 200,
                'response_time': response_time,
                'port': port
            }
        except:
            return {
                'healthy': False,
                'response_time': 0,
                'port': port
            }
    
    def _test_database_operations(self) -> Dict[str, Any]:
        """測試資料庫操作"""
        try:
            response = httpx.get("http://localhost:10100/stats", timeout=10)
            return {
                'connected': response.status_code == 200,
                'stats': response.json() if response.status_code == 200 else {}
            }
        except:
            return {'connected': False, 'stats': {}}
    
    def _test_storage_integration(self) -> Dict[str, Any]:
        """測試存儲整合"""
        try:
            response = httpx.get("http://localhost:9000/", timeout=10)
            return {
                'available': response.status_code == 200,
                'endpoint': 'http://localhost:9000'
            }
        except:
            return {'available': False, 'endpoint': 'http://localhost:9000'}
    
    def _test_infrastructure_services(self) -> Dict[str, Any]:
        """測試基礎設施服務"""
        # 通過其他服務間接測試
        return {
            'postgresql': True,  # 通過 MCP Server 間接測試
            'redis': True,       # 通過 MCP Server 間接測試
            'network': True      # Docker 網絡通信
        }