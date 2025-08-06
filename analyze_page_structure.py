"""
頁面結構分析器
訪問測試頁面，保存HTML快照，分析DOM結構以修復選擇器
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup
import re

import sys
sys.path.append(str(Path(__file__).parent))

from playwright.async_api import async_playwright
from common.config import get_auth_file_path

# 測試目標
TEST_URL = "https://www.threads.net/@threads/post/DMxtXaggxsL"

class PageAnalyzer:
    """頁面結構分析器"""
    
    def __init__(self):
        self.auth_file_path = get_auth_file_path()
    
    async def analyze_page_structure(self):
        """分析頁面結構並保存HTML快照"""
        print("🔍 分析頁面結構...")
        print(f"🎯 目標頁面: {TEST_URL}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                storage_state=str(self.auth_file_path),
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            
            page = await context.new_page()
            
            try:
                # 導航到頁面
                print("   🌐 導航到測試頁面...")
                await page.goto(TEST_URL, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(5)  # 等待完全載入
                
                # 保存頁面快照
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # 1. 保存完整HTML
                html_content = await page.content()
                html_file = Path(f"page_snapshot_{timestamp}.html")
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                print(f"   📄 HTML快照已保存: {html_file}")
                
                # 2. 保存截圖
                screenshot_file = Path(f"page_screenshot_{timestamp}.png")
                await page.screenshot(path=str(screenshot_file), full_page=True)
                print(f"   📸 截圖已保存: {screenshot_file}")
                
                # 3. 分析DOM結構
                print("   🔍 分析DOM結構...")
                analysis_result = await self._analyze_dom_structure(page, html_content)
                
                # 4. 保存分析結果
                analysis_file = Path(f"dom_analysis_{timestamp}.json")
                with open(analysis_file, 'w', encoding='utf-8') as f:
                    json.dump(analysis_result, f, indent=2, ensure_ascii=False)
                print(f"   📊 分析結果已保存: {analysis_file}")
                
                # 5. 生成修復建議
                suggestions = self._generate_fix_suggestions(analysis_result)
                suggestions_file = Path(f"fix_suggestions_{timestamp}.md")
                with open(suggestions_file, 'w', encoding='utf-8') as f:
                    f.write(suggestions)
                print(f"   💡 修復建議已保存: {suggestions_file}")
                
                print(f"\n✅ 頁面分析完成！")
                print(f"   📁 生成了 4 個文件：HTML快照、截圖、分析結果、修復建議")
                
                return analysis_result
                
            except Exception as e:
                print(f"   ❌ 頁面分析失敗: {e}")
                return None
            finally:
                await browser.close()
    
    async def _analyze_dom_structure(self, page, html_content: str) -> Dict[str, Any]:
        """分析DOM結構，尋找互動數據元素"""
        analysis = {
            "page_info": {
                "url": TEST_URL,
                "title": await page.title(),
                "analyzed_at": datetime.now().isoformat()
            },
            "potential_selectors": {
                "likes": [],
                "comments": [],
                "reposts": [],
                "shares": [],
                "content": []
            },
            "found_numbers": [],
            "button_elements": [],
            "aria_labels": []
        }
        
        # 使用BeautifulSoup解析HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 1. 找到所有包含數字的元素
        print("      🔢 搜索包含數字的元素...")
        all_elements = soup.find_all(string=re.compile(r'\d+'))
        for element in all_elements[:50]:  # 限制數量避免太多
            parent = element.parent
            if parent:
                text = element.strip()
                if re.search(r'\d+', text):
                    analysis["found_numbers"].append({
                        "text": text,
                        "tag": parent.name,
                        "classes": parent.get('class', []),
                        "aria_label": parent.get('aria-label', ''),
                        "parent_tag": parent.parent.name if parent.parent else None
                    })
        
        # 2. 找到所有按鈕元素
        print("      🔘 分析按鈕元素...")
        buttons = soup.find_all(['button', 'div'], attrs={'role': 'button'})
        for button in buttons[:30]:  # 限制數量
            button_info = {
                "tag": button.name,
                "aria_label": button.get('aria-label', ''),
                "classes": button.get('class', []),
                "text": button.get_text().strip()[:100],  # 限制長度
                "has_svg": bool(button.find('svg')),
                "data_attributes": {k: v for k, v in button.attrs.items() if k.startswith('data-')}
            }
            analysis["button_elements"].append(button_info)
        
        # 3. 收集所有aria-label
        print("      🏷️ 收集aria-label屬性...")
        aria_elements = soup.find_all(attrs={'aria-label': True})
        for element in aria_elements[:50]:
            aria_label = element.get('aria-label', '')
            if aria_label:
                analysis["aria_labels"].append({
                    "aria_label": aria_label,
                    "tag": element.name,
                    "classes": element.get('class', []),
                    "text": element.get_text().strip()[:50]
                })
        
        # 4. 基於啟發式方法推薦選擇器
        print("      🎯 生成選擇器建議...")
        
        # 按讚相關
        like_keywords = ['like', 'likes', '喜歡', '按讚', '👍', '❤️']
        for item in analysis["aria_labels"] + analysis["button_elements"]:
            text = (item.get('aria_label', '') + ' ' + item.get('text', '')).lower()
            if any(keyword in text for keyword in like_keywords):
                selector = self._generate_selector_from_element(item)
                if selector:
                    analysis["potential_selectors"]["likes"].append(selector)
        
        # 留言相關
        comment_keywords = ['comment', 'comments', '留言', '評論', '💬']
        for item in analysis["aria_labels"] + analysis["button_elements"]:
            text = (item.get('aria_label', '') + ' ' + item.get('text', '')).lower()
            if any(keyword in text for keyword in comment_keywords):
                selector = self._generate_selector_from_element(item)
                if selector:
                    analysis["potential_selectors"]["comments"].append(selector)
        
        # 轉發相關
        repost_keywords = ['repost', 'reposts', '轉發', '轉貼', '🔄']
        for item in analysis["aria_labels"] + analysis["button_elements"]:
            text = (item.get('aria_label', '') + ' ' + item.get('text', '')).lower()
            if any(keyword in text for keyword in repost_keywords):
                selector = self._generate_selector_from_element(item)
                if selector:
                    analysis["potential_selectors"]["reposts"].append(selector)
        
        # 分享相關
        share_keywords = ['share', 'shares', '分享', '📤']
        for item in analysis["aria_labels"] + analysis["button_elements"]:
            text = (item.get('aria_label', '') + ' ' + item.get('text', '')).lower()
            if any(keyword in text for keyword in share_keywords):
                selector = self._generate_selector_from_element(item)
                if selector:
                    analysis["potential_selectors"]["shares"].append(selector)
        
        return analysis
    
    def _generate_selector_from_element(self, element_info: Dict) -> Optional[str]:
        """從元素信息生成CSS選擇器"""
        tag = element_info.get('tag', '')
        classes = element_info.get('classes', [])
        aria_label = element_info.get('aria_label', '')
        
        selectors = []
        
        # 基於aria-label的選擇器
        if aria_label:
            # 完整匹配
            selectors.append(f'{tag}[aria-label="{aria_label}"]')
            # 部分匹配
            selectors.append(f'{tag}[aria-label*="{aria_label[:20]}"]')
        
        # 基於class的選擇器
        if classes:
            class_selector = '.'.join(classes[:3])  # 最多用前3個class
            selectors.append(f'{tag}.{class_selector}')
        
        # 返回第一個有效的選擇器
        return selectors[0] if selectors else None
    
    def _generate_fix_suggestions(self, analysis: Dict[str, Any]) -> str:
        """生成修復建議文檔"""
        suggestions = f"""# Threads DOM結構分析 - 修復建議

