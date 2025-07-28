# 動態B+C層步驟組合器

## 功能概述
根據原文的主題、調性和風格特徵，智能組合最適合的B+C層規則應用步驟，提供彈性的客製化流程。

## 核心組合邏輯

### 🎯 主題調性分析維度

#### 內容類型分類
```json
{
  "narrative_heavy": "敘事重點型（故事、經歷、現場描述）",
  "commentary_heavy": "評論重點型（觀點、分析、價值判斷）", 
  "emotional_heavy": "情感重點型（心情、感受、抒發）",
  "interactive_heavy": "互動重點型（問答、分享、邀請）",
  "mixed_balanced": "混合平衡型（多種元素並重）"
}
```

#### 語言節奏偏好
```json
{
  "fast_paced": "快節奏型（短句多、跳接感強）",
  "slow_paced": "慢節奏型（長句多、深度思考）",
  "rhythmic_varied": "節奏變化型（長短句交錯）",
  "conversational": "對話型（口語化、親近感）"
}
```

#### 邏輯連貫需求
```json
{
  "strong_logic": "強邏輯型（因果清晰、論證完整）",
  "weak_coherence": "弱連貫型（意象呼應、跳躍思維）",
  "narrative_chain": "敘事鏈型（時間順序、情節發展）",
  "thematic_flow": "主題流動型（主題延續、層次深入）"
}
```

## 預設步驟組合模板

### 📋 模板1：敘事重點型 + 快節奏
```json
{
  "template_id": "narrative_fast",
  "suitable_for": "現場描述、事件記錄、互動故事",
  "steps": [
    {
      "step": 1,
      "title": "場景設定與情緒起點",
      "layer": "B1+C1",
      "goal": "快速建立場景，用短句開場抓住注意力",
      "action": [
        "用短句直接切入場景（時間、地點、人物）",
        "設定輕鬆或好奇的開場情緒",
        "避免冗長的背景說明"
      ],
      "ai_prompts": [
        "這個場景最吸引人的第一印象是什麼？",
        "用什麼短句能立刻讓讀者進入現場？"
      ]
    },
    {
      "step": 2,
      "title": "事件推進與細節跳接",
      "layer": "C2+B4",
      "goal": "用中長句描述關鍵事件，保持敘事節奏",
      "action": [
        "選擇2-3個關鍵事件片段",
        "用中長句描述重要細節",
        "段落間用弱連貫跳接，保持新鮮感"
      ],
      "ai_prompts": [
        "哪些細節最能體現現場的真實感？",
        "怎樣跳接能保持故事的吸引力？"
      ]
    },
    {
      "step": 3,
      "title": "詞彙生活化與感官豐富",
      "layer": "B2+B3+C4",
      "goal": "用帳號專屬詞彙和生活化比喻增強代入感",
      "action": [
        "將抽象感受轉為具體的感官描述",
        "使用帳號常用的生活化詞彙",
        "加入視覺、聽覺、觸覺等感官細節"
      ],
      "ai_prompts": [
        "這個場景有哪些獨特的感官體驗？",
        "用什麼比喻最能讓讀者感同身受？"
      ]
    },
    {
      "step": 4,
      "title": "口語化調整與節奏優化",
      "layer": "B5+C3",
      "goal": "加入口語標記，調整句子韻律",
      "action": [
        "插入「嗯」「其實」「對了」等思考標記",
        "調整句子長短，營造自然說話節奏",
        "保持輕快的整體語感"
      ],
      "ai_prompts": [
        "哪裡加入語助詞會讓語感更自然？",
        "怎樣的節奏最符合這個帳號的說話習慣？"
      ]
    },
    {
      "step": 5,
      "title": "溫暖收束與互動邀請",
      "layer": "C6",
      "goal": "用溫暖的語調收尾，邀請讀者互動",
      "action": [
        "總結現場體驗的感受",
        "用開放式問題邀請讀者分享",
        "加入帳號常用的emoji和互動語句"
      ],
      "ai_prompts": [
        "這次經歷最想和讀者分享的感受是什麼？",
        "什麼問題能引發讀者的共鳴和回應？"
      ]
    }
  ]
}
```

