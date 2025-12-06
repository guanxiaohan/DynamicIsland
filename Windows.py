# WindowsSMTC.py

import asyncio
import time
from winsdk.windows.devices.enumeration import (DeviceClass, DeviceInformation, DeviceInformationKind)
from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager, GlobalSystemMediaTransportControlsSessionTimelineProperties, GlobalSystemMediaTransportControlsSessionPlaybackStatus
from winsdk.windows.media.control import (MediaPropertiesChangedEventArgs,
                                          PlaybackInfoChangedEventArgs)
from winsdk.windows.storage.streams import Buffer, DataReader

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


if __name__ == "__main__":
    ...