## 分析時間
{analysis['page_info']['analyzed_at']}

## 頁面信息
- URL: {analysis['page_info']['url']}
- 標題: {analysis['page_info']['title']}

## 🔧 建議的新選擇器

### 按讚數提取
"""
        
        # 添加按讚選擇器建議
        likes_selectors = analysis['potential_selectors']['likes']
        if likes_selectors:
            suggestions += "```python\nlikes_selectors = [\n"
            for selector in likes_selectors[:5]:
                suggestions += f'    "{selector}",\n'
            suggestions += "]\n```\n\n"
        else:
            suggestions += "❌ 未找到明顯的按讚相關元素\n\n"
        
        # 添加留言選擇器建議
        suggestions += "### 留言數提取\n"
        comments_selectors = analysis['potential_selectors']['comments']
        if comments_selectors:
            suggestions += "```python\ncomments_selectors = [\n"
            for selector in comments_selectors[:5]:
                suggestions += f'    "{selector}",\n'
            suggestions += "]\n```\n\n"
        else:
            suggestions += "❌ 未找到明顯的留言相關元素\n\n"
        
        # 添加數字元素分析
        suggestions += "## 📊 發現的數字元素\n\n"
        found_numbers = analysis['found_numbers'][:10]
        for i, num_info in enumerate(found_numbers):
            suggestions += f"**元素 {i+1}:**\n"
            suggestions += f"- 文字: `{num_info['text']}`\n"
            suggestions += f"- 標籤: `{num_info['tag']}`\n"
            suggestions += f"- 類別: `{num_info['classes']}`\n"
            if num_info['aria_label']:
                suggestions += f"- Aria-label: `{num_info['aria_label']}`\n"
            suggestions += "\n"
        
        # 添加實施建議
        suggestions += """## 🛠️ 實施建議

