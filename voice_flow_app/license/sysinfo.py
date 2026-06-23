"""系统信息采集 — 全面采集 OS / CPU / 内存 / 磁盘 / 网络 / GPU / 音频 / 电池 / IP，随心跳上报"""
import os
import json
import platform
import socket
import subprocess
import sys
import urllib.request


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _get_public_ip_info() -> dict | None:
    try:
        req = urllib.request.Request(
            "http://ip-api.com/json/?fields=query,country,regionName,city,isp,lat,lon",
            headers={"User-Agent": "VoiceFlow/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") != "fail":
                return {
                    "public_ip": data.get("query", ""),
                    "country": data.get("country", ""),
                    "region": data.get("regionName", ""),
                    "city": data.get("city", ""),
                    "isp": data.get("isp", ""),
                    "location": f"{data.get('country', '')} {data.get('regionName', '')} {data.get('city', '')}".strip(),
                }
    except Exception:
        pass
    return None


def _gpu_info() -> dict:
    """GPU 型号/显存/驱动 — 按平台调用系统命令"""
    info = {}
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(
                ["wmic", "path", "win32_videocontroller", "get",
                 "name,adapterram,driverversion", "/format:csv"],
                timeout=5, encoding="utf-8", errors="ignore",
            )
            lines = [l.strip() for l in out.splitlines() if l.strip()][1:]  # skip header
            for i, line in enumerate(lines):
                parts = line.split(",")
                if len(parts) >= 4:
                    name = parts[1].strip()
                    ram_bytes = parts[2].strip()
                    driver = parts[3].strip()
                    try:
                        ram_gb = round(int(ram_bytes) / (1024 ** 3), 1)
                    except Exception:
                        ram_gb = 0
                    info[f"gpu{i}_name"] = name
                    info[f"gpu{i}_vram_gb"] = ram_gb
                    info[f"gpu{i}_driver"] = driver
        elif sys.platform == "darwin":
            out = subprocess.check_output(
                ["system_profiler", "SPDisplaysDataType"],
                timeout=10, encoding="utf-8", errors="ignore",
            )
            # ponytail: parse key lines, full SPDisplaysDataType output is verbose
            for i, line in enumerate(out.splitlines()):
                stripped = line.strip()
                if "Chipset Model:" in stripped:
                    info[f"gpu_name"] = stripped.split(":", 1)[1].strip()
                if "VRAM" in stripped:
                    info[f"gpu_vram"] = stripped.split(":", 1)[1].strip()
        else:
            out = subprocess.check_output(
                ["lspci"], timeout=5, encoding="utf-8", errors="ignore",
            )
            for line in out.splitlines():
                if "VGA" in line or "3D" in line:
                    info["gpu_name"] = line.split(":", 1)[1].strip() if ":" in line else line.strip()
                    break
    except Exception:
        pass
    return info


def _audio_devices() -> dict:
    """列出所有音频输入/输出设备"""
    info = {}
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            io = "in" if dev["max_input_channels"] > 0 else "out"
            info[f"audio_{io}{i}"] = dev["name"]
    except Exception:
        pass
    return info


def collect() -> dict:
    """采集当前客户端操作系统和硬件信息"""
    info = {
        "os": platform.system(),
        "os_version": platform.release(),
        "os_arch": platform.machine(),
        "cpu_model": platform.processor() or "Unknown",
        "cpu_cores": os.cpu_count() or 0,
        "hostname": socket.gethostname(),
        "python_version": sys.version.split()[0],
        "local_ip": _get_local_ip(),
    }

    # ── psutil 核心增强 ──
    try:
        import psutil

        # CPU
        info["cpu_cores_physical"] = psutil.cpu_count(logical=False) or 0
        info["cpu_cores_logical"] = psutil.cpu_count(logical=True) or 0
        freq = psutil.cpu_freq()
        if freq:
            info["cpu_freq_mhz"] = round(freq.max, 1)
            info["cpu_freq_current_mhz"] = round(freq.current, 1)

        # 内存
        mem = psutil.virtual_memory()
        info["ram_total_gb"] = round(mem.total / (1024 ** 3), 1)
        info["ram_available_gb"] = round(mem.available / (1024 ** 3), 1)
        info["ram_used_percent"] = mem.percent
        swap = psutil.swap_memory()
        info["swap_total_gb"] = round(swap.total / (1024 ** 3), 1)
        info["swap_used_percent"] = swap.percent

        # 磁盘
        try:
            for part in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    mount = part.mountpoint.replace("\\", "/").rstrip("/") or "/"
                    key = f"disk_{mount.replace(':', '').replace('/', '_')}"
                    info[f"{key}_total_gb"] = round(usage.total / (1024 ** 3), 1)
                    info[f"{key}_free_gb"] = round(usage.free / (1024 ** 3), 1)
                    info[f"{key}_used_percent"] = usage.percent
                except Exception:
                    pass
        except Exception:
            pass

        # 网络接口
        try:
            net = psutil.net_if_addrs()
            for name, addrs in net.items():
                for addr in addrs:
                    if str(addr.family) == "AddressFamily.AF_INET":
                        info[f"net_{name}_ip"] = addr.address
                    if str(addr.family).endswith("AF_LINK") or hasattr(addr, "address"):
                        # ponytail: MAC address from AF_LINK family
                        try:
                            info[f"net_{name}_mac"] = addr.address.replace("-", ":")
                        except Exception:
                            pass
            io = psutil.net_io_counters()
            info["net_bytes_sent"] = io.bytes_sent
            info["net_bytes_recv"] = io.bytes_recv
        except Exception:
            pass

        # 电池
        try:
            battery = psutil.sensors_battery()
            if battery:
                info["battery_percent"] = battery.percent
                info["battery_plugged"] = battery.power_plugged
                if battery.secsleft > 0:
                    info["battery_secs_left"] = battery.secsleft
        except Exception:
            pass

        # 系统运行时间
        try:
            import time
            boot = psutil.boot_time()
            info["boot_time"] = boot
            uptime = time.time() - boot
            info["uptime_hours"] = round(uptime / 3600, 1)
        except Exception:
            pass

        # 登录用户
        try:
            users = psutil.users()
            info["logged_in_users"] = ", ".join(u.name for u in users)
        except Exception:
            pass

        # 进程数
        try:
            info["process_count"] = len(psutil.pids())
        except Exception:
            pass

        # CPU 温度（可能不可用）
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for category, entries in temps.items():
                    for i, entry in enumerate(entries):
                        info[f"temp_{category}_{i}"] = f"{entry.label or 'sensor'}: {entry.current}°C"
        except Exception:
            pass

    except ImportError:
        pass

    # ── GPU ──
    info.update(_gpu_info())

    # ── 音频设备 ──
    info.update(_audio_devices())

    # ── 客户端版本 ──
    try:
        from pathlib import Path
        vf_json = Path.home() / ".voice_flow" / "version.json"
        if vf_json.exists():
            v = json.loads(vf_json.read_text(encoding="utf-8"))
            info["client_version"] = v.get("version", "")
    except Exception:
        pass

    # ── 公网 IP + 地理位置 ──
    pub = _get_public_ip_info()
    if pub:
        info.update(pub)

    return info
