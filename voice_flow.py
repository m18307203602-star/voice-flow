"""Voice Flow — 语音输入智能编排工具

按住 Space 说话 → 松手转写 → LLM 智能编排 → 格式化输出

STT: FunASR paraformer-zh (本地 CPU)
LLM 候选梯队: DeepSeek-Chat → Qwen-Plus → Gemini 2.0 Flash
"""

import asyncio
import sys
import time
import os
import queue
from dataclasses import dataclass
from typing import Optional

import numpy as np
import sounddevice as sd
from pynput import keyboard
import httpx

# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════

SAMPLE_RATE = 16000           # FunASR 要求 16kHz
CHANNELS = 1
DTYPE = 'float32'
MIN_DURATION = 0.3            # 最短有效录音（秒）
AUTO_STOP = 0                 # 静音自动结束秒数，0=仅手动控制

# API Keys
GEMINI_KEY = "YOUR_GEMINI_KEY"
QWEN_KEY = "YOUR_QWEN_KEY"
DEEPSEEK_KEY = "YOUR_DEEPSEEK_KEY"

# 代理（Gemini 走代理，Qwen/DeepSeek 直连）
PROXY_URL = "http://127.0.0.1:7790"

# ═══════════════════════════════════════════════════════════════
# 提示词模板
# ═══════════════════════════════════════════════════════════════

