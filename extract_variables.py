import json
import urllib.parse

# 讀取檔案
with open('potential_content_BarcelonaPostPageRefetchableDirectQuery_183429.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 提取 POST 數據
post_data = data['request_post_data']

# 分解變數
variables_part = post_data.split('variables=')[1].split('&')[0]
variables_json = urllib.parse.unquote(variables_part)

print("真實的變數格式:")
print(json.dumps(json.loads(variables_json), indent=2, ensure_ascii=False))

# 提取 doc_id
doc_id_match = post_data.split('doc_id=')[1].split('&')[0]
print(f"\n真實的 doc_id: {doc_id_match}")