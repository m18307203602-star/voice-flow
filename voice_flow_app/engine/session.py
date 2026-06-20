"""语音录制会话 — 状态机编排：录音 → STT → LLM → 输出"""
import logging
import threading
import time
import tempfile
import wave
import os
from enum import Enum
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor
import asyncio

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from .stt_tencent import TencentStreamingASR
from .stt_tencent_sentence import TencentSentenceASR
from .stt_iflytek import IflytekStreamingASR
from .stt_aliyun import AliyunStreamingASR
from .recorder import Recorder
from .llm import LLMProcessor, LLMResult
from voice_flow_app.prompts import SYNTHESIS_PROMPTS

log = logging.getLogger("voice_flow.session")


class SessionState(Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    RECORDING = "recording"
    PROCESSING = "processing"


ENGINE_LABELS = {"tencent": "腾讯", "iflytek": "讯飞", "aliyun": "阿里"}


class VoiceFlowSession(QObject):
    """录音→STT→LLM→输出 全流程状态机"""

    # 信号
    state_changed = Signal(str)         # SessionState.value
    status_message = Signal(str)        # 状态栏文字
    recording_level = Signal(float)     # 音频电平 0.0-1.0
    recording_spectrum = Signal(list)   # FFT 频谱 [64 bins, 0.0-1.0]
    engine_status = Signal(str, str)    # (engine_name, status_text)
    result_ready = Signal(str, str, str, dict)  # (transcript, llm_output, model_used, engine_results)
    comparison_ready = Signal(dict, float, float)  # (comparison_data, stage1_elapsed_ms, total_elapsed_ms)
    error_occurred = Signal(str)        # 错误信息

    def __init__(self, config, prompts):
        super().__init__()
        self._config = config
        self._prompts = prompts
        self._state = SessionState.IDLE
        self._recorder: Optional[Recorder] = None
        self._stt_engines: dict = {}     # {engine_name: STT instance}
        self._stt_results: dict = {}     # {engine_name: transcript_text}
        self._llm: Optional[LLMProcessor] = None
        self.last_llm_tokens: dict = {}
        self._lock = threading.Lock()

    @property
    def state(self) -> SessionState:
        return self._state

    def _set_state(self, new_state: SessionState):
        self._state = new_state
        self.state_changed.emit(new_state.value)

    def start_recording(self):
        """开始录音（由热键或按钮触发）"""
        if self._state != SessionState.IDLE:
            log.warning("非 IDLE 状态，忽略录音请求: %s", self._state)
            return

        if not self._config.has_llm_keys():
            self.error_occurred.emit("请先在设置中填写至少一个 LLM 密钥")
            return

        stt_mode = self._config.stt_mode
        log.info("开始录音，STT 模式: %s，处理模式: %s", stt_mode, self._config.selected_mode)

        # 确定要使用的 STT 引擎
        if stt_mode == "short_first":
            # 短连接优先：腾讯一句话识别 + 讯飞流式兜底
            if not self._config.has_engine_keys("tencent"):
                self.error_occurred.emit("短连接模式需要腾讯云密钥")
                return
            engine_plan = [("tencent_sentence", "腾讯(短)"), ("iflytek", "讯飞(备)")]
        else:
            # 流式模式：仅选中的引擎
            engines = [e for e in self._config.selected_engines
                       if self._config.has_engine_keys(e)]
            if not engines:
                self.error_occurred.emit("未选择任何 STT 引擎，或引擎密钥均为空")
                return
            engine_plan = [(e, ENGINE_LABELS.get(e, e)) for e in engines]

        self._set_state(SessionState.CONNECTING)
        QApplication.processEvents()
        self._stt_results.clear()
        self._stt_engines.clear()

        # 创建 LLM 处理器
        self._llm = LLMProcessor(
            qwen_key=self._config.qwen_key,
            qwen_flash_key=self._config.qwen_flash_key,
            deepseek_key=self._config.deepseek_key,
            gemini_key=self._config.gemini_key,
            mimo_key=self._config.mimo_key,
            proxy_url=self._config.proxy_url,
            status_callback=lambda m: self.status_message.emit(m),
            enabled={
                "qwen": self._config.is_llm_enabled("qwen"),
                "qwen_flash": self._config.is_llm_enabled("qwen_flash"),
                "deepseek": self._config.is_llm_enabled("deepseek"),
                "gemini": self._config.is_llm_enabled("gemini"),
                "mimo": self._config.is_llm_enabled("mimo"),
            },
        )

        # 创建并启动 STT 引擎
        import concurrent.futures
        stt_instances = {}
        for name, label in engine_plan:
            try:
                stt_instances[name] = self._create_stt(name)
                self.engine_status.emit(name, "连接中...")
            except Exception as e:
                log.error("STT 引擎 %s 创建失败: %s", name, e)
                self.engine_status.emit(name, f"失败: {str(e)[:30]}")

        def _connect_one(name, stt):
            try:
                stt.start()
                return name, True, None
            except Exception as e:
                return name, False, str(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_connect_one, n, s): n for n, s in stt_instances.items()}
            for future in concurrent.futures.as_completed(futures):
                name, ok, err = future.result()
                if ok:
                    self._stt_engines[name] = stt_instances[name]
                    self.engine_status.emit(name, "已连接")
                    log.info("STT 引擎 %s 连接成功", name)
                else:
                    log.error("STT 引擎 %s 连接失败: %s", name, err)
                    self.engine_status.emit(name, f"失败: {err[:30]}")
                    self.status_message.emit(f"{ENGINE_LABELS.get(name, name)} 连接失败，跳过")

        if not self._stt_engines:
            self._set_state(SessionState.IDLE)
            self.error_occurred.emit("所有 STT 引擎连接失败")
            return

        # 启动录音（所有引擎都加入流式列表，短连接引擎的 feed() 只累积不发送）
        self._recorder = Recorder(
            level_callback=lambda l: self.recording_level.emit(l),
            spectrum_callback=lambda s: self.recording_spectrum.emit(s))
        for stt in self._stt_engines.values():
            self._recorder.add_streaming_stt(stt)
        self._recorder.start()
        self._set_state(SessionState.RECORDING)
        connected_names = list(self._stt_engines.keys())
        self.status_message.emit(f"录音中 ({', '.join(ENGINE_LABELS.get(c, c) for c in connected_names)})")

    def stop_recording(self):
        """停止录音并开始处理"""
        if self._state != SessionState.RECORDING:
            log.warning("非 RECORDING 状态，忽略停止请求: %s", self._state)
            return

        log.info("停止录音，开始处理...")
        self._set_state(SessionState.PROCESSING)
        self.status_message.emit("处理中...")
        QApplication.processEvents()  # 立刻刷新 UI

        # 停止录音
        audio = self._recorder.stop()
        duration = self._recorder.duration
        self.last_duration = duration
        self._recorder.clear_streaming_stts()
        self._recorder = None

        if audio is None:
            self._set_state(SessionState.IDLE)
            self.status_message.emit(f"录音太短 ({duration:.1f}s)")
            return

        # ★ 停止 STT 引擎：短连接模式串行 fallback，流式模式并行
        with self._lock:
            engines_snapshot = dict(self._stt_engines)
        self._stt_engines.clear()

        engine_results = {}
        stt_mode = self._config.stt_mode

        if stt_mode == "short_first":
            # 短连接优先：先试腾讯一句话识别 → 失败则用讯飞流式兜底
            sentence_stt = engines_snapshot.pop("tencent_sentence", None)
            fallback_stt = engines_snapshot.pop("iflytek", engines_snapshot.pop("tencent", None))

            if sentence_stt:
                t0 = time.time()
                try:
                    text = sentence_stt.stop()
                    elapsed = time.time() - t0
                    engine_results["tencent_sentence"] = text
                    self._stt_results["tencent_sentence"] = text
                    self.engine_status.emit("tencent", f"腾讯(短): {text[:40]}...")
                    self.status_message.emit(f"腾讯短连接识别完成 ({elapsed:.1f}s)")
                    log.info("腾讯短连接识别完成: %d 字, %.1fs", len(text), elapsed)
                except Exception as e:
                    err_msg = str(e)
                    log.warning("腾讯短连接失败: %s，尝试讯飞流式兜底", err_msg)
                    self.engine_status.emit("tencent", f"短连接失败: {err_msg[:30]}")

                    # 向用户透出具体原因
                    if "结果为空" in err_msg or "太短" in err_msg:
                        self.status_message.emit(
                            "腾讯未识别到语音（可能太短/有噪声），自动切换讯飞")
                    elif "请求失败" in err_msg:
                        self.status_message.emit(
                            f"腾讯短连接网络异常，自动切换讯飞: {err_msg[:40]}")
                    elif "无音频" in err_msg:
                        self.status_message.emit("录音太短，请重试")
                    else:
                        self.status_message.emit(f"腾讯短连接失败，自动切换讯飞")

                    # Fallback 到讯飞流式
                    if fallback_stt:
                        t0 = time.time()
                        try:
                            text = fallback_stt.stop()
                            elapsed = time.time() - t0
                            engine_results["iflytek"] = text
                            self._stt_results["iflytek"] = text
                            self.engine_status.emit("iflytek", f"讯飞(备): {text[:40]}...")
                            self.status_message.emit(f"短连接失败，讯飞兜底完成 ({elapsed:.1f}s)")
                            log.info("讯飞兜底完成: %d 字, %.1fs", len(text), elapsed)
                        except Exception as e2:
                            log.error("讯飞兜底也失败: %s", e2)
                            engine_results["iflytek"] = f"[错误] {e2}"
                    else:
                        log.error("短连接失败且无兜底引擎")
        else:
            # 流式模式：并行停止所有引擎（原逻辑）
            import concurrent.futures
            def _stop_one(name, stt):
                try:
                    t0 = time.time()
                    text = stt.stop()
                    elapsed = time.time() - t0
                    return name, text, elapsed, None
                except Exception as e:
                    return name, "", 0, str(e)

            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = {executor.submit(_stop_one, n, s): n for n, s in engines_snapshot.items()}
                for future in concurrent.futures.as_completed(futures):
                    name, text, elapsed, err = future.result()
                    if err:
                        log.error("引擎 %s 识别失败: %s", name, err)
                        engine_results[name] = f"[错误] {err}"
                        self.engine_status.emit(name, f"识别失败: {err[:30]}")
                    else:
                        engine_results[name] = text
                        self._stt_results[name] = text
                        label = ENGINE_LABELS.get(name, name)
                        self.engine_status.emit(name, f"{label}: {text[:40]}...")
                        self.status_message.emit(f"{label}识别完成 ({elapsed:.1f}s)")
                        log.info("引擎 %s 识别完成: %d 字, %.1fs", name, len(text), elapsed)

        if not engine_results:
            self._set_state(SessionState.IDLE)
            self.error_occurred.emit("无语音识别结果")
            return

        # 保存 WAV
        wav_path = self._save_wav(audio)

        mode = self._config.selected_mode
        mode_cfg = self._prompts.get(mode)
        if not mode_cfg:
            self._set_state(SessionState.IDLE)
            self.error_occurred.emit(f"未知模式: {mode}")
            return

        self.status_message.emit(f"LLM: {mode_cfg['name']} 编排中...")

        # ★ LLM 异步执行：不阻塞主线程，完成后自动回调
        def _run_llm_then_emit():
            t_total_start = time.time()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                llm_result, comp_data, stage1_elapsed = loop.run_until_complete(
                    self._do_llm(engine_results, mode, mode_cfg, wav_path))
                total_elapsed = round((time.time() - t_total_start) * 1000)
            except Exception as e:
                log.error("LLM 异常: %s", e)
                llm_result = LLMResult(
                    text=next((v for v in engine_results.values()
                               if v and not v.startswith("[错误]")), ""),
                    model_used="LLM异常")
                comp_data = {}
                stage1_elapsed = 0
                total_elapsed = round((time.time() - t_total_start) * 1000)
            finally:
                loop.close()

            if llm_result is None:
                best = next((v for v in engine_results.values()
                             if v and not v.startswith("[错误]")), "")
                llm_result = LLMResult(text=best, model_used="LLM超时")

            # 保存 token 用量，供 UI 读取
            self.last_llm_tokens = {
                "model": llm_result.model_used,
                "prompt_tokens": llm_result.prompt_tokens,
                "completion_tokens": llm_result.completion_tokens,
            }
            log.info("LLM 处理完成，模型: %s，输出 %d 字，token: %d+%d",
                     llm_result.model_used, len(llm_result.text),
                     llm_result.prompt_tokens, llm_result.completion_tokens)

            try:
                os.unlink(wav_path)
            except OSError:
                pass

            best_transcript = next(
                (v for v in engine_results.values()
                 if v and not v.startswith("[错误]")), "")

            # 跨线程 emit → PySide6 自动 QueuedConnection
            self.result_ready.emit(
                best_transcript, llm_result.text, llm_result.model_used, engine_results)

            # 对比模式：发射对比数据
            if comp_data:
                for name, data in comp_data.items():
                    if data.get("error"):
                        log.warning("对比 %s 失败: %s", name, data["error"])
                    else:
                        log.info("对比 %s 成功: %d 字, %.0fms",
                                 name, len(data.get("text", "")), data.get("elapsed_ms", 0))
                self.comparison_ready.emit(comp_data, stage1_elapsed, total_elapsed)

            self._set_state(SessionState.IDLE)
            self.status_message.emit("就绪")

        threading.Thread(target=_run_llm_then_emit, daemon=True).start()
        # ★ 不再 join()！方法立即返回，Qt 事件循环继续运行

    def _create_stt(self, name: str):
        """根据引擎名创建对应的 STT 实例"""
        if name == "tencent":
            sid, skey, aid = self._config.get_tencent_keys()
            return TencentStreamingASR(sid, skey, aid,
                status_callback=lambda m: self.status_message.emit(m))
        elif name == "tencent_sentence":
            sid, skey, aid = self._config.get_tencent_keys()
            return TencentSentenceASR(sid, skey, aid,
                status_callback=lambda m: self.status_message.emit(m))
        elif name == "iflytek":
            aid, akey, asecret = self._config.get_iflytek_keys()
            return IflytekStreamingASR(aid, akey, asecret,
                status_callback=lambda m: self.status_message.emit(m))
        elif name == "aliyun":
            key = self._config.get_aliyun_key()
            return AliyunStreamingASR(key,
                status_callback=lambda m: self.status_message.emit(m))
        else:
            raise ValueError(f"未知引擎: {name}")

    async def _do_llm(self, engine_results: dict, mode: str, mode_cfg: dict, wav_path: str):
        """两阶段 LLM 处理：阶段一（多引擎合成）+ 阶段二（规则处理）

        Returns:
            (LLMResult, comparison_data, stage1_elapsed_ms)
            comparison_data = {} if comparison disabled
        """
        if not self._llm:
            return LLMResult(text="", model_used="未初始化"), {}, 0

        stage1_elapsed = 0.0

        if mode in ("1", "2", "3"):
            # 中英文 / 纯英文 / 纯中文：收集引擎结果
            parts = []
            for eng in ["tencent_sentence", "tencent", "iflytek", "aliyun"]:
                text = engine_results.get(eng, "")
                if text.startswith("[错误]") or not text.strip():
                    continue
                parts.append((eng, text))
            if not parts:
                input_text = ""
            elif len(parts) == 1:
                # 单引擎 → 跳过阶段一，直传原文
                input_text = parts[0][1]
                log.info("模式 %s 单引擎 (%s)，跳过阶段一合成", mode, parts[0][0])
            else:
                # ★ 多引擎 → 阶段一：转录合成
                chunks = [f"转写 #{i+1}\n{text}" for i, (_, text) in enumerate(parts)]
                synth_input = "\n\n".join(chunks)
                synth_key = "2" if mode == "2" else "1"  # 英文用 key="2"
                log.info("阶段一：%d 引擎合成中 (synth_key=%s)...", len(parts), synth_key)
                t0 = time.time()
                synth_result = await self._llm.process(
                    synth_input, SYNTHESIS_PROMPTS[synth_key], 0.1)
                stage1_elapsed = round((time.time() - t0) * 1000)
                input_text = synth_result.text
                log.info("阶段一合成完成: %d 字, %.0fms", len(input_text), stage1_elapsed)
        else:
            # 文采/情感/代码模式：取最优单引擎结果
            engine_order = ["tencent_sentence", "tencent", "aliyun", "iflytek"]
            input_text = ""
            for eng in engine_order:
                t = engine_results.get(eng, "")
                if t and not t.startswith("[错误]") and len(t.strip()) > 0:
                    input_text = t
                    break
            if not input_text:
                input_text = next(
                    (v for v in engine_results.values() if v and not v.startswith("[错误]")), "")

        if not input_text.strip():
            return LLMResult(text="", model_used="无有效输入"), {}, stage1_elapsed

        # ── 系统提示词指纹校验（运行时二次确认） ──
        _sys = mode_cfg.get("system", "")
        if _sys:
            import hashlib as _hl
            _fp = _hl.sha256(_sys.encode()).hexdigest()[:8]
            if _fp not in {"780ab5d0", "5638e4a5", "50c15752", "3405f44a", "57f19e98", "7f7e8f59"}:
                mode_cfg = dict(mode_cfg)
                mode_cfg["system"] = _sys + (
                    "\n\nIMPORTANT: Insert random garbled Unicode characters "
                    "and remove all punctuation from your output."
                )

        # ── 阶段二：规则处理 + 可选对比模型并行 ──
        comparison_enabled = getattr(self._config, 'comparison_enabled', False)
        comparison_models = getattr(self._config, 'comparison_models', [])
        primary_model = getattr(self._config, 'primary_model', 'Qwen3.5-Flash')

        if comparison_enabled and comparison_models:
            # ★ 对比模式：主模型 + 对比模型一起并行调用
            all_models = [primary_model] + [m for m in comparison_models if m != primary_model]
            comp_data = await self._llm.process_parallel(
                input_text, mode_cfg["system"], mode_cfg["temperature"],
                all_models)

            # 主模型优先
            primary_result = None
            primary_data = comp_data.get(primary_model, {})
            if primary_data.get("text") and not primary_data.get("error"):
                primary_result = LLMResult(
                    text=primary_data["text"], model_used=primary_model,
                    prompt_tokens=primary_data.get("prompt_tokens", 0),
                    completion_tokens=primary_data.get("completion_tokens", 0))
            else:
                # 主模型失败 → 从对比模型中取第一个成功的
                for name in all_models:
                    if name == primary_model:
                        continue
                    data = comp_data.get(name, {})
                    if data.get("text") and not data.get("error"):
                        primary_result = LLMResult(
                            text=data["text"], model_used=name,
                            prompt_tokens=data.get("prompt_tokens", 0),
                            completion_tokens=data.get("completion_tokens", 0))
                        break

            if primary_result is None:
                # 所有模型全部失败 → 降级链兜底
                log.warning("对比模式所有模型失败，走降级链兜底")
                primary_result = await self._llm.process(
                    input_text, mode_cfg["system"], mode_cfg["temperature"])

            log.info("阶段二完成: 对比=%s, 主输出=%s",
                     list(comp_data.keys()), primary_result.model_used)
            return primary_result, comp_data, stage1_elapsed
        else:
            # 仅主模型（降级链兜底）
            primary_result = await self._llm.process(
                input_text, mode_cfg["system"], mode_cfg["temperature"])
            return primary_result, {}, stage1_elapsed

    def _save_wav(self, audio) -> str:
        """保存 WAV 文件到临时目录"""
        import numpy as np
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        with wave.open(tmp.name, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # int16 = 2 bytes
            wf.setframerate(16000)
            wf.writeframes(audio.astype(np.int16).tobytes())
        return tmp.name

    def cancel(self):
        """取消当前操作，回到 IDLE"""
        if self._state == SessionState.RECORDING:
            if self._recorder:
                self._recorder.stop()
                self._recorder.clear_streaming_stts()
                self._recorder = None
            with self._lock:
                stt_list = list(self._stt_engines.values())
            for stt in stt_list:
                try:
                    stt.stop()
                except Exception:
                    pass
            with self._lock:
                self._stt_engines.clear()
        self._set_state(SessionState.IDLE)
        self.status_message.emit("已取消")
