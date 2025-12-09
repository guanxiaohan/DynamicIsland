# WindowsSMTC.py

import asyncio
import time
from winsdk.windows.devices.enumeration import (DeviceClass, DeviceInformation, DeviceInformationKind)
from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager, GlobalSystemMediaTransportControlsSessionTimelineProperties, GlobalSystemMediaTransportControlsSessionPlaybackStatus
from winsdk.windows.media.control import (MediaPropertiesChangedEventArgs,
                                          PlaybackInfoChangedEventArgs)
from winsdk.windows.storage.streams import Buffer, DataReader
from winsdk.windows.ui.notifications import ToastNotificationManager, ToastNotificationMode

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]

class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_long),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", ctypes.c_long),
    ]

def get_process_name_from_hwnd(hwnd: int) -> str:
    """
    Returns process name (e.g. 'explorer.exe') of a window.
    """

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x0400 | 0x0010, False, pid.value)  # QUERY_INFORMATION | VM_READ
    if not handle:
        return ""

    image_filename = (ctypes.c_wchar * 260)()
    psapi.GetModuleBaseNameW(handle, None, image_filename, 260)

    kernel32.CloseHandle(handle)
    return image_filename.value.lower()


def is_foreground_window_fullscreen(exclude_explorer: bool = True) -> bool:
    """
    Returns True if the foreground window is fullscreen
    and optionally excludes explorer.exe (desktop).
    """

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False

    # Optional exclusion of explorer.exe (desktop / shell)
    if exclude_explorer:
        name = get_process_name_from_hwnd(hwnd)
        if name in ("explorer.exe", "shellexperiencehost.exe"):
            return False

    # Get window rect
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False

    # Get monitor rect
    monitor = user32.MonitorFromWindow(hwnd, 1)
    if not monitor:
        return False

    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW(monitor, ctypes.byref(mi))
    m = mi.rcMonitor

    # Tolerance for borders, DPI scaling
    TOL = 1
    is_fullscreen = (
        abs(rect.left - m.left) <= TOL and
        abs(rect.top - m.top) <= TOL and
        abs(rect.right - m.right) <= TOL and
        abs(rect.bottom - m.bottom) <= TOL
    )

    return is_fullscreen

async def get_current_session():
    manager = await MediaManager.request_async()
    manager.get_sessions()
    sessions = manager.get_sessions()
    return sessions

async def get_media_info():
    sessions = await get_current_session()

    if not sessions or len(sessions) == 0:
        return None

    # Sort sessions by priority: has cover+title+artist > has cover > has title+artist > has app name > None
    def session_priority(session):
        try:
            info = session.source_info
            playback = session.get_playback_info()
            title = info.title if info else None
            artist = info.artist if info else None
            has_cover = info.thumbnail if info else None
            playing = (playback.playback_status == GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING) if playback else False
            print(title, playing)
            # app_name = session.source_info.display_name if session.source_info else None
            
            if has_cover and title and artist and playing:
                return 0
            elif title and artist and playing:
                return 1
            elif title and playing:
                return 2
            elif has_cover and title and artist:
                return 3
            elif title and artist:
                return 4
            else:
                return 5
        except:
            return 5

    sorted_sessions = sorted(sessions, key=session_priority)
    session = sorted_sessions[0]

    info = await session.try_get_media_properties_async()
    playback = session.get_playback_info()
    is_playing = (playback.playback_status == GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING) if playback else False
    is_paused = (playback.playback_status == GlobalSystemMediaTransportControlsSessionPlaybackStatus.PAUSED) if playback else False
    current_time = session.get_timeline_properties()
    timeline = current_time

    def _ts_secs(ts: GlobalSystemMediaTransportControlsSessionTimelineProperties | None):
        if ts is None:
            return 0, 0
        
        try:
            return ts.position.total_seconds(), ts.end_time.total_seconds()
        
        except Exception:
            # fallback: some WinRT TimeSpan representations expose 'duration' in 100-ns units
            dur = getattr(ts, "duration", None)
            if dur is not None:
                return 0, dur / 10_000_000
            return 0, 0

    position_secs, duration_secs = _ts_secs(timeline) if timeline else (0, 0)

    result = {
        "title": info.title or session.source_app_user_model_id,
        "artist": info.artist,
        "album": info.album_title,
        "playback_status": playback.playback_status if playback else None,
        "album_artist": info.album_artist,
        "genres": info.genres,
        "thumbnail": None,
        "position_seconds": position_secs,
        "duration_seconds": duration_secs,
        "last_update": timeline.last_updated_time.timestamp() if timeline else time.time(),
        "is_playing": is_playing,
        "is_paused": is_paused
    }

    # 封面图（thumbnail）需要手动读取二进制
    if info.thumbnail:
        stream = await info.thumbnail.open_read_async()
        size = stream.size

        # 获取 InputStream（DataReader 要求 IInputStream）
        input_stream = stream.get_input_stream_at(0)

        reader = DataReader(input_stream)
        await reader.load_async(size)
        byte_result_pointer = bytearray(size)
        reader.read_bytes(byte_result_pointer) # type: ignore
        result["thumbnail"] = bytes(byte_result_pointer)

    return result

def get_media_info_sync():
    return asyncio.get_event_loop().run_until_complete(get_media_info())

def is_do_not_disturb_on() -> bool:
    """
    Returns True if Windows Do Not Disturb / Focus Assist is ON.
    Windows 11 and Windows 10 supported.
    """

    x = ToastNotificationManager.get_default()
    mode = x.notification_mode if x else ToastNotificationMode.UNRESTRICTED

    # Modes:
    #   ToastNotificationMode.UNRESTRICTED → notifications allowed
    #   ToastNotificationMode.PRIORITY_ONLY → DND on
    #   ToastNotificationMode.ALARMS_ONLY  → DND strongly on
    #
    return mode != ToastNotificationMode.UNRESTRICTED

if __name__ == "__main__":
    ...