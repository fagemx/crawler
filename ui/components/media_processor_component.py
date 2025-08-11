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
        
        # 清理自動刷新標記（避免無限循環）
        if 'refresh_stats_after_download' in st.session_state:
            del st.session_state.refresh_stats_after_download
            
        # 健檢
        try:
            from services.rustfs_client import RustFSClient
            client = RustFSClient()
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
            concurrency = st.selectbox("並發數", [1], index=0)
        with col6:
            skip_completed = st.checkbox("跳過已完成", value=True)
        with col7:
            only_unpaired = st.checkbox("僅未配對", value=False, help="無 media_files 記錄才視為未配對")

        # 下載目標：全部 / 僅重試失敗
        retry_failed_only = st.checkbox("只重試失敗", value=False, help="僅針對 media_files.download_status='failed' 的項目重新下載")

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
                with st.spinner("正在下載媒體檔案..."):
                    result = asyncio.get_event_loop().run_until_complete(svc.run_download(plan, concurrency_per_post=min(2, int(concurrency))))
                
                # 顯示詳細結果
                st.success(f"下載完成：成功 {result['success']}，失敗 {result['failed']} / 共 {result['total']}")
                
                # 檢查是否有自動重新爬取
                retry_after_refresh = [d for d in result.get('details', []) if d.get('retry_after_refresh')]
                if retry_after_refresh:
                    st.info(f"🔄 自動重新爬取: {len(retry_after_refresh)} 個項目通過重新爬取成功下載")
            except Exception as e:
                st.error(f"下載執行失敗：{e}")

        # 進階：單篇刷新/下載（折疊，不常用）
        st.markdown("---")
        with st.expander("進階：單篇重爬 / 刷新媒體 URL", expanded=False):
            st.caption("建議僅在批次下載遇到 403/過期時使用。")
            
            # 🆕 失敗記錄查詢（放在這裡更符合邏輯）
            st.subheader("🔍 查看失敗記錄")
            st.caption("找出需要重試的失敗貼文，獲取具體的貼文URL")
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
                                            # 顯示可選中複製的URL
                                            st.text_input("貼文URL（可選中複製）", value=record['post_url'], key=f"copyable_url_{hash(record['post_url'])}")
                                            st.info("✅ URL已顯示在上方文字框中，請選中並複製 (Ctrl+A, Ctrl+C)")
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
            
            # 分隔線
            st.markdown("---")
            
            # 單篇刷新功能
            st.subheader("🔄 單篇刷新")
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
                    
                    with st.spinner("🔄 正在刷新URL..."):
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
                            result = asyncio.get_event_loop().run_until_complete(svc.run_download(plan, concurrency_per_post=1))
                            st.success(f"✅ 下載完成：成功 {result['success']}，失敗 {result['failed']} / 共 {result['total']}")
                            
                            # 🆕 如果有成功下載，自動重新整理頁面以更新統計
                            if result['success'] > 0:
                                st.info("🔄 下載成功！正在重新整理統計資料...")
                                # 使用session state觸發刷新，避免無限循環
                                if 'refresh_stats_after_download' not in st.session_state:
                                    st.session_state.refresh_stats_after_download = True
                                    st.rerun()
                            
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
                                                    st.text_input("貼文URL（可選中複製）", value=copy_url, key=f"copyable_detail_url_{hash(copy_url)}")
                                                    st.info("✅ URL已顯示在上方文字框中，請選中並複製 (Ctrl+A, Ctrl+C)")
                                            st.markdown("---")
                                            
                except Exception as e:
                    import traceback
                    error_detail = traceback.format_exc()
                    st.error(f"🚨 刷新並下載失敗：{str(e)}")
                    with st.expander("🔍 詳細錯誤訊息", expanded=False):
                        st.code(error_detail, language="python")

        # 介面：單篇媒體瀏覽（輸入貼文 URL 預覽）
        st.markdown("---")
        with st.expander("📂 單篇媒體瀏覽（輸入貼文 URL 預覽）", expanded=False):
            view_post_url = st.text_input("貼文 URL（https://www.threads.net/@user/post/XXXX）", key="view_post_url_media")
            if st.button("載入媒體", key="btn_view_media") and view_post_url:
                try:
                    from common.db_client import get_db_client
                    from services.rustfs_client import RustFSClient
                    import nest_asyncio, asyncio
                    nest_asyncio.apply()
                    db = asyncio.get_event_loop().run_until_complete(get_db_client())
                    client = RustFSClient()
                    rows = asyncio.get_event_loop().run_until_complete(
                        db.fetch_all(
                            """
                            SELECT id, media_type, rustfs_url, original_url
                            FROM media_files
                            WHERE post_url = $1 AND download_status='completed'
                            ORDER BY id ASC
                            """,
                            view_post_url,
                        )
                    )
                    if not rows:
                        st.info("此貼文尚無可預覽的已下載媒體")
                    else:
                        st.success(f"找到 {len(rows)} 筆已下載媒體：")
                        for r in rows:
                            rustfs_url = r.get('rustfs_url')
                            original_url = r.get('original_url')
                            # 嘗試從 rustfs_url 萃取 key → 產生可讀 URL
                            url = None
                            try:
                                if rustfs_url:
                                    prefix = f"{client.base_url}/{client.bucket_name}/"
                                    key = rustfs_url[len(prefix):] if rustfs_url.startswith(prefix) else None
                                    url = client.get_public_or_presigned_url(key or '', prefer_presigned=True) if key else rustfs_url
                            except Exception:
                                url = None
                            if not url:
                                url = original_url

                            st.caption(f"[{r.get('media_type')}] 媒體ID: {r.get('id')}")
                            if r.get('media_type') == 'image' and url:
                                st.image(url, use_container_width=True)
                            elif r.get('media_type') == 'video' and url:
                                st.video(url)
                            else:
                                st.write(url or "(無可用連結)")
                            st.markdown("---")
                except Exception as e:
                    st.error(f"載入媒體失敗：{e}")

        # 介面：已下載媒體畫廊（快速總覽）
        st.markdown("---")
        # 畫廊展開狀態：載入後維持展開，避免因重繪而自行收合
        with st.expander("🖼️ 已下載媒體瀏覽（畫廊）", expanded=st.session_state.get("gal_loaded", False)):
            col_g1, col_g2, col_g3, col_g4, col_g5 = st.columns([2, 1, 1, 1, 1])
            with col_g1:
                gallery_user = st.text_input("帳號（可選）", value="", key="gallery_user")
            with col_g2:
                # 預設僅顯示圖片，減少負載、優先處理頭像類型
                gallery_types = st.multiselect("媒體類型", ["image", "video"], default=["image"], key="gallery_types")
            with col_g3:
                # 固定顯示 20 筆，避免卡頓
                gallery_limit = st.selectbox("顯示數量", [20], index=0, key="gallery_limit")
            with col_g4:
                cols_per_row = st.select_slider("每列數", options=[3, 4, 5, 6], value=5, key="gallery_cols")
            with col_g5:
                size_label = st.selectbox("縮圖大小", ["小", "中", "大"], index=0, key="gallery_size")

            thumb_width = {"小": 160, "中": 240, "大": 320}[size_label]

            # 是否走內部代理（由伺服器抓取 bytes，再由 8501 回傳給前端）— 預設關閉以降低阻塞風險
            use_internal_proxy = st.checkbox("由伺服器代理顯示（避免瀏覽器連 9000）", value=False, help="預設關閉以避免伺服器端同步抓取造成卡頓；必要時再開啟")
            # 快速互動模式：僅顯示連結，不抓取內容，避免每次勾選觸發重載造成卡頓
            # 為確保能看到縮圖進行勾選，預設關閉快速模式（僅 20 張影像）
            quick_mode = st.checkbox("快速互動模式（不載入縮圖/影片）", value=False, help="啟用後僅顯示連結；建議僅在大量操作或卡頓時開啟")

            # 點擊後記住狀態，避免元素在下一次重繪時消失而看起來像被鎖住
            if st.button("載入畫廊", key="btn_load_gallery"):
                st.session_state["gal_loaded"] = True
                st.session_state["gal_user"] = gallery_user
                st.session_state["gal_types"] = gallery_types
                st.session_state["gal_limit"] = int(gallery_limit)
                st.session_state["gal_cols"] = int(cols_per_row)
                st.session_state["gal_size"] = size_label
                st.session_state["gal_proxy"] = bool(use_internal_proxy)
                # 初始化分頁
                st.session_state["gal_page"] = 0

            if st.session_state.get("gal_loaded"):
                try:
                    # 使用已儲存的條件（若未存則採用當前 UI 值）
                    gallery_user = st.session_state.get("gal_user", gallery_user)
                    gallery_types = st.session_state.get("gal_types", gallery_types)
                    gallery_limit = st.session_state.get("gal_limit", int(gallery_limit))
                    cols_per_row = st.session_state.get("gal_cols", int(cols_per_row))
                    size_label = st.session_state.get("gal_size", size_label)
                    use_internal_proxy = st.session_state.get("gal_proxy", use_internal_proxy)
                    from common.db_client import get_db_client
                    from services.rustfs_client import RustFSClient
                    import nest_asyncio, asyncio
                    nest_asyncio.apply()

                    # 分頁狀態
                    page = int(st.session_state.get("gal_page", 0))
                    page_size = int(st.session_state.get("gal_limit", int(gallery_limit)))
                    offset = page * page_size

                    async def load_rows():
                        db = await get_db_client()
                        params = []
                        where = ["mf.download_status='completed'"]
                        if gallery_user:
                            where.append("ppm.username = $1")
                            params.append(gallery_user)
                        if gallery_types and len(gallery_types) < 2:
                            # 單一媒體類型
                            where.append("mf.media_type = $%d" % (len(params) + 1))
                            params.append(gallery_types[0])
                        where_sql = " AND ".join(where)
                        limit_param = len(params) + 1
                        offset_param = len(params) + 2
                        sql = f"""
                            SELECT mf.id, mf.media_type, mf.rustfs_key, mf.rustfs_url, mf.post_url, mf.original_url,
                                   mf.downloaded_at, mf.width, mf.height
                            FROM media_files mf
                            LEFT JOIN playwright_post_metrics ppm ON ppm.url = mf.post_url
                            WHERE {where_sql}
                            ORDER BY mf.downloaded_at DESC NULLS LAST, mf.id DESC
                            LIMIT ${limit_param} OFFSET ${offset_param}
                        """
                        params.append(int(page_size))
                        params.append(int(offset))
                        return await db.fetch_all(sql, *params)

                    rows = asyncio.get_event_loop().run_until_complete(load_rows())
                    if not rows:
                        st.info("沒有可顯示的已下載媒體")
                    else:
                        # 分頁控制列
                        nav_c1, nav_c2, nav_c3 = st.columns([1,1,3])
                        with nav_c1:
                            if st.button("⬅️ 上一頁", key="gal_prev", disabled=(page <= 0)):
                                st.session_state["gal_page"] = max(0, page - 1)
                                st.rerun()
                        with nav_c2:
                            if st.button("下一頁 ➡️", key="gal_next", disabled=(len(rows) < page_size)):
                                st.session_state["gal_page"] = page + 1
                                st.rerun()
                        with nav_c3:
                            st.caption(f"頁碼：第 {page + 1} 頁 | 本頁 {len(rows)} 筆（每頁 {page_size}）")
                        client = RustFSClient()
                        cols = None
                        # 管理工具：選取刪除
                        st.markdown("### 管理工具")
                        mg_col1, mg_col2, mg_col3, mg_col4, mg_col5 = st.columns([1,1,2,1,1])
                        with mg_col1:
                            select_all = st.button("全選", key="gal_select_all")
                        with mg_col2:
                            unselect_all = st.button("全不選", key="gal_unselect_all")
                        with mg_col3:
                            auto_avatar = st.checkbox("自動選取疑似頭像", value=False, help="依尺寸與近似方形自動勾選")
                        # 頭像判斷參數（並排顯示）
                        p_col1, p_col2 = st.columns([1,1])
                        with p_col1:
                            avatar_max_edge = st.number_input(
                                "頭像最大邊長(px)",
                                min_value=64, max_value=512,
                                value=int(st.session_state.get("avatar_max_edge", 256)),
                                step=10,
                                help="建議先用 256～320，再視結果微調；此值表示 min(寬,高) 的上限"
                            )
                        with p_col2:
                            avatar_square_tol = st.slider(
                                "方形容差(%)",
                                min_value=0, max_value=30,
                                value=int(st.session_state.get("avatar_square_tol", 10)),
                                step=1,
                                help="寬高比需在 1±此百分比 內（越小越接近正方形）"
                            )
                        require_squareish = st.checkbox(
                            "要求近似正方形",
                            value=bool(st.session_state.get("require_squareish", False)),
                            help="開啟：同時滿足『小尺寸』且『近方形』；關閉：任一成立即可（較寬鬆）"
                        )
                        # 持久化目前設定，便於一鍵套用與重繪後保留
                        st.session_state["avatar_max_edge"] = int(avatar_max_edge)
                        st.session_state["avatar_square_tol"] = int(avatar_square_tol)
                        st.session_state["require_squareish"] = bool(require_squareish)
                        with mg_col4:
                            if st.button("重新載入", key="gal_reload"):
                                st.rerun()
                        with mg_col5:
                            # 在工具列提供刪除按鈕，避免滾動到最下方才看見
                            quick_del = st.button("🗑️ 刪除選擇(頂部)", type="secondary", key="btn_delete_selected_top")

                        # 推薦門檻：根據本頁資料推估，提供一鍵套用（寬鬆/嚴格）
                        try:
                            img_edges = []
                            for rr in rows:
                                if rr.get('media_type') == 'image':
                                    wv = rr.get('width')
                                    hv = rr.get('height')
                                    try:
                                        wv = int(float(wv)) if wv is not None else 0
                                        hv = int(float(hv)) if hv is not None else 0
                                    except Exception:
                                        wv, hv = 0, 0
                                    if wv > 0 and hv > 0:
                                        img_edges.append(min(wv, hv))
                            if img_edges:
                                img_edges.sort()
                                n = len(img_edges)
                                idx35 = max(0, min(n - 1, int(0.35 * (n - 1))))
                                idx50 = max(0, min(n - 1, int(0.50 * (n - 1))))
                                rec_loose = max(128, min(320, img_edges[idx50]))
                                rec_strict = max(100, min(240, img_edges[idx35]))
                                tip_col1, tip_col2, tip_col3 = st.columns([2,1,1])
                                with tip_col1:
                                    st.caption(f"建議門檻：寬鬆≈{rec_loose}px、嚴格≈{rec_strict}px（依本頁樣本推估）")
                                with tip_col2:
                                    if st.button("套用寬鬆", key="gal_apply_loose"):
                                        st.session_state["avatar_max_edge"] = int(rec_loose)
                                        st.session_state["avatar_square_tol"] = 20
                                        st.session_state["require_squareish"] = False
                                        st.rerun()
                                with tip_col3:
                                    if st.button("套用嚴格", key="gal_apply_strict"):
                                        st.session_state["avatar_max_edge"] = int(rec_strict)
                                        st.session_state["avatar_square_tol"] = 8
                                        st.session_state["require_squareish"] = True
                                        st.rerun()
                        except Exception:
                            pass

                        # 先渲染卡片
                        def _to_int_dim(v):
                            try:
                                if isinstance(v, (int, float)):
                                    return int(v)
                                if isinstance(v, str) and v.strip():
                                    return int(float(v))
                                # 避免直接依賴 Decimal 類型，動態轉 float
                                if 'Decimal' in str(type(v)):
                                    return int(float(v))
                            except Exception:
                                return 0
                            return 0
                        for idx, r in enumerate(rows):
                            if idx % cols_per_row == 0:
                                cols = st.columns(cols_per_row)
                            col = cols[idx % cols_per_row]
                            with col:
                                # 選取方塊
                                chk_key = f"gal_sel_{r.get('id')}"
                                # 初始化選取狀態
                                default_chk = False
                                if auto_avatar:
                                    # 僅對圖片判斷頭像：小尺寸且近似正方形
                                    if r.get('media_type') == 'image':
                                        w = _to_int_dim(r.get('width'))
                                        h = _to_int_dim(r.get('height'))
                                        if w > 0 and h > 0:
                                            min_edge = min(w, h)
                                            ratio = (max(w, h) / min_edge) if min_edge > 0 else 999
                                            tol = 1.0 + (avatar_square_tol / 100.0)
                                            is_small = min_edge <= int(avatar_max_edge)
                                            is_squareish = ratio <= tol
                                            if require_squareish:
                                                default_chk = bool(is_small and is_squareish)
                                            else:
                                                default_chk = bool(is_small or is_squareish)
                                        else:
                                            default_chk = False
                                    else:
                                        default_chk = False
                                if select_all:
                                    st.session_state[chk_key] = True
                                if unselect_all:
                                    st.session_state[chk_key] = False
                                checked = st.checkbox("選取", key=chk_key, value=st.session_state.get(chk_key, default_chk))
                                rust_key = r.get('rustfs_key')
                                rustfs_url = r.get('rustfs_url')
                                original_url = r.get('original_url')
                                media_type = r.get('media_type')
                                # 產生可用 URL（優先簽名 URL）
                                url = None
                                try:
                                    if rust_key:
                                        url = client.get_public_or_presigned_url(rust_key, prefer_presigned=True)
                                    elif rustfs_url:
                                        prefix = f"{client.base_url}/{client.bucket_name}/"
                                        key = rustfs_url[len(prefix):] if rustfs_url.startswith(prefix) else None
                                        url = client.get_public_or_presigned_url(key or '', prefer_presigned=True) if key else rustfs_url
                                except Exception:
                                    url = None
                                if not url:
                                    url = original_url

                                # 顯示尺寸資訊，便於判斷門檻
                                w_disp = _to_int_dim(r.get('width'))
                                h_disp = _to_int_dim(r.get('height'))
                                size_tag = f" · {w_disp}x{h_disp}px" if (w_disp and h_disp) else ""
                                st.caption(f"#{r.get('id')} · {media_type}{size_tag}")
                                if media_type == 'image' and url:
                                    if quick_mode:
                                        st.markdown(f"[預覽圖片]({url})")
                                    else:
                                        if use_internal_proxy:
                                            try:
                                                # 伺服器端抓取圖片 bytes，再由 Streamlit 內嵌顯示
                                                import requests
                                                resp = requests.get(url, timeout=5)
                                                if resp.status_code == 200:
                                                    st.image(resp.content, width=thumb_width)
                                                else:
                                                    st.caption(f"(圖片載入失敗 {resp.status_code})")
                                            except Exception as _:
                                                st.caption("(圖片代理失敗)")
                                        else:
                                            st.image(url, width=thumb_width)
                                elif media_type == 'video' and url:
                                    # 為避免鎖死與高記憶體占用，影片一律以連結開啟；快速模式同樣顯示連結
                                    st.markdown(f"[開啟影片]({url})")
                                else:
                                    st.write(url or "(無可用連結)")
                                # 連結與貼文 URL
                                link_cols = st.columns([1, 1])
                                with link_cols[0]:
                                    if url:
                                        st.markdown(f"[開啟]({url})")
                                with link_cols[1]:
                                    pu = r.get('post_url')
                                    if pu:
                                        st.markdown(f"[貼文]({pu})")

                        # 刪除動作
                        # 共用刪除處理
                        def _perform_delete(rows):
                            import asyncio
                            from common.db_client import get_db_client
                            # 讀取選取清單
                            sel_ids = []
                            for r in rows:
                                chk_key = f"gal_sel_{r.get('id')}"
                                if st.session_state.get(chk_key):
                                    sel_ids.append(r.get('id'))
                            if not sel_ids:
                                st.info("未選取任何項目")
                                return
                            async def _fetch_for_delete(ids: list[int]):
                                db = await get_db_client()
                                placeholders = ",".join([f"${i+1}" for i in range(len(ids))])
                                rows_del = await db.fetch_all(
                                    f"SELECT id, rustfs_key FROM media_files WHERE id IN ({placeholders})",
                                    *ids
                                )
                                return rows_del
                            rows_del = asyncio.get_event_loop().run_until_complete(_fetch_for_delete(sel_ids))
                            from common.rustfs_client import get_rustfs_client as get_common_rustfs
                            rust_client = get_common_rustfs()
                            s3_deleted, s3_failed = 0, 0
                            for rr in rows_del:
                                key = rr.get('rustfs_key')
                                if key:
                                    try:
                                        if rust_client.delete_media(key):
                                            s3_deleted += 1
                                        else:
                                            s3_failed += 1
                                    except Exception:
                                        s3_failed += 1
                            async def _delete_rows(ids: list[int]):
                                db = await get_db_client()
                                placeholders = ",".join([f"${i+1}" for i in range(len(ids))])
                                await db.execute(
                                    f"DELETE FROM media_files WHERE id IN ({placeholders})",
                                    *ids
                                )
                            asyncio.get_event_loop().run_until_complete(_delete_rows(sel_ids))
                            st.success(f"刪除完成：S3刪除成功 {s3_deleted}，失敗 {s3_failed}，DB刪除 {len(sel_ids)}")
                            st.rerun()

                        if quick_del:
                            try:
                                _perform_delete(rows)
                            except Exception as de:
                                st.error(f"刪除失敗：{de}")

                        if st.button("🗑️ 刪除選擇", type="secondary", key="btn_delete_selected"):
                            try:
                                _perform_delete(rows)
                            except Exception as de:
                                st.error(f"刪除失敗：{de}")
                except Exception as e:
                    st.error(f"載入畫廊失敗：{e}")

        

    # ---------- 描述器 ----------
    def _render_describer(self):
        st.subheader("🧠 媒體描述器（Gemini 2.5 Pro）")
        # Gemini 健檢（只檢查 API key 存在）
        import os
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except Exception:
            pass
        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            st.success("Gemini API Key 已配置")
        else:
            st.error("缺少 GEMINI_API_KEY/GOOGLE_API_KEY")

        st.markdown("---")

        # 描述現況（帳號彙總）
        try:
            from agents.vision.media_describe_service import MediaDescribeService
            import nest_asyncio, asyncio, pandas as pd
            nest_asyncio.apply()
            svc = MediaDescribeService()
            stats = asyncio.get_event_loop().run_until_complete(svc.get_account_describe_stats(limit=50))
            st.subheader("📊 描述現況（帳號彙總：待描述）")
            if stats:
                df = pd.DataFrame(stats)
                df = df.rename(columns={
                    "username": "使用者",
                    "pending_images": "待描述圖片",
                    "pending_videos": "待描述影片",
                    "completed_images": "已描述圖片",
                    "completed_videos": "已描述影片",
                    "pending_total": "待描述合計",
                    "completed_total": "已描述合計",
                })
                st.dataframe(df, use_container_width=True, height=min(400, 38 + len(df) * 32))
            else:
                st.info("尚無待描述統計資料")
        except Exception as e:
            st.warning(f"描述統計載入失敗：{e}")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            target_username = st.text_input("帳號", value="natgeo", key="desc_user")
        with col2:
            media_types = st.multiselect("媒體類型", ["image", "video"], default=["image"], key="desc_types")
        with col3:
            sort_by = st.selectbox("排序欄位", ["none", "views", "likes", "comments", "reposts"], index=0, key="desc_sort")
        with col4:
            top_k = st.selectbox("Top-N", ["全部", 5, 10, 25, 50, 100], index=0, key="desc_topk")

        col5, col6, col7 = st.columns(3)
        with col5:
            overwrite = st.checkbox("重新描述（覆蓋舊的）", value=True)
        with col6:
            concurrency = st.selectbox("並發數", [1, 2, 3], index=0, key="desc_ccy")
        with col7:
            only_undesc = st.checkbox("僅未描述", value=True, key="only_undesc")

        col8, col9, col10 = st.columns(3)
        with col8:
            only_primary = st.checkbox("僅主貼圖（圖片）", value=True, help="根據規則分數/標記過濾非主貼圖")
        with col9:
            primary_threshold = st.slider("主貼圖門檻", min_value=0.5, max_value=0.9, value=0.7, step=0.05)
        with col10:
            use_vlm_refine = st.checkbox("使用小模型複核(預留)", value=False, help="預留開關，後續接入快速VLM二分類")

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
                    only_undesc=only_undesc,
                    only_primary=only_primary,
                    primary_threshold=float(primary_threshold)
                ))
                # 以媒體數量為單位的 Top-N 強制切齊（UI 保護，避免後端未切齊或版本差異）
                try:
                    if top_k != "全部":
                        items = items[:int(top_k)]
                except Exception:
                    pass
                if not items:
                    st.info("沒有待描述的媒體")
                    return
                st.info(f"即將描述 {len(items)} 個媒體項目…")
                # 即時進度條
                progress = st.progress(0.0)
                status_area = st.empty()

                # 逐批處理，邊更新 UI（避免一次性等待）
                batch_size = 5
                total = len(items)
                completed = 0
                agg_success, agg_failed = 0, 0
                details_all = []
                for i in range(0, total, batch_size):
                    batch = items[i:i+batch_size]
                    result = asyncio.get_event_loop().run_until_complete(svc.run_describe(batch, overwrite=True))
                    agg_success += result.get('success', 0)
                    agg_failed += result.get('failed', 0)
                    details_all.extend(result.get('details', []))
                    completed = min(total, i+batch_size)
                    progress.progress(completed/total)
                    status_area.info(f"進度：{completed}/{total}（成功 {agg_success}，失敗 {agg_failed}）")

                st.success(f"描述完成：成功 {agg_success}，失敗 {agg_failed} / 共 {total}")
                # 失敗樣本展示
                failed_samples = [d for d in details_all if d.get('status') == 'failed']
                if failed_samples:
                    with st.expander("❌ 失敗詳情（前10筆）", expanded=False):
                        for d in failed_samples[:10]:
                            st.write(d)
            except Exception as e:
                st.error(f"描述執行失敗：{e}")

        # 介面：依帳號瀏覽（成果/待描述 內容預覽）
        st.markdown("---")
        with st.expander("📋 帳號內容瀏覽（描述成果 / 待描述）", expanded=False):
            sum_user = st.text_input("帳號", value="natgeo", key="sum_user")
            sum_types = st.multiselect("媒體類型", ["image", "video"], default=["image"], key="sum_types")
            sum_limit = st.selectbox("顯示數量", [10, 20, 50], index=1, key="sum_limit")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                btn_recent = st.button("載入最近描述成果", key="btn_load_recent_desc")
            with col_b2:
                btn_pending = st.button("載入待描述媒體", key="btn_load_pending_media")

            if btn_recent and sum_user:
                try:
                    from agents.vision.media_describe_service import MediaDescribeService
                    import nest_asyncio, asyncio
                    nest_asyncio.apply()
                    svc = MediaDescribeService()
                    rows = asyncio.get_event_loop().run_until_complete(
                        svc.get_recent_descriptions_by_user(sum_user, sum_types, int(sum_limit))
                    )
                    if rows:
                        st.subheader("🟩 最近描述成果")
                        for r in rows:
                            st.caption(f"[{r.get('media_type')}] 模型: {r.get('model')} | 時間: {r.get('created_at')} | 貼文: {r.get('post_url')}")
                            try:
                                import json as _json
                                st.json(_json.loads(r.get('response_json') or '{}'))
                            except Exception:
                                st.code(r.get('response_json') or '')
                            st.markdown("---")
                    else:
                        st.info("此帳號暫無描述成果")
                except Exception as e:
                    st.error(f"載入描述成果失敗：{e}")

            if btn_pending and sum_user:
                try:
                    from agents.vision.media_describe_service import MediaDescribeService
                    from services.rustfs_client import RustFSClient
                    import nest_asyncio, asyncio
                    nest_asyncio.apply()
                    svc = MediaDescribeService()
                    client = RustFSClient()
                    rows = asyncio.get_event_loop().run_until_complete(
                        svc.get_pending_media_by_user(sum_user, sum_types, int(sum_limit))
                    )
                    if rows:
                        st.subheader("🟨 待描述媒體預覽")
                        for f in rows:
                            rust_key = f.get('rustfs_key')
                            rustfs_url = None
                            if rust_key:
                                rustfs_url = client.get_public_or_presigned_url(rust_key, prefer_presigned=True)
                            st.caption(f"[{f.get('media_type')}] {f.get('post_url')}")
                            if rustfs_url and f.get('media_type') == 'image':
                                st.image(rustfs_url, use_container_width=True)
                            elif rustfs_url and f.get('media_type') == 'video':
                                st.video(rustfs_url)
                            st.markdown("---")
                    else:
                        st.info("此帳號沒有待描述的媒體或篩選為空")
                except Exception as e:
                    st.error(f"載入待描述內容失敗：{e}")
                try:
                    from agents.vision.media_describe_service import MediaDescribeService
                    import nest_asyncio, asyncio, pandas as pd
                    nest_asyncio.apply()
                    svc = MediaDescribeService()
                    data = asyncio.get_event_loop().run_until_complete(
                        svc.get_undesc_summary_by_user(sum_user, sum_types, int(sum_limit))
                    )
                    if data:
                        df = pd.DataFrame(data)
                        df = df.rename(columns={
                            'post_url': '貼文URL',
                            'pending_images': '待描述圖片',
                            'pending_videos': '待描述影片',
                            'pending_total': '合計'
                        })
                        st.dataframe(df, use_container_width=True)
                    else:
                        st.info("找不到未描述的貼文摘要")
                except Exception as e:
                    st.error(f"載入摘要失敗：{e}")

        # 介面：單篇立即描述（上移）
        with st.expander("🔧 單篇立即描述", expanded=False):
            sp_url = st.text_input("貼文 URL（https://www.threads.net/@user/post/XXXX）", key="single_desc_url")
            st.caption("此模式並發數固定為 1（不受上方並發設定影響）")
            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            with col_s1:
                sp_types = st.multiselect("媒體類型", ["image", "video"], default=["image"], key="single_desc_types")
            with col_s2:
                sp_only_primary = st.checkbox("僅主貼圖（圖片）", value=True, key="single_only_primary")
            with col_s3:
                sp_threshold = st.slider("主貼圖門檻", min_value=0.5, max_value=0.9, value=0.7, step=0.05, key="single_primary_th")
            with col_s4:
                sp_overwrite = st.checkbox("重新描述（覆蓋舊的）", value=True, key="single_overwrite")

            if st.button("開始單篇描述", key="btn_single_describe") and sp_url:
                try:
                    from agents.vision.media_describe_service import MediaDescribeService
                    import nest_asyncio, asyncio
                    nest_asyncio.apply()
                    svc = MediaDescribeService()
                    with st.spinner("正在描述該貼文的媒體..."):
                        sp_result = asyncio.get_event_loop().run_until_complete(
                            svc.describe_single_post(
                                post_url=sp_url,
                                media_types=sp_types,
                                only_primary=sp_only_primary,
                                primary_threshold=float(sp_threshold),
                                overwrite=sp_overwrite,
                            )
                        )
                    st.success(f"完成：成功 {sp_result.get('success',0)}，失敗 {sp_result.get('failed',0)} / 共 {sp_result.get('total',0)}")
                    # 顯示少量詳情
                    dets = sp_result.get('details') or []
                    failed = [d for d in dets if d.get('status') == 'failed']
                    if failed:
                        with st.expander("❌ 失敗詳情（前5筆）", expanded=False):
                            for d in failed[:5]:
                                st.write(d)
                except Exception as e:
                    st.error(f"單篇描述執行失敗：{e}")

        # 介面：單篇描述結果瀏覽（下移）
        st.markdown("---")
        with st.expander("🧾 單篇描述結果瀏覽（輸入貼文 URL）", expanded=False):
            view_post_url = st.text_input("貼文 URL（https://www.threads.net/@user/post/XXXX）", key="view_post_url_desc")
            col_v1, col_v2 = st.columns([1, 9])
            with col_v1:
                if st.button("載入描述結果", key="btn_view_desc") and view_post_url:
                    try:
                        from agents.vision.media_describe_service import MediaDescribeService
                        import nest_asyncio, asyncio
                        nest_asyncio.apply()
                        svc = MediaDescribeService()
                        rows = asyncio.get_event_loop().run_until_complete(svc.get_descriptions_by_post(view_post_url))
                        if not rows:
                            st.info("此貼文尚無描述結果")
                        else:
                            st.success(f"找到 {len(rows)} 筆描述結果：")
                        for r in rows:
                            st.caption(f"[{r.get('media_type')}] 模型: {r.get('model')} | 時間: {r.get('created_at')}")
                            resp = r.get('response_json') or ''
                            st.code(resp, language="json")
                            st.markdown("---")
                    except Exception as e:
                        st.error(f"載入媒體失敗：{e}")


