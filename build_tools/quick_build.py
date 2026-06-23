"""Voice Flow 增量构建 — 只重建变化的部分，避免每次完整 PyArmor + PyInstaller + NSIS。

用法:
  python build_tools/quick_build.py              # 检测变化，增量构建
  python build_tools/quick_build.py --full       # 强制全量重建
  python build_tools/quick_build.py --only-nsis  # 仅 NSIS 重打包（资源文件改了）

构建矩阵:
  变更类型                     | 步骤
  ───────────────────────────┼──────────────────────────
  仅资源文件 (.wav/.ico)     │ NSIS
  明文 .py (4个大文件)       │ 复制 + PyInstaller + NSIS
  加密 .py (其他源码)        │ PyArmor单文件 + 复制 + PyInstaller + NSIS
  .spec / requirements       │ 全量重建
  首次构建 (无状态文件)      │ 全量重建
"""

import os
import sys
import json
import hashlib
import shutil
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
APP = PROJECT / "voice_flow_app"
BUILD_ENC = PROJECT / "build" / "voice_flow_app_enc"
BUILD_PYI = PROJECT / "build" / "voiceflow_enc"
STATE_FILE = PROJECT / "build_tools" / ".build_state.json"
NSIS_EXE = r"C:\Program Files (x86)\NSIS\Bin\makensis.exe"

# PyArmor 试用版超出限制，这 4 个文件不加密，直接复制明文
PLAIN_FILES = [
    "voice_flow_app/ui/settings_dialog.py",
    "voice_flow_app/ui/main_window.py",
    "voice_flow_app/ui/history_panel.py",
    "voice_flow_app/ui/credential_sync.py",
]

RESOURCE_EXTS = {".wav", ".ico", ".png", ".jpg", ".svg"}

SPEC_FILES = ["build_tools/voiceflow_enc.spec", "build_tools/installer.nsi"]


# ═══════════════════════════════════════════════
# 文件哈希
# ═══════════════════════════════════════════════

def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_sources() -> dict[str, str]:
    """收集所有源码 → {相对路径: sha256}"""
    result: dict[str, str] = {}
    for py_file in APP.rglob("*.py"):
        result[str(py_file.relative_to(PROJECT))] = hash_file(py_file)
    for pattern in ["build_tools/*.spec", "build_tools/*.nsi",
                    "voice_flow_app/resources/**/*"]:
        for f in PROJECT.glob(pattern):
            if f.is_file():
                result[str(f.relative_to(PROJECT))] = hash_file(f)
    return result


def load_state() -> dict[str, str]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict[str, str]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))


# ═══════════════════════════════════════════════
# 构建步骤
# ═══════════════════════════════════════════════

def run(cmd: list[str], **kwargs) -> None:
    print(f"  > {' '.join(cmd)}")
    kwargs.setdefault("cwd", str(PROJECT))
    r = subprocess.run(cmd, **kwargs)
    if r.returncode != 0:
        print(f"  ERROR: exit {r.returncode}")
        sys.exit(1)


def copy_plain_files() -> None:
    """复制 4 个明文 .py 到构建目录"""
    for rel in PLAIN_FILES:
        src = PROJECT / rel
        dst = BUILD_ENC / rel
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        print(f"  plain: {rel}")


def pyarmor_full() -> None:
    """完整 PyArmor 加密（排除明文文件）"""
    print("  PyArmor full gen...")
    # 临时移走明文文件
    for rel in PLAIN_FILES:
        src = PROJECT / rel
        bak = Path(str(src) + ".bak")
        if src.exists():
            shutil.move(str(src), str(bak))

    run(["pyarmor", "gen", "--output", str(BUILD_ENC), "voice_flow_app"])

    # 恢复
    for rel in PLAIN_FILES:
        src = PROJECT / rel
        bak = Path(str(src) + ".bak")
        if bak.exists():
            shutil.move(str(bak), str(src))


def pyarmor_single(rel_path: str) -> None:
    """对单个 .py 文件加密，结果放到 build/voice_flow_app_enc 对应位置"""
    src = PROJECT / rel_path
    print(f"  pyarmor: {rel_path}")
    run([
        "pyarmor", "gen", "--output", str(BUILD_ENC), str(src),
    ])

    # PyArmor 单文件输出到 BUILD_ENC/<basename>.py，需要挪到包结构里
    basename = os.path.basename(rel_path)
    flat_out = BUILD_ENC / basename
    nested_out = BUILD_ENC / rel_path
    if flat_out.exists():
        nested_out.parent.mkdir(parents=True, exist_ok=True)
        if nested_out.exists():
            nested_out.unlink()
        shutil.move(str(flat_out), str(nested_out))


def pyinstaller() -> None:
    BUILD_PYI.mkdir(parents=True, exist_ok=True)
    run(["pyinstaller", "--noconfirm", "build_tools/voiceflow_enc.spec"])


def nsis() -> None:
    run([NSIS_EXE, "installer.nsi"], cwd=str(PROJECT / "build_tools"))


def clean() -> None:
    for d in [BUILD_ENC, BUILD_PYI, PROJECT / "dist"]:
        if d.exists():
            shutil.rmtree(d)


# ═══════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════

def main() -> None:
    full = "--full" in sys.argv
    only_nsis = "--only-nsis" in sys.argv

    if only_nsis:
        print("=== NSIS only ===\n")
        nsis()
        return

    if full:
        print("=== Full rebuild ===\n")
        clean()
        pyarmor_full()
        copy_plain_files()
        pyinstaller()
        nsis()
        save_state(collect_sources())
        print("\nDone.")
        return

    # ── 增量检测 ──
    current = collect_sources()
    previous = load_state()

    if not previous:
        print("=== First build → full rebuild ===\n")
        clean()
        pyarmor_full()
        copy_plain_files()
        pyinstaller()
        nsis()
        save_state(current)
        print("\nDone.")
        return

    changed = [p for p, h in current.items()
               if p not in previous or previous[p] != h]
    deleted = [p for p in previous if p not in current]

    if not changed and not deleted:
        print("=== No source changes → NSIS only ===\n")
        nsis()
        return

    print(f"=== Changes: {len(changed)} modified/new, {len(deleted)} deleted ===\n")
    for p in changed:
        print(f"  M {p}")
    for p in deleted:
        print(f"  D {p}")
    print()

    # 分类
    is_resource_only = True
    has_plain = False
    has_encrypted = False
    has_spec = False

    for p in changed + deleted:
        ext = os.path.splitext(p)[1]
        if ext in RESOURCE_EXTS:
            continue
        is_resource_only = False
        if p in PLAIN_FILES:
            has_plain = True
        elif any(p == s for s in SPEC_FILES):
            has_spec = True
        elif ext == ".py":
            has_encrypted = True

    if is_resource_only:
        print("→ Resources only: NSIS\n")
        nsis()
        save_state(current)
        return

    if has_spec:
        print("→ Spec changed: full rebuild\n")
        clean()
        pyarmor_full()
        copy_plain_files()
        pyinstaller()
        nsis()
        save_state(current)
        return

    # ── 增量代码构建 ──
    print("→ Incremental code build\n")

    # 清理删除的文件
    for p in deleted:
        dead = BUILD_ENC / p
        if dead.exists():
            dead.unlink()
            print(f"  rm {p}")

    # 加密文件：单文件 PyArmor
    for p in changed:
        if p.endswith(".py") and p not in PLAIN_FILES and not p.startswith("build_tools/"):
            pyarmor_single(p)

    # 明文文件：直接复制
    copy_plain_files()

    # PyInstaller（保留缓存，增量编译）
    pyinstaller()

    # NSIS
    nsis()

    save_state(current)
    print("\nDone.")


if __name__ == "__main__":
    main()