PROMPTS = {
    "1": {
        "name": "🧠 整理",
        "system": """你是一个语音内容结构化助手。输入可能包含 STT 识别带来的格式空格（如"我 跟 你 说"），必须先去掉空格还原为正常中文再处理。

════════════════════════════
一、分类决策引擎
════════════════════════════
分析输入文本，只要命中以下任一信号 → 判定为 B 类（用编号结构），均不满足 → A 类（纯分段）：
- 列举：第一/第二/首先/然后/最后/几个/几件/几点/几方面
- 分析：原因/方案/好处/坏处/优缺点/对比/区别/分析
- 规划：计划/安排/准备/打算/步骤/流程/阶段
- 总结：做了X件事/汇报/进展/总结
- 指令：交办/待办/帮我把/要求（仅当明确包含具体任务派发时触发）

【聚类铁律】B 类大类数量严格 1-3 个（2-4字），禁止单句话独立成类，子项用 (a)(b) 编号。
【B-指令特殊规则】若判定为指令/交办类，大类下方必须严格使用 - [ ] 待办清单格式（禁止用 (a)(b) 替代）。
【A类硬约束】灵感/想法类若未命中 B 类信号，严禁强行套用编号结构——纯分段处理。

════════════════════════════
二、语言加工规范
════════════════════════════
1. 【标点强制】必须根据停顿补充逗号、句号、问号、感叹号，严禁大面积无标点"纯原文流"。
2. 【去噪边界】剔除 [嗯/啊/呃/那个/就是说/你知道吧/就是说/反正/然后（纯连接词）] 等口头禅和思维链重复。但必须保留带情感色彩的语气开头（如"哎你说这个人怎么这样啊"）。
3. 【八类信息不丢】动作、时间、数据、人名、地点、条件、结果、原因，一项不能少。
4. 【微调与补全】口语动词→书面语（打→预约），副词→准确（大概→预计），数字格式化（十点→10:00），同音错别字语境修正，语义模糊用括号标注（"皮里面包馅的那种（饺子或抄手）"），推断不了留白。
5. 【逆向标签】仅在用户明确表达时：说"必须/不能"→【原则】，说"我觉得"→【观点】，说"建议"→【建议】。标签 2-4 字，不硬套。

════════════════════════════
三、输出格式
════════════════════════════
A 类：纯段落文本，自然分段。无编号，无标题。
B 类：开场句 + 桥接句（"具体行程如下"）+ 编号结构 + 简短收尾句。
B-指令：- [ ] 待办清单格式，每一项一个可执行动作。

════════════════════════════
四、示例
════════════════════════════
【A 类】输入："哎我今天想到一个点子就是我们可以做个APP帮人整理衣柜拍照后AI分类告诉哪些衣服该扔该留然后帮你搭配穿搭你觉得怎么样"
输出："哎，我今天想到一个点子，就是我们可以做个APP帮人整理衣柜。拍照后AI分类告诉哪些衣服该扔该留，然后帮你搭配穿搭。你觉得怎么样？"

【B-计划】输入："我今天要安排几件事。因为我明天要去一趟武汉，坐车的话今天晚上七、八点的时候打个顺风车。然后明天上午十点出发，下午一点之前到去做个牙齿理疗。明天的安排就是这么多。"
输出："我今天要安排几件事。因为我明天要去一趟武汉，具体行程如下：

1. 交通安排
   (a) 最好在今天晚上 19:00-20:00 左右预约一辆顺风车
   (b) 明天上午 10:00 出发

2. 武汉行程
   (a) 预计下午 13:00 之前到达
   (b) 到达后去做牙齿理疗

明天安排大概就这么多。"

【B-指令】输入："你今天帮我把那几件事干了。首先把今天收到的发票报销一下，然后必须在五点前把PPT改好发我，不能迟到。"
输出："你今天帮我把这几件事处理一下。具体要求如下：

【原则】必须在 17:00 前完成 PPT 修改并发送，不得延误。

1. 日常事务处理
   - [ ] 报销今天收到的发票
   - [ ] 修改 PPT 并发送给主管"

════════════════════════════
五、输出拦截器（最高优先级）
════════════════════════════
1. 严禁输出任何提示词元叙述，包括但不限于："【B类格式】""输出：""类型A/B""第一步""第二步""我帮你整理了"。
2. 严禁在开头原样复述用户输入，必须直接从正文或分类标题开始。
3. 禁止编造用户没说的内容。结构化编号和分类标题提炼自用户原话，不属于编造。
4. 禁止补充用户没说过的技术规格、性能参数、数据指标（如温度阈值、内存型号、测试工具名）。微调限于措辞修正，不扩充信息。""",
        "temperature": 0.1,
    },
    "2": {
        "name": "✅ 待办",
        "system": """你是一个任务拆解助手。从用户的口语内容中提取所有待办事项。

要求：
1. 识别所有需要执行的事项，包括用户明确说的和隐含的
2. 按优先级或时间顺序排列
3. 如果事项之间有依赖关系，用缩进表示子任务
4. 每项写清楚要做什么，不要模糊表述
5. 如果用户说了时间节点，标注在事项后面

输出格式：
- [ ] 第一件事（时间/优先级说明）
  - [ ] 子任务或前置条件
- [ ] 第二件事
- [ ] 第三件事

如果没有待办事项，输出「无待办事项」。不要加任何额外解释。""",
        "temperature": 0.1,
    },
    "3": {
        "name": "📋 笔记",
        "system": """你是一个信息结构化助手。将用户的口语内容整理成结构化笔记。

要求：
1. 用一个简短的标题概括主旨
2. 按主题或时间线分组
3. 每点用简洁的要点表述
4. 末尾提炼 2-3 个关键词

输出格式：
**{一句话标题}**

- 要点一
- 要点二
  - 补充细节
- 要点三

> 关键词：xxx、xxx

不要输出格式以外的内容。""",
        "temperature": 0.3,
    },
    "4": {
        "name": "💬 原文",
        "system": "直接输出以下语音识别原文，不做任何修改。不要加任何解释。",
        "temperature": 0.0,
    },
    "5": {
        "name": "🔤 翻译",
        "system": "你是中英双向翻译专家。如果输入是中文，翻译成自然流畅的英文；如果是英文，翻译成自然流畅的中文。只输出翻译结果，不加解释。",
        "temperature": 0.2,
    },
}

