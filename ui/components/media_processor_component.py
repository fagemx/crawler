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
                st.subheader("📊 下載現況（帳號彙總）")
                # 重新整理按鈕：強制重載統計
                refresh_col = st.columns([1, 9])[0]
                with refresh_col:
                    if st.button("🔄 重新整理", key="refresh_media_stats"):
                        try:
                            st.rerun()
                        except Exception:
                            # 舊版 Streamlit 相容
                            st.experimental_rerun()
                df = pd.DataFrame(stats)
                # 轉中文欄位名稱並調整欄位順序
                col_order = [
                    "username",
                    "total_images", "total_videos",
                    "paired_images", "paired_videos",
                    "completed_images", "completed_videos",
                    "pending_images", "pending_videos",
                ]
                df = df[[c for c in col_order if c in df.columns]]
                df = df.rename(columns={
                    "username": "使用者",
                    "total_images": "總圖片",
                    "total_videos": "總影片",
                    "paired_images": "已配對圖片",
                    "paired_videos": "已配對影片",
                    "completed_images": "已下載圖片",
                    "completed_videos": "已下載影片",
                    "pending_images": "待下載圖片",
                    "pending_videos": "待下載影片",
                })
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

        # 下載目標：全部 / 僅重試失敗
        retry_failed_only = st.checkbox("只重試失敗", value=False, help="僅針對 media_files.download_status='failed' 的項目重新下載")
        
        # 🆕 新增：查看失敗記錄
        st.markdown("---")
        st.subheader("🔍 失敗記錄查詢")
        col_f1, col_f2 = st.columns([2, 1])
        with col_f1:
            failed_username = st.text_input("查詢失敗記錄的帳號", value=target_username, key="failed_lookup_user")
        with col_f2:
            if st.button("🔍 查看失敗記錄", key="view_failed"):
                try:
                    from common.db_client import get_db_client
                    import asyncio, nest_asyncio
                    nest_asyncio.apply()
                    db = asyncio.get_event_loop().run_until_complete(get_db_client())
                    
                    # 查詢失敗的下載記錄
                    failed_records = asyncio.get_event_loop().run_until_complete(db.fetch_all("""
                        SELECT DISTINCT mf.post_url, COUNT(*) as failed_count,
                               STRING_AGG(DISTINCT mf.media_type, ', ') as media_types,
                               STRING_AGG(DISTINCT SUBSTRING(mf.download_error FROM 1 FOR 50), '; ') as errors
                        FROM media_files mf 
                        JOIN playwright_post_metrics ppm ON ppm.url = mf.post_url
                        WHERE ppm.username = $1 AND mf.download_status = 'failed'
                        GROUP BY mf.post_url
                        ORDER BY failed_count DESC
                        LIMIT 20
                    """, failed_username))
                    
                    if failed_records:
                        st.write(f"🚨 找到 {len(failed_records)} 個有失敗記錄的貼文：")
                        for record in failed_records:
                            with st.expander(f"貼文：{record['post_url'][-20:]}... (失敗 {record['failed_count']} 個媒體)", expanded=False):
                                st.text(f"📄 完整URL：{record['post_url']}")
                                st.text(f"🎬 失敗媒體類型：{record['media_types']}")
                                st.text(f"❌ 錯誤摘要：{record['errors']}")
                                col_action1, col_action2 = st.columns(2)
                                with col_action1:
                                    if st.button("📋 複製URL", key=f"copy_failed_{hash(record['post_url'])}"):
                                        st.code(record['post_url'])
                                with col_action2:
                                    if st.button("🔄 立即重試", key=f"retry_failed_{hash(record['post_url'])}"):
                                        # 觸發該貼文的重新下載
                                        try:
                                            from agents.vision.media_download_service import MediaDownloadService
                                            svc = MediaDownloadService()
                                            # 只下載失敗的媒體
                                            plan = asyncio.get_event_loop().run_until_complete(svc.build_download_plan(
                                                username=failed_username,
                                                media_types=["image", "video"],
                                                retry_failed_only=True
                                            ))
                                            # 過濾出這個貼文的失敗項目
                                            post_plan = {k: v for k, v in plan.items() if k == record['post_url']}
                                            if post_plan:
                                                result = asyncio.get_event_loop().run_until_complete(svc.run_download(post_plan))
                                                st.success(f"重試完成：成功 {result['success']}，失敗 {result['failed']}")
                                            else:
                                                st.info("該貼文沒有需要重試的項目")
                                        except Exception as e:
                                            st.error(f"重試失敗：{e}")
                    else:
                        st.info(f"🎉 帳號 @{failed_username} 沒有失敗的下載記錄")
                        
                except Exception as e:
                    st.error(f"查詢失敗記錄時出錯：{e}")

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
                    retry_failed_only=retry_failed_only,
                ))
                if not plan:
                    st.info("沒有需要下載的媒體")
                    return
                # 服務內含 403 → 自動刷新後重試
                result = asyncio.get_event_loop().run_until_complete(svc.run_download(plan, concurrency_per_post=int(concurrency)))
                st.success(f"下載完成：成功 {result['success']}，失敗 {result['failed']} / 共 {result['total']}")
            except Exception as e:
                st.error(f"下載執行失敗：{e}")

        # 進階：單篇刷新/下載（折疊，不常用）
        st.markdown("---")
        with st.expander("進階：單篇重爬 / 刷新媒體 URL", expanded=False):
            st.caption("建議僅在批次下載遇到 403/過期時使用。")
            colr1, colr2, colr3 = st.columns([3, 1, 1])
            with colr1:
                single_post_url = st.text_input("貼文 URL（https://www.threads.net/@user/post/XXXX）", key="single_post_url")
            with colr2:
                do_refresh = st.button("🔄 單篇刷新URL", key="btn_refresh_single")
            with colr3:
                do_refresh_and_download = st.button("⬇️ 刷新並下載", key="btn_refresh_and_download")

            if do_refresh and single_post_url:
                try:
                    from agents.vision.media_download_service import MediaDownloadService
                    import nest_asyncio
                    import asyncio
                    nest_asyncio.apply()
                    svc = MediaDownloadService()
                    refreshed = asyncio.get_event_loop().run_until_complete(svc.refresh_post_media_urls(single_post_url))
                    imgs = len(refreshed.get("images") or [])
                    vids = len(refreshed.get("videos") or [])
                    st.success(f"已刷新：images={imgs}, videos={vids}")
                except Exception as e:
                    st.error(f"刷新失敗：{e}")

            if do_refresh_and_download and single_post_url:
                try:
                    from agents.vision.media_download_service import MediaDownloadService
                    import nest_asyncio
                    import asyncio
                    nest_asyncio.apply()
                    svc = MediaDownloadService()
                    
                    # Step 1: 刷新貼文數據
                    with st.spinner("🔄 正在刷新貼文數據..."):
                        refreshed = asyncio.get_event_loop().run_until_complete(svc.refresh_post_media_urls(single_post_url))
                        imgs = refreshed.get("images") or []
                        vids = refreshed.get("videos") or []
                        urls = imgs + vids
                        st.info(f"📊 刷新完成：圖片 {len(imgs)} 個，影片 {len(vids)} 個")
                    
                    if not urls:
                        st.warning("⚠️ 刷新後未獲得媒體 URL，可能該貼文無媒體或頁面結構已變")
                    else:
                        # Step 2: 下載媒體
                        with st.spinner("⬇️ 正在下載媒體檔案..."):
                            plan = {single_post_url: urls}
                            result = asyncio.get_event_loop().run_until_complete(svc.run_download(plan, concurrency_per_post=3))
                            st.success(f"✅ 下載完成：成功 {result['success']}，失敗 {result['failed']} / 共 {result['total']}")
                            
                            # 顯示失敗詳情
                            if result['failed'] > 0:
                                failed_details = [d for d in result['details'] if d.get('status') == 'failed']
                                if failed_details:
                                    with st.expander("❌ 失敗詳情", expanded=False):
                                        for detail in failed_details[:5]:  # 只顯示前5個
                                            st.text(f"📄 貼文: {detail.get('post_url', 'N/A')}")
                                            st.text(f"🎬 媒體: {detail.get('original_url', 'N/A')}")
                                            st.text(f"❌ 錯誤: {detail.get('error', 'N/A')}")
                                            if detail.get('post_url'):
                                                copy_url = detail['post_url']
                                                if st.button(f"📋 複製貼文URL", key=f"copy_{hash(copy_url)}", help="複製此貼文URL用於單篇重試"):
                                                    st.code(copy_url)
                                            st.markdown("---")
                                            
                except Exception as e:
                    import traceback
                    error_detail = traceback.format_exc()
                    st.error(f"🚨 刷新並下載失敗：{str(e)}")
                    with st.expander("🔍 詳細錯誤訊息", expanded=False):
                        st.code(error_detail, language="python")

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


