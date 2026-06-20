"""翻译引擎 — 语言检测 + LLM 逐行对照翻译"""
import asyncio
import logging
import re

from .llm import LLMProcessor

log = logging.getLogger("voice_flow.translator")

# 翻译系统 Prompt 模板
TRANSLATE_PROMPT = """你是专业翻译引擎。严格按以下规则输出：

1. 将原文按句号、问号、感叹号、换行符拆分为独立句子
2. 每个句子翻译为{target_lang}
3. 严格逐行对照输出，原文一行、译文一行交替排列，无需任何标签或前缀，格式如下：

中文句子一
English translation of sentence one

中文句子二
English translation of sentence two

4. 修正原文中明显的语法、拼写错误（如 "take a week" → "take a walk"），但不得增删中文原意或添加未提及信息
5. 译文必须语法正确、语义准确、自然流畅
6. 只输出翻译结果，不要添加任何额外说明、标签或前缀"""

# 纯英文输出 Prompt（模式4：整理→翻译一体化，最终只输出英文）
# 保留原文编号/标签/结构，翻译为优雅地道的英文，不附加中文原文
TRANSLATE_PROMPT_ENGLISH_ONLY = """你是顶级英文翻译与文体大师。你将收到已整理好的中文文本。
请严格按以下规则翻译为{target_lang}：

【翻译标准 — 优雅 / 高贵 / 地道 / 正宗】
1. 语法：使用正宗标准英语语法（Standard English），杜绝中式英语（Chinglish）
2. 用词：选用精准、优雅、有质感的词汇。避免生硬直译、避免过于口语化。追求《经济学人》《纽约客》级别的书面英文质感
3. 句式：自然流畅的英语句式，适当变换句型（简单句/复合句/从句），避免全部用"I did A. I did B."的单调结构
4. 地道性：表达方式符合英语母语者的思维习惯，不是中文的逐字翻译。比如中文"具体如下"→ 自然处理为段落逻辑，而非硬译成 "specifically as follows"
5. 高贵感：避免俚语、避免过于随意的缩写（如 gonna/wanna），保持正式但不僵硬、优雅但不做作

【结构保留】
6. 完整保留原文的所有结构：段落、编号（1. 2. (a) (b) 等）、标签
7. 中文方括号标签翻译为英文（如【原则】→ [Principle]，【建议】→ [Suggestion]）
8. 中文分类标题翻译为英文（如"日常采购"→ "Daily Shopping"）

【输出约束】
9. 纯英文输出，不加中文原文、不加双语对照、不加任何解释
10. 只输出最终的英文翻译结果"""


class TranslationEngine:
    """翻译引擎 — 复用 LLM 三级降级链，输出逐行对照格式"""

    CJK_RE = re.compile(r'[一-鿿㐀-䶿豈-﫿]')

    def __init__(self, config):
        self._config = config

    def _build_llm(self):
        return LLMProcessor(
            qwen_key=self._config.qwen_key,
            deepseek_key=self._config.deepseek_key,
            gemini_key=self._config.gemini_key,
            mimo_key=self._config.mimo_key,
            proxy_url=self._config.proxy_url,
        )

    def detect_language(self, text: str) -> str:
        """检测文本主要语言。返回 'zh' 或 'en'"""
        cjk_count = len(self.CJK_RE.findall(text))
        alpha_count = len(re.findall(r'[a-zA-Z]', text))
        return 'zh' if cjk_count >= alpha_count else 'en'

    def translate(self, text: str, source_lang: str = "auto",
                  target_lang: str = "auto", english_only: bool = False) -> str:
        """同步翻译入口（内部 asyncio 执行）

        Args:
            text: 待翻译文本
            source_lang: 源语言，"auto" / "中文" / "English" / 自定义
            target_lang: 目标语言，"auto" / "中文" / "English" / 自定义
            english_only: True=纯英文输出（保留结构），False=逐行双语对照

        Returns:
            翻译结果
        """
        # ── 语言检测 ──
        if source_lang == "auto":
            detected = self.detect_language(text)
        else:
            detected = "zh" if "中" in source_lang else "en"

        if target_lang == "auto":
            target = "English" if detected == "zh" else "中文"
        else:
            target = target_lang

        # ── 构建 Prompt（english_only 模式用纯英文输出模板） ──
        if english_only:
            system = TRANSLATE_PROMPT_ENGLISH_ONLY.format(target_lang=target)
        else:
            system = TRANSLATE_PROMPT.format(target_lang=target)
        full_prompt = f"{system}\n\n待翻译内容：\n{text}"

        # ── LLM 三级降级（同步包装） ──
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self._translate_with_fallback(full_prompt))
        finally:
            loop.close()

        return result

    async def _translate_with_fallback(self, full_prompt: str) -> str:
        """LLM 三级降级调用"""
        llm = self._build_llm()

        candidates = [
            ("Qwen-Plus", llm._call_qwen),
            ("DeepSeek-Chat", llm._call_deepseek),
            ("Gemini 2.0 Flash", llm._call_gemini),
        ]

        for name, fn in candidates:
            try:
                log.info("翻译: 尝试 %s ...", name)
                result, _ = await fn(full_prompt, temperature=0.3)
                log.info("翻译: %s 成功 (%d 字)", name, len(result))
                return result
            except Exception as e:
                log.warning("翻译: %s 不可用 (%s)", name, str(e)[:80])

        log.error("翻译: 全部 LLM 不可用")
        return full_prompt  # 兜底返回原文
