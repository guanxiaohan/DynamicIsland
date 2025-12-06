# WindowsSMTC.py

import asyncio

from winsdk.windows.devices.enumeration import (DeviceClass, DeviceInformation, DeviceInformationKind)
from winsdk.windows.media.control import \
    GlobalSystemMediaTransportControlsSessionManager as MediaManager
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
            # app_name = session.source_info.display_name if session.source_info else None
            
            if has_cover and title and artist:
                return 0
            elif has_cover:
                return 1
            elif title and artist:
                return 2
            # elif app_name:
            #     return 3
            else:
                return 4
        except:
            return 4

    sorted_sessions = sorted(sessions, key=session_priority)
    session = sorted_sessions[0]

    info = await session.try_get_media_properties_async()
    playback = session.get_playback_info()

    result = {
        "title": info.title or session.source_app_user_model_id,
        "artist": info.artist,
        "album": info.album_title,
        "playback_status": playback.playback_status if playback else None,
        "album_artist": info.album_artist,
        "genres": info.genres,
        "thumbnail": None,
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

async def check_device_usage():
    # from winsdk.windows.media.capture import MediaCapture, MediaCaptureInitializationSettings
    # from winsdk.windows.media.devices import MediaDevice, AudioDeviceRole

    # 摄像头检测
    # cam_in_use = False
    # try:
    #     cam_settings = MediaCaptureInitializationSettings()
    #     cam_settings.video_device_id = MediaDevice.get_default_video_capture_id(
    #         MediaDevice.default_video_capture_id
    #     )
    #     cam_capture = MediaCapture()
    #     await cam_capture.initialize_async(cam_settings)
    #     # 如果能成功初始化，说明摄像头可用（未被占用）
    #     cam_in_use = False
    # except Exception as e:
    #     # 初始化失败，通常是设备被占用或权限不足
    #     cam_in_use = True

    # 麦克风检测
    # mic_in_use = False
    # try:
    #     mic_settings = MediaCaptureInitializationSettings()
    #     mic_settings.audio_device_id = MediaDevice.get_default_audio_capture_id(
    #         AudioDeviceRole.DEFAULT
    #     )
    #     mic_capture = MediaCapture()
    #     await mic_capture.initialize_async(mic_settings)
    #     mic_in_use = False
    # except Exception as e:
    #     mic_in_use = True

    # print(mic_in_use, cam_in_use)
    # return mic_in_use, cam_in_use
    return False, False


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(check_device_usage())