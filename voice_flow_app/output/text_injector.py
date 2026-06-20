"""向当前焦点窗口注入文字（剪贴板 + Ctrl+V / Cmd+V）"""
import logging
import sys
import time
from typing import Optional

log = logging.getLogger("voice_flow.injector")

try:
    import pyperclip
    import pyautogui
    _INJECT_AVAILABLE = True
except ImportError:
    _INJECT_AVAILABLE = False
    log.warning("pyperclip 或 pyautogui 未安装，注入不可用")


class TextInjector:
    """通过剪贴板 + Ctrl+V 向当前焦点输入框注入文字"""

    @staticmethod
    def inject(text: str) -> bool:
        """注入文字到当前焦点控件。恢复原剪贴板内容。成功返回 True"""
        if not _INJECT_AVAILABLE:
            log.error("注入库不可用")
            return False

        if not text.strip():
            log.warning("注入文本为空")
            return False

        try:
            # 保存当前剪贴板
            old_clip = ""
            try:
                old_clip = pyperclip.paste()
                log.debug("保存原剪贴板: %d 字符", len(old_clip))
            except Exception as e:
                log.debug("无法读取原剪贴板: %s", e)

            # 复制目标文本
            pyperclip.copy(text)
            time.sleep(0.12)
            log.info("已复制到剪贴板: %d 字符", len(text))

            # 模拟 Ctrl+V（Mac 上自动用 Cmd+V）
            mod_key = 'command' if sys.platform == 'darwin' else 'ctrl'
            pyautogui.hotkey(mod_key, 'v')
            time.sleep(0.15)
            log.info("Ctrl+V 已执行")

            # 恢复原剪贴板
            if old_clip:
                try:
                    pyperclip.copy(old_clip)
                except Exception:
                    pass

            return True
        except Exception as e:
            log.error("注入失败: %s", e)
            return False
