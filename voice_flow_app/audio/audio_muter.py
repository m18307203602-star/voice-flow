"""录音时静默其他应用音频（pycaw - Windows Core Audio API）"""
import os
import sys
from typing import Optional

try:
    from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
    _PYCAW_AVAILABLE = True
except ImportError:
    _PYCAW_AVAILABLE = False


class AudioMuter:
    """录音时自动静音其他音频会话"""

    def __init__(self):
        self._muted_sessions: list = []  # [(volume_interface, previous_mute_state)]
        self._is_muted = False

    def mute_all(self) -> bool:
        """静默除本进程外的所有音频会话。返回是否成功"""
        if not _PYCAW_AVAILABLE:
            return False

        if self._is_muted:
            return True

        try:
            sessions = AudioUtilities.GetAllSessions()
            my_pid = os.getpid()

            for session in sessions:
                if session.Process and session.Process.pid == my_pid:
                    continue
                try:
                    vol = session._ctl.QueryInterface(ISimpleAudioVolume)
                    was_muted = vol.GetMute()
                    if not was_muted:
                        vol.SetMute(True, None)
                        self._muted_sessions.append(vol)
                except Exception:
                    pass

            self._is_muted = True
            return True
        except Exception:
            return False

    def unmute_all(self):
        """恢复所有被静音的音频会话"""
        if not self._is_muted:
            return

        for vol in self._muted_sessions:
            try:
                vol.SetMute(False, None)
            except Exception:
                pass

        self._muted_sessions.clear()
        self._is_muted = False

    @property
    def available(self) -> bool:
        return _PYCAW_AVAILABLE
