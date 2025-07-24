# threads_fetch.py
import asyncio, json, pathlib, sys, re
from playwright.async_api import async_playwright
import logging

# 設定基本日誌記錄
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 組態設定 ---
# AUTH_FILE: 驗證狀態檔案的路徑。
# 請先執行 save_auth.py 指令碼來建立此檔案。
AUTH_FILE = pathlib.Path("auth.json")

# TARGET_URL: 要爬取的 Threads 個人檔案 URL。
TARGET_URL = "https://www.threads.com/@natgeo"

# MAX_POSTS: 要爬取的最大貼文數量。
MAX_POSTS = 100

# OUTPUT_FILE: 儲存爬取資料的路徑。
# 如果目錄不存在，將會自動建立。
OUTPUT_FILE = pathlib.Path("results/profile.json")

# --- GraphQL API 詳細資訊 ---
# 用於識別貼文 GraphQL API 呼叫的正規表示式。
GRAPHQL_RE = re.compile(r"/graphql/query")

# 已知的 GraphQL 查詢名稱，用於擷取貼文。
# 我們監聽這些查詢以擷取貼文資料。
POST_QUERY_NAMES = {
    # 2025 年 7 月發現，似乎是個人檔案貼文的主要查詢
    "BarcelonaProfileThreadsTabRefetchableDirectQuery",
    # 舊的查詢名稱，保留作為備用
    "BarcelonaProfilePostsTabQuery",
    "BarcelonaProfilePostsPageQuery",
}


def remove_media_versions(data):
    """
    遞迴地從資料中移除 'image_versions2' 和 'video_versions'，以簡化輸出。
    """
    if isinstance(data, dict):
        # 移除目前層級的鍵
        data.pop('image_versions2', None)
        data.pop('video_versions', None)
        # 遞迴處理字典中的值
        for key, value in data.items():
            remove_media_versions(value)
    elif isinstance(data, list):
        # 遞迴處理列表中的每個項目
        for item in data:
            remove_media_versions(item)


def parse_post_data(post_data: dict) -> dict:
    """
    解析單篇貼文的 JSON 資料並提取相關欄位。
    """
    post = post_data.get('post', {})
    if not post:
        return {}

    # 安全地提取使用者資訊
    user = post.get('user', {})
    # 提取文字和媒體資訊
    caption = post.get('caption', {})
    text_post_app_info = post.get('text_post_app_info', {})
    share_info = text_post_app_info.get('share_info', {})

    # 提取圖片和影片 URL
    image_url = None
    if post.get('image_versions2', {}).get('candidates'):
        # 取得最高解析度的圖片
        if post['image_versions2']['candidates']:
            image_url = post['image_versions2']['candidates'][0].get('url')

    video_url = None
    if post.get('video_versions'):
        if post['video_versions']:
            video_url = post['video_versions'][0].get('url')

    # 遞迴處理引用的貼文
    quoted_post = None
    if share_info.get('quoted_post'):
        # 引用的貼文是巢狀結構，所以我們也對其進行解析。
        # 注意：'quoted_post' 可能不包含完整的 'post' 物件，
        # 所以我們將整個字典傳遞給解析器。
        quoted_post_data = {'post': share_info['quoted_post']}
        quoted_post = parse_post_data(quoted_post_data)


    return {
        'post_id': post.get('pk'),
        'post_code': post.get('code'),
        'post_url': f"https://www.threads.net/t/{post.get('code')}" if post.get('code') else None,
        'user_id': user.get('pk'),
        'username': user.get('username'),
        'user_profile_pic': user.get('profile_pic_url'),
        'is_verified_user': user.get('is_verified'),
        'taken_at': post.get('taken_at'),
        'caption': caption.get('text'),
        'like_count': post.get('like_count'),
        'reply_count': text_post_app_info.get('direct_reply_count'),
        'repost_count': text_post_app_info.get('repost_count'),
        'quote_count': text_post_app_info.get('quote_count'),
        'view_count': post.get('view_count'), # 註：此欄位目前在 API 回應中找不到，預留欄位
        'image_url': image_url,
        'video_url': video_url,
        'quoted_post': quoted_post,
    }


async def main():
    if not AUTH_FILE.exists():
        logging.error("驗證檔案 'auth.json' 不存在。")
        sys.exit(f"❌ 請先執行 save_auth.py 指令碼以建立 {AUTH_FILE}")

    # 確保輸出目錄存在
    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    
    posts = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(storage_state=AUTH_FILE)
        page = await ctx.new_page()

        async def on_response(res):
            # 我們只對 GraphQL 回應感興趣
            if not GRAPHQL_RE.search(res.url):
                return
            
            # 檢查回應是否為我們的目標查詢之一
            qname = res.request.headers.get("x-fb-friendly-name")
            if qname not in POST_QUERY_NAMES:
                return

            logging.info(f"🎯 命中目標查詢: {qname}")
            try:
                data = await res.json()
                # 貼文巢狀地位於此結構中
                edges = data.get('data', {}).get('mediaData', {}).get('edges', [])
                
                parsed_count = 0
                for edge in edges:
                    thread_items = edge.get('node', {}).get('thread_items', [])
                    for item in thread_items:
                        parsed_post = parse_post_data(item)
                        if parsed_post.get('post_id') and parsed_post['post_id'] not in posts:
                            posts[parsed_post['post_id']] = parsed_post
                            parsed_count += 1
                
                if parsed_count > 0:
                    logging.info(f"✅ 已解析 {parsed_count} 則新貼文。總數: {len(posts)}")

            except Exception as e:
                logging.error(f"解析查詢 {qname} 的 JSON 失敗: {e}")

        page.on("response", on_response)
        
        logging.info(f"正在導覽至 {TARGET_URL}")
        await page.goto(TARGET_URL, wait_until="networkidle")

        logging.info("開始滾動並爬取貼文...")
        
        # 滾動迴圈以載入更多貼文
        scroll_attempts = 0
        max_scroll_attempts_without_new_posts = 5

        while len(posts) < MAX_POSTS:
            posts_before_scroll = len(posts)
            
            # 滾動到頁面底部
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            
            # 等待新內容載入
            try:
                # 使用 expect_response 等待符合條件的網路回應
                async with page.expect_response(lambda res: GRAPHQL_RE.search(res.url), timeout=5000) as response_info:
                    await response_info.value
            except asyncio.TimeoutError:
                logging.warning("滾動後等待網路回應逾時。可能已達頁面末端。")

            # 額外等待以確保客戶端渲染完成
            await page.wait_for_timeout(2000)

            posts_after_scroll = len(posts)

            if posts_after_scroll == posts_before_scroll:
                scroll_attempts += 1
                logging.info(f"滾動嘗試 {scroll_attempts}/{max_scroll_attempts_without_new_posts} 未發現新貼文。")
                if scroll_attempts >= max_scroll_attempts_without_new_posts:
                    logging.info("已達個人檔案末端或無新貼文載入。停止滾動。")
                    break
            else:
                # 若找到新貼文則重設計數器
                scroll_attempts = 0

            if len(posts) >= MAX_POSTS:
                logging.info(f"已達到 {MAX_POSTS} 的 MAX_POSTS 限制。")
                break
        
        await ctx.close()

    logging.info(f"爬取完成。總共收集到 {len(posts)} 則貼文。")
    
    # 儲存收集到的資料
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(list(posts.values()), f, indent=2, ensure_ascii=False)
    
    logging.info(f"✅ 結果已儲存至 {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main()) 