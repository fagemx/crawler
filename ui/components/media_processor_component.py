import streamlit as st
from typing import List, Dict


class MediaProcessorComponent:
    """媒體處理器 - 兩個子分頁：下載(RustFS) / 描述(Gemini)"""

    def render(self):
        st.header("👁️ 媒體處理器")
        tabs = st.tabs(["📥 媒體下載器（RustFS）", "🧠 媒體描述器（Gemini 2.5 Pro）"])

        with tabs[0]:
            self._render_downloader()

        with tabs[1]:
            self._render_describer()

    # ---------- 下載器 ----------
    def _render_downloader(self):
        st.subheader("📥 媒體下載器（RustFS）")
        # 健檢
        try:
            from services.rustfs_client import get_rustfs_client
            import asyncio
            client = asyncio.run(get_rustfs_client())
            health = client.health_check()
            if health.get("status") == "healthy":
                st.success(f"RustFS 連線正常：{health.get('endpoint')} | bucket={health.get('bucket')}")
            else:
                st.warning(f"RustFS 可能不可用：{health}")
        except Exception as e:
            st.error(f"RustFS 健檢失敗：{e}")

        st.markdown("---")

        # 帳號統計（摘要）
        try:
            from agents.vision.media_download_service import MediaDownloadService
            import nest_asyncio
            import asyncio
            nest_asyncio.apply()
            svc = MediaDownloadService()
            stats = asyncio.get_event_loop().run_until_complete(svc.get_account_media_stats(limit=50))
            if stats:
                import pandas as pd
                df = pd.DataFrame(stats)
                st.dataframe(df, use_container_width=True, height=min(400, 38 + len(df) * 32))
            else:
                st.info("尚無統計資料")
        except Exception as e:
            st.warning(f"統計載入失敗：{e}")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            target_username = st.text_input("帳號", value="natgeo")
        with col2:
            media_types = st.multiselect("媒體類型", ["image", "video"], default=["image", "video"])
        with col3:
            sort_by = st.selectbox("排序欄位", ["none", "views", "likes", "comments", "reposts"], index=1)
        with col4:
            top_k = st.selectbox("Top-N", ["全部", 10, 25, 50], index=2)

        col5, col6, col7 = st.columns(3)
        with col5:
            concurrency = st.selectbox("並發數", [3, 5, 10], index=0)
        with col6:
            skip_completed = st.checkbox("跳過已完成", value=True)
        with col7:
            only_unpaired = st.checkbox("僅未配對", value=False, help="無 media_files 記錄才視為未配對")

        if st.button("開始下載", type="primary"):
            try:
                from agents.vision.media_download_service import MediaDownloadService
                import nest_asyncio
                import asyncio
                nest_asyncio.apply()
                svc = MediaDownloadService()
                plan = asyncio.get_event_loop().run_until_complete(svc.build_download_plan(
                    username=target_username,
                    media_types=media_types,
                    sort_by=sort_by,
                    top_k=None if top_k == "全部" else int(top_k),
                    skip_completed=skip_completed,
                    only_unpaired=only_unpaired,
                ))
                if not plan:
                    st.info("沒有需要下載的媒體")
                    return
                result = asyncio.get_event_loop().run_until_complete(svc.run_download(plan, concurrency_per_post=int(concurrency)))
                st.success(f"下載完成：成功 {result['success']}，失敗 {result['failed']} / 共 {result['total']}")
            except Exception as e:
                st.error(f"下載執行失敗：{e}")

    # ---------- 描述器 ----------
    def _render_describer(self):
        st.subheader("🧠 媒體描述器（Gemini 2.5 Pro）")
        # Gemini 健檢（只檢查 API key 存在）
        import os
        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            st.success("Gemini API Key 已配置")
        else:
            st.error("缺少 GEMINI_API_KEY/GOOGLE_API_KEY")

        st.markdown("---")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            target_username = st.text_input("帳號", value="natgeo", key="desc_user")
        with col2:
            media_types = st.multiselect("媒體類型", ["image", "video"], default=["image"], key="desc_types")
        with col3:
            sort_by = st.selectbox("排序欄位", ["none", "views", "likes", "comments", "reposts"], index=0, key="desc_sort")
        with col4:
            top_k = st.selectbox("Top-N", ["全部", 10, 25, 50], index=0, key="desc_topk")

        col5, col6 = st.columns(2)
        with col5:
            overwrite = st.checkbox("重新描述（覆蓋舊的）", value=True)
        with col6:
            concurrency = st.selectbox("並發數", [1, 2, 3], index=1, key="desc_ccy")

        if st.button("開始描述", type="primary", key="start_desc"):
            try:
                from agents.vision.media_describe_service import MediaDescribeService
                import nest_asyncio
                import asyncio
                nest_asyncio.apply()
                svc = MediaDescribeService()
                items = asyncio.get_event_loop().run_until_complete(svc.build_describe_plan(
                    username=target_username,
                    media_types=media_types,
                    sort_by=sort_by,
                    top_k=None if top_k == "全部" else int(top_k),
                    only_undesc=True
                ))
                if not items:
                    st.info("沒有待描述的媒體")
                    return
                result = asyncio.get_event_loop().run_until_complete(svc.run_describe(items, overwrite=True))
                st.success(f"描述完成：成功 {result['success']}，失敗 {result['failed']} / 共 {result['total']}")
            except Exception as e:
                st.error(f"描述執行失敗：{e}")