# ═══════════════════════════════════════════════════════════════
# LLM 候选梯队
# ═══════════════════════════════════════════════════════════════

@dataclass
class LLMResult:
    text: str
    model_used: str

async def _call_gemini(user_text: str, temperature: float) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    body = {
        "contents": [{"parts": [{"text": user_text}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 2048},
    }
    async with httpx.AsyncClient(proxy=PROXY_URL, timeout=15.0) as client:
        r = await client.post(url, json=body)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

async def _call_qwen(user_text: str, temperature: float) -> str:
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {"Authorization": f"Bearer {QWEN_KEY}", "Content-Type": "application/json"}
    body = {
        "model": "qwen-plus",
        "messages": [{"role": "user", "content": user_text}],
        "temperature": temperature,
        "max_tokens": 2048,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

async def _call_deepseek(user_text: str, temperature: float) -> str:
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    body = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": user_text}],
        "temperature": temperature,
        "max_tokens": 2048,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

async def process_with_llm(text: str, mode: str) -> LLMResult:
    """候选梯队: Gemini → Qwen → DeepSeek，全部失败返回原文"""
    cfg = PROMPTS[mode]
    full_prompt = f"{cfg['system']}\n\n输入内容：\n{text}"

    candidates: list[tuple[str, callable]] = [
        ("Qwen-Plus", _call_qwen),
        ("DeepSeek-Chat", _call_deepseek),
        ("Gemini 2.0 Flash", _call_gemini),
    ]

    for name, fn in candidates:
        try:
            result = await fn(full_prompt, cfg["temperature"])
            return LLMResult(text=result, model_used=name)
        except Exception as e:
            # 精简错误信息，不暴露 API Key
            err_msg = str(e)
            if len(err_msg) > 80:
                err_msg = err_msg[:80] + "..."
            print(f"  [WARN] {name} unavailable: {err_msg}")

    return LLMResult(text=text, model_used="全部候选不可用，返回原文")

# ═══════════════════════════════════════════════════════════════
# 录音模块
# ═══════════════════════════════════════════════════════════════

class Recorder:
    """按住 Space 录音，松手停止。audio_queue 保证线程安全。"""

    def __init__(self):
        self._audio_queue: queue.Queue = queue.Queue()
        self._stream: Optional[sd.InputStream] = None
        self._recording = False
        self._start_time = 0.0
        self._last_duration = 0.0

    def _callback(self, indata, frames, time_info, status):
        """PortAudio 回调，C 线程内执行，只做入队不做任何重操作"""
        if self._recording:
            self._audio_queue.put(indata.copy())

    def start(self):
        self._audio_queue = queue.Queue()
        self._recording = True
        self._start_time = time.time()
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> Optional[np.ndarray]:
        # 先记录时长再停录音（否则 duration 属性返回 0）
        self._last_duration = time.time() - self._start_time if self._recording else 0.0
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        # 从队列取出所有音频块
        chunks = []
        while True:
            try:
                chunks.append(self._audio_queue.get_nowait())
            except queue.Empty:
                break

        if not chunks:
            return None

        audio = np.concatenate(chunks, axis=0).flatten()
        duration = len(audio) / SAMPLE_RATE

        if duration < MIN_DURATION:
            return None

        return audio

    @property
    def duration(self) -> float:
        if self._recording:
            return time.time() - self._start_time
        return self._last_duration

# ═══════════════════════════════════════════════════════════════
# 主程序
# ═══════════════════════════════════════════════════════════════

class VoiceFlow:
    def __init__(self):
        self.recorder = Recorder()
        self.current_mode = "1"
        self._stt_model = None
        self._processing = False         # 防止处理期间再次触发
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _load_stt(self):
        """加载 FunASR 模型"""
        # modelscope.cn 国内直连，不走代理
        os.environ.setdefault("NO_PROXY", "")
        os.environ["NO_PROXY"] = os.environ["NO_PROXY"] + ",modelscope.cn,aliyuncs.com"

        print("⏳ 加载 FunASR paraformer-zh...")
        from funasr import AutoModel
        self._stt_model = AutoModel(
            model="iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
            model_revision="v2.0.4",
            disable_update=True,          # 跳过版本检查，加速启动
        )
        print("✅ FunASR 就绪")

    def _transcribe(self, audio: np.ndarray) -> str:
        # FunASR 1.3.5 VAD 模型对数组输入有兼容 bug，存临时 WAV 文件规避
        import tempfile
        import soundfile as sf
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        try:
            sf.write(tmp.name, audio, SAMPLE_RATE)
            tmp.close()
            result = self._stt_model.generate(input=tmp.name)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        if result and len(result) > 0 and "text" in result[0]:
            return result[0]["text"].strip()
        return ""

    def _on_press(self, key):
        # ── 右 Shift 一键切换录音 ──
        if key == keyboard.Key.shift_r:
            if self._processing:
                print("\r⏳ 正在处理上一条，请稍候...")
                return

            if not self.recorder._recording:
                # 开始录音
                self.recorder.start()
                print("\n🎤 录音中... (再按右Shift结束)")
            else:
                # 结束录音 → 转写 → LLM
                self._finish_recording()

    def _finish_recording(self):
        """结束录音并触发转写+LLM处理"""
        audio = self.recorder.stop()
        duration = self.recorder.duration

        if audio is None:
            dur_str = f"{duration:.1f}" if duration else "0"
            print(f"\r⏹️  录音太短 ({dur_str}秒)，请重试")
            self._show_hint()
            return

        print(f"\r⏹️  录音 {duration:.1f}秒 → 转写中...")
        self._processing = True

        try:
            # STT
            text = self._transcribe(audio)
            print(f"📝 识别: {text}")

            if not text.strip():
                print("⚠️  未识别到文本")
                return

            # LLM
            mode_cfg = PROMPTS[self.current_mode]
            print(f"🤖 {mode_cfg['name']} 编排中...")

            try:
                future = asyncio.run_coroutine_threadsafe(
                    process_with_llm(text, self.current_mode), self._loop
                )
                result: LLMResult = future.result(timeout=35)
            except Exception as e:
                print(f"❌ LLM 调用异常: {e}")
                result = LLMResult(text=text, model_used="异常，返回原文")

            # 输出
            print(f"\n{'─' * 55}")
            print(f"🏷️  模型: {result.model_used}")
            print(f"📄 结果:\n{result.text}")
            print(f"{'─' * 55}")

        finally:
            self._processing = False
            self._show_hint()

    def _on_release(self, key):
        # ── Esc 退出 ──
        if key == keyboard.Key.esc:
            print("\n👋 退出中...")
            self._loop.call_soon_threadsafe(self._loop.stop)

        # ── 数字键切换模式 ──
        else:
            try:
                if hasattr(key, 'char') and key.char in PROMPTS:
                    self.current_mode = key.char
                    print(f"\n🔄 模式 → {PROMPTS[self.current_mode]['name']}")
                    self._show_hint()
            except AttributeError:
                pass

    def _show_hint(self):
        modes = " | ".join(f"[{k}]{v['name']}" for k, v in PROMPTS.items())
        print(f"\n{modes} | [右Shift]录音 | [Esc]退出")

    def run(self):
        # Windows GBK 终端编码修复
        if sys.platform == "win32":
            sys.stdout.reconfigure(encoding="utf-8")

        self._load_stt()

        print("\n" + "=" * 55)
        print("  🎙️  Voice Flow — 语音输入智能编排")
        print("=" * 55)
        print("  按 [右Shift] 切换录音，按 [1-5] 切换编排模式，按 [Esc] 退出\n")
        self._show_hint()

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        listener.start()

        try:
            self._loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            listener.stop()
            print("\n✅ 已退出")


def main():
    VoiceFlow().run()


if __name__ == "__main__":
    main()