1. **更新 details_extractor.py**
   - 將新的選擇器添加到 `count_selectors` 字典中
   - 按優先級排序（最可能成功的放在前面）

2. **測試建議**
   - 先測試單個選擇器
   - 確認提取到的文字格式
   - 驗證數字解析邏輯

3. **後備策略**
   - 如果特定選擇器失敗，嘗試通用數字提取
   - 使用智能數字分配邏輯

## 📝 實施代碼範例

```python
# 在 details_extractor.py 中更新選擇器
count_selectors = {
    "likes": [
        # 新的選擇器（從分析結果中獲得）
"""
        
        # 添加實際的選擇器
        for selector in likes_selectors[:3]:
            suggestions += f'        "{selector}",\n'
        
        suggestions += """    ],
    "comments": [
        # 新的留言選擇器
"""
        
        for selector in comments_selectors[:3]:
            suggestions += f'        "{selector}",\n'
        
        suggestions += """    ]
}
```
"""
        
        return suggestions

async def main():
    """主函數"""
    print("🔍 Threads頁面結構分析器")
    
    analyzer = PageAnalyzer()
    
    # 檢查認證文件
    if not analyzer.auth_file_path.exists():
        print(f"❌ 認證檔案 {analyzer.auth_file_path} 不存在")
        print("💡 請先運行 save_auth.py 生成認證檔案")
        return
    
    # 分析頁面結構
    result = await analyzer.analyze_page_structure()
    
    if result:
        print(f"\n🎉 分析完成！")
        print(f"📊 找到 {len(result['found_numbers'])} 個數字元素")
        print(f"🔘 找到 {len(result['button_elements'])} 個按鈕元素")
        print(f"🏷️ 找到 {len(result['aria_labels'])} 個aria-label")
        
        # 顯示建議的選擇器數量
        selectors_count = sum(len(selectors) for selectors in result['potential_selectors'].values())
        print(f"🎯 生成 {selectors_count} 個候選選擇器")
        
        print(f"\n💡 接下來可以:")
        print(f"   1. 查看生成的HTML快照和截圖")
        print(f"   2. 閱讀修復建議文件")
        print(f"   3. 將新選擇器整合到playwright_crawler中")
    else:
        print(f"\n😞 分析失敗")

if __name__ == "__main__":
    asyncio.run(main())