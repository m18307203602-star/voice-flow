"""PROMPTS — 提示词元数据（系统提示词从服务器拉取，不存本地）"""

PROMPTS = {
    "1": {
        "name": "中英文（推荐）",
        "temperature": 0.1,
        "system": "",  # 从服务器拉取
    },
    "2": {
        "name": "纯英文",
        "temperature": 0.1,
        "system": "",  # 从服务器拉取
    },
    "3": {
        "name": "纯中文",
        "temperature": 0.1,
        "system": "",  # 从服务器拉取
    },
    "4": {
        "name": "文采",
        "temperature": 0.2,
        "system": "",  # 从服务器拉取
    },
    "5": {
        "name": "情感",
        "temperature": 0.2,
        "system": "",  # 从服务器拉取
    },
    "6": {
        "name": "代码",
        "temperature": 0.1,
        "system": "",  # 从服务器拉取
    },
}

# ═══════════════════════════════════════════════════════════════════
# 多引擎转录合成（短 prompt，保留本地 — 不以独立模式展示给用户）
# ═══════════════════════════════════════════════════════════════════
SYNTHESIS_PROMPTS = {
    "1": """你是转录合成专家。对比多份语音转写结果，输出最优合成文本。

第一层：多数投票 — 同一位置两份一致一份不同→取多数派；三份都不同→取语义最通顺的
第二层：语义终审 — 多数派合理→采用；多数派不合理→检查少数派，合理则采用
第三层：自行纠错 — 都不合理→用中文理解能力+常见STT同音错误推断原文；必须有上下文依据，不确定时括号标注

引擎数：2引擎→一致采用/分歧取合理方并标注【A或B】；3引擎→完整三层

严禁输出评估过程、投票细节、编号标签。只输出合成后的最终文本。格式空格先还原为正常中文。""",
    "2": """You are a transcript synthesizer. Compare multiple ASR transcripts and output the single most accurate version.

Layer 1: Majority Voting — Two agree/one differs → adopt majority. All differ → adopt semantically most coherent.
Layer 2: Semantic Review — Majority reasonable → adopt. If not, check minority; adopt if reasonable.
Layer 3: Self-Correction — All unreasonable → infer using language understanding + ASR homophone errors. Ground in context, never fabricate.

Engine count: 2 → adopt if consistent; if divergent, choose more reasonable, mark [A or B]. 3 → full three-layer.

NEVER output evaluation process, voting details, transcript labels. Output ONLY the final synthesized text.""",
}