### 📋 模板2：評論重點型 + 慢節奏
```json
{
  "template_id": "commentary_slow",
  "suitable_for": "觀點表達、深度分析、價值思辨",
  "steps": [
    {
      "step": 1,
      "title": "議題引入與觀點預告",
      "layer": "B1+C1",
      "goal": "溫和引入議題，預告個人觀點立場",
      "action": [
        "用思考型短句開場（「我想說」「其實」）",
        "簡潔點出要討論的議題",
        "暗示個人的觀點方向"
      ],
      "ai_prompts": [
        "這個議題最觸動你的點是什麼？",
        "用什麼語氣開場最能引起讀者思考？"
      ]
    },
    {
      "step": 2,
      "title": "深度分析與論證建立",
      "layer": "C2+C5",
      "goal": "用長句進行深度分析，建立完整論證鏈",
      "action": [
        "用評論型長句表達核心觀點",
        "建立因果關係和邏輯推論",
        "使用強邏輯連貫詞（因為、所以、結果）"
      ],
      "ai_prompts": [
        "你的核心論點是什麼？有什麼證據支持？",
        "怎樣的邏輯順序最能說服讀者？"
      ]
    },
    {
      "step": 3,
      "title": "具體化與意象轉寫",
      "layer": "B2+B3",
      "goal": "將抽象觀點轉為具體可感的描述",
      "action": [
        "用帳號專屬的比喻和意象",
        "將抽象概念轉為日常生活的具體例子",
        "保持思辨的深度但增加親近感"
      ],
      "ai_prompts": [
        "這個觀點能用什麼生活例子來說明？",
        "什麼比喻最能讓讀者理解你的想法？"
      ]
    },
    {
      "step": 4,
      "title": "結構深化與層次建立",
      "layer": "B4+C5",
      "goal": "建立完整的評論結構，層次分明",
      "action": [
        "安排觀點→分析→例證→結論的結構",
        "用強邏輯連貫保持論證完整性",
        "適當插入個人經驗或感受"
      ],
      "ai_prompts": [
        "你的論證結構是否完整且有說服力？",
        "哪裡需要加入個人經驗來增強可信度？"
      ]
    },
    {
      "step": 5,
      "title": "思考標記與語感調整",
      "layer": "C3+B5",
      "goal": "加入思考過程，保持自然的語感",
      "action": [
        "插入思考標記（「嗯」「說真的」「更準確地說」）",
        "調整句子韻律，避免過於正式",
        "保持深度思考但不失親近感"
      ],
      "ai_prompts": [
        "哪裡加入思考標記能讓論述更自然？",
        "怎樣平衡深度和親近感？"
      ]
    },
    {
      "step": 6,
      "title": "開放收束與思考邀請",
      "layer": "C6",
      "goal": "開放式結尾，邀請讀者深度思考",
      "action": [
        "總結核心觀點但保留思考空間",
        "用開放式問題邀請讀者表達看法",
        "溫和收尾，避免過於強硬的結論"
      ],
      "ai_prompts": [
        "你希望讀者思考什麼問題？",
        "怎樣的結尾能引發有意義的討論？"
      ]
    }
  ]
}
```

