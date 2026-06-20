"""Voice Flow PyInstaller 启动入口（加密版）"""
import sys
import os

if getattr(sys, 'frozen', False):
    _base = sys._MEIPASS
else:
    _base = os.path.dirname(os.path.abspath(__file__))

# 确定加密副本路径（仅开发模式）
_enc = os.path.join(os.path.dirname(_base), "build", "voice_flow_app_enc")

# 确保父目录在 sys.path 中
_parent = os.path.dirname(_base)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

# 开发模式：加密副本覆盖原始源码，优先级更高
if os.path.isdir(_enc) and _enc not in sys.path:
    sys.path.insert(0, _enc)  # 插入到 _parent 前面

from voice_flow_app.main import main

if __name__ == "__main__":
    main()
