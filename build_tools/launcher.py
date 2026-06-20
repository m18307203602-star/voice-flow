"""Voice Flow PyInstaller 启动入口"""
import sys
import os

# PyInstaller 打包后的资源路径
if getattr(sys, 'frozen', False):
    _base = sys._MEIPASS
else:
    _base = os.path.dirname(os.path.abspath(__file__))

# 确保 voice_flow_app 在 sys.path 中
_parent = os.path.dirname(_base)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from voice_flow_app.main import main

if __name__ == "__main__":
    main()