### 📋 模板3：情感重點型 + 節奏變化
```json
{
  "template_id": "emotional_varied",
  "suitable_for": "心情抒發、感受分享、情感共鳴",
  "steps": [
    {
      "step": 1,
      "title": "情緒狀態直接表達",
      "layer": "B1+C1+C4",
      "goal": "直接表達當下情緒，用感官細節增強真實感",
      "action": [
        "用短句直接表達情緒狀態",
        "加入具體的身體感受或環境感知",
        "設定情緒的起點和可能的變化方向"
      ],
      "ai_prompts": [
        "現在最真實的感受是什麼？",
        "這種情緒在身體上有什麼感覺？"
      ]
    },
    {
      "step": 2,
      "title": "情緒探索與內心對話",
      "layer": "C2+C3",
      "goal": "深入探索情緒的來源和變化",
      "action": [
        "用長句探索情緒的深層原因",
        "加入內心對話和自我反思",
        "使用思考標記展現真實的思考過程"
      ],
      "ai_prompts": [
        "這種情緒是怎麼來的？",
        "內心深處真正想說的是什麼？"
      ]
    },
    {
      "step": 3,
      "title": "意象化與詩意表達",
      "layer": "B2+B3",
      "goal": "用詩意的語言和意象表達情感",
      "action": [
        "將情緒轉為自然意象或生活比喻",
        "使用帳號專屬的情感詞彙",
        "創造美感和共鳴"
      ],
      "ai_prompts": [
        "這種感覺像什麼？能用什麼來比喻？",
        "什麼意象最能表達你的情緒？"
      ]
    },
    {
      "step": 4,
      "title": "節奏變化與情緒起伏",
      "layer": "B5+C5",
      "goal": "用節奏變化表現情緒的起伏",
      "action": [
        "短句表達強烈情緒，長句表達複雜感受",
        "用弱連貫營造情緒的流動感",
        "適當留白讓情緒有呼吸空間"
      ],
      "ai_prompts": [
        "情緒的高低起伏是怎樣的？",
        "哪裡需要停頓讓情緒沉澱？"
      ]
    },
    {
      "step": 5,
      "title": "共鳴建立與溫暖陪伴",
      "layer": "C6",
      "goal": "與讀者建立情感共鳴，提供溫暖支持",
      "action": [
        "分享情緒體驗，邀請讀者共鳴",
        "提供溫暖的安慰或鼓勵",
        "用溫柔的語調收尾"
      ],
      "ai_prompts": [
        "你希望給有同樣感受的讀者什麼支持？",
        "怎樣的話語最能帶來溫暖？"
      ]
    }
  ]
}
```

### 📋 模板4：互動重點型 + 對話感
```json
{
  "template_id": "interactive_conversational",
  "suitable_for": "問答互動、經驗分享、社群建立",
  "steps": [
    {
      "step": 1,
      "title": "親近開場與話題引入",
      "layer": "C1+C3",
      "goal": "用親近的語調開場，自然引入話題",
      "action": [
        "用對話式短句開場（「你們有沒有...」「最近發現...」）",
        "加入口語化標記增加親近感",
        "直接點出想討論的話題"
      ],
      "ai_prompts": [
        "怎樣開場最能拉近與讀者的距離？",
        "什麼話題最能引起大家的興趣？"
      ]
    },
    {
      "step": 2,
      "title": "經驗分享與細節描述",
      "layer": "C2+C4",
      "goal": "分享個人經驗，用細節增加可信度",
      "action": [
        "用敘事型長句分享具體經驗",
        "加入感官細節讓經驗更生動",
        "保持真實和親近的語調"
      ],
      "ai_prompts": [
        "哪些個人經驗最值得分享？",
        "什麼細節最能讓讀者感同身受？"
      ]
    },
    {
      "step": 3,
      "title": "觀點表達與價值分享",
      "layer": "B1+B2",
      "goal": "表達個人觀點，但保持開放和包容",
      "action": [
        "用溫和的方式表達個人看法",
        "使用帳號專屬的價值觀詞彙",
        "避免過於強硬的立場"
      ],
      "ai_prompts": [
        "你的核心觀點是什麼？怎樣表達最合適？",
        "如何在堅持觀點的同時保持開放？"
      ]
    },
    {
      "step": 4,
      "title": "結構靈活與話題跳接",
      "layer": "B4+C5",
      "goal": "靈活組織內容，保持對話的自然感",
      "action": [
        "用弱連貫在不同話題間跳接",
        "模擬真實對話的隨意性",
        "保持內容的豐富性和趣味性"
      ],
      "ai_prompts": [
        "還有什麼相關的話題值得聊？",
        "怎樣跳接最自然？"
      ]
    },
    {
      "step": 5,
      "title": "互動邀請與社群建立",
      "layer": "C6",
      "goal": "積極邀請互動，建立社群歸屬感",
      "action": [
        "用多種方式邀請讀者參與（問題、投票、分享）",
        "表達對讀者回應的期待",
        "營造溫暖的社群氛圍"
      ],
      "ai_prompts": [
        "什麼問題最能引發熱烈討論？",
        "怎樣讓讀者感受到被重視和歡迎？"
      ]
    }
  ]
}
```

## 動態選擇邏輯

### 🤖 LLM自動選擇流程

#### 步驟1：內容分析
```json
{
  "analysis_prompt": "請分析以下原文的特徵：\n1. 主要內容類型（敘事/評論/情感/互動）\n2. 語言節奏偏好（快/慢/變化/對話）\n3. 邏輯連貫需求（強邏輯/弱連貫/敘事鏈/主題流動）\n\n原文：[插入原文]",
  "output_format": {
    "content_type": "narrative_heavy|commentary_heavy|emotional_heavy|interactive_heavy|mixed_balanced",
    "rhythm_preference": "fast_paced|slow_paced|rhythmic_varied|conversational", 
    "coherence_need": "strong_logic|weak_coherence|narrative_chain|thematic_flow",
    "recommended_template": "template_id"
  }
}
```

#### 步驟2：模板匹配
```json
{
  "matching_rules": {
    "narrative_heavy + fast_paced": "narrative_fast",
    "commentary_heavy + slow_paced": "commentary_slow", 
    "emotional_heavy + rhythmic_varied": "emotional_varied",
    "interactive_heavy + conversational": "interactive_conversational",
    "mixed_balanced + any": "custom_combination"
  }
}
```

#### 步驟3：客製化調整
```json
{
  "customization_options": {
    "step_reorder": "允許用戶調整步驟順序",
    "step_skip": "允許跳過不需要的步驟", 
    "step_merge": "允許合併相似的步驟",
    "step_add": "允許添加額外的步驟",
    "emphasis_adjust": "允許調整各步驟的重點"
  }
}
```

## 使用介面設計

### 💻 用戶操作流程

#### 1. 自動分析與推薦
```
用戶輸入原文 → LLM分析特徵 → 推薦最適合的模板 → 展示步驟組合
```

#### 2. 客製化調整
```
用戶查看推薦 → 選擇調整選項 → 修改步驟組合 → 確認最終流程
```

#### 3. 執行與優化
```
按步驟執行生成 → 檢查效果 → 調整參數 → 持續優化
```

### 🎛️ 調整選項介面

```json
{
  "adjustment_interface": {
    "template_selection": {
      "current": "narrative_fast",
      "alternatives": ["commentary_slow", "emotional_varied", "interactive_conversational"],
      "custom": "允許用戶自定義組合"
    },
    "step_modification": {
      "reorder": "拖拽調整步驟順序",
      "skip": "勾選要跳過的步驟",
      "merge": "選擇要合併的步驟",
      "emphasis": "滑桿調整各步驟權重"
    },
    "parameter_tuning": {
      "rhythm_speed": "調整整體節奏快慢",
      "coherence_strength": "調整邏輯連貫強度", 
      "emotional_intensity": "調整情感表達強度",
      "interaction_level": "調整互動邀請程度"
    }
  }
}
```

## 效果監控與優化

### 📊 效果評估指標

```json
{
  "evaluation_metrics": {
    "style_similarity": "風格相似度 (目標: >85%)",
    "content_quality": "內容品質 (目標: >8/10)",
    "user_satisfaction": "用戶滿意度 (目標: >8/10)",
    "engagement_rate": "互動率提升 (目標: >20%)"
  }
}
```

### 🔄 持續優化機制

```json
{
  "optimization_process": {
    "data_collection": "收集使用數據和用戶反饋",
    "pattern_analysis": "分析成功案例的共同模式",
    "template_update": "更新和優化模板組合",
    "parameter_adjustment": "調整推薦算法參數"
  }
}
```

這套動態B+C層步驟組合器提供了：

1. **智能推薦**：根據原文特徵自動選擇最適合的步驟組合
2. **彈性調整**：用戶可以根據需求自由調整步驟
3. **多樣選擇**：提供多種預設模板適應不同需求
4. **持續優化**：根據使用效果不斷改進推薦準確度

這樣就能實現你要求的「根據原文組合合適的步驟」且「有彈性可以變換組合方式」的目標！