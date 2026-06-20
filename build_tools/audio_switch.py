"""音频设备切换工具 — 在 Realtek 扬声器和 VB-Cable 之间切换默认播放设备"""
import sys
from pycaw.pycaw import AudioUtilities
from pycaw.constants import ERole


def list_output_devices():
    """列出所有输出设备"""
    print("=== 可用播放设备 ===")
    for dev in AudioUtilities.GetAllDevices():
        name = dev.FriendlyName
        try:
            df = AudioUtilities.GetEndpointDataFlow(dev)
            flow = "OUT" if df == 0 else "IN"
            print(f"  [{flow}] {name}")
            print(f"       ID: {dev.id[:60]}...")
        except Exception:
            print(f"  [?] {name}")


def set_default(keyword: str):
    """设置默认播放设备"""
    target_id = None
    target_name = ""

    for dev in AudioUtilities.GetAllDevices():
        name = dev.FriendlyName
        if keyword.lower() in name.lower():
            try:
                df = AudioUtilities.GetEndpointDataFlow(dev)
                if df == 0:  # output only
                    target_id = dev.id
                    target_name = name
                    break
            except Exception:
                pass

    if target_id is None:
        # 回退：不限制方向
        for dev in AudioUtilities.GetAllDevices():
            if keyword.lower() in dev.FriendlyName.lower():
                target_id = dev.id
                target_name = dev.FriendlyName
                break

    if target_id is None:
        print(f"ERROR: 未找到包含 '{keyword}' 的设备")
        return False

    print(f"切换到: {target_name}")
    AudioUtilities.SetDefaultDevice(
        target_id,
        roles=[ERole.eMultimedia, ERole.eCommunications]
    )
    print("DONE")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        list_output_devices()
        print("\n用法:")
        print("  python audio_switch.py realtek   → 切到 Realtek 扬声器")
        print("  python audio_switch.py cable     → 切到 VB-Cable（屏幕内录用）")
        print("  python audio_switch.py list      → 列出所有设备")
    elif sys.argv[1] == "list":
        list_output_devices()
    else:
        set_default(sys.argv[1])
