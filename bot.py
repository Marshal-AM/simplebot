#!/usr/bin/env python3
"""
Daily bot that joins a room and publishes a video file using daily-python SDK.
"""
import sys
import os
import asyncio
import cv2
import numpy as np
from typing import Optional

try:
    from daily import CallClient, Daily, VirtualCameraDevice, VideoFrame
except ImportError:
    print("Error: daily-python package not installed.")
    print("Install it with: pip install daily-python")
    sys.exit(1)

# Initialize Daily core context (required before creating CallClient)
# This must be called once before any CallClient instances are created
_daily_initialized = False

def _ensure_daily_initialized():
    """Ensure Daily is initialized before creating CallClient."""
    global _daily_initialized
    if not _daily_initialized:
        Daily.init()
        _daily_initialized = True

try:
    import cv2
except ImportError:
    print("Error: opencv-python package not installed.")
    print("Install it with: pip install opencv-python")
    sys.exit(1)


class VideoFileTrack:
    """
    A video track that reads frames from a video file.
    This creates a generator that yields video frames.
    """
    def __init__(self, video_path: str):
        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")
        
        self.fps = int(self.cap.get(cv2.CAP_PROP_FPS)) or 30
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        print(f"Video info: {self.width}x{self.height} @ {self.fps}fps, {self.frame_count} frames")
    
    def read_frame(self) -> Optional[np.ndarray]:
        """Read the next frame as RGB numpy array."""
        ret, frame = self.cap.read()
        if not ret:
            # Loop the video
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
            if not ret:
                return None
        
        # Convert BGR to RGB
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return frame
    
    def release(self):
        if self.cap:
            self.cap.release()


async def publish_video_file(room_url: str, token: str, video_path: str):
    """
    Join a Daily room and publish a video file as a video track.
    """
    # Check if video file exists
    if not os.path.exists(video_path):
        print(f"Error: Video file not found at {video_path}")
        return
    
    video_path = os.path.abspath(video_path)
    
    # Initialize Daily core context (MUST be called before creating CallClient)
    print("Initializing Daily core context...")
    _ensure_daily_initialized()
    
    # Create CallClient with event handler
    print("Creating CallClient...")
    call_client = CallClient(event_handler=None)  # We don't need event handlers for simple video publishing
    video_track = None
    
    try:
        # Load video file
        print(f"Loading video file: {video_path}")
        video_track = VideoFileTrack(video_path)
        
        # Create virtual camera device BEFORE joining (like pipecat does)
        print(f"[CAMERA] Creating virtual camera device...")
        print(f"[CAMERA] Width: {video_track.width}, Height: {video_track.height}, FPS: {video_track.fps}")
        camera_name = "video-bot-camera"
        try:
            camera = Daily.create_camera_device(
                camera_name,
                width=video_track.width,
                height=video_track.height,
                color_format="RGB"
            )
            print(f"[CAMERA] ✅ Camera device created: {camera}")
            print(f"[CAMERA] Camera device type: {type(camera)}")
        except Exception as e:
            print(f"[CAMERA] ❌ Error creating camera device: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        # Join the room
        # CallClient.join() takes positional arguments: room_url, token, completion, client_settings
        print(f"[JOIN] Starting join process...")
        print(f"[JOIN] Room URL: {room_url}")
        print(f"[JOIN] Token: {'Provided' if token else 'None'}")
        
        # Set user name
        print(f"[JOIN] Setting user name to 'Video Bot'...")
        call_client.set_user_name("Video Bot")
        print(f"[JOIN] User name set")
        
        # Join with positional arguments (room_url, token, completion callback)
        print(f"[JOIN] Creating future for join completion...")
        future = asyncio.get_event_loop().create_future()
        
        callback_called = False
        callback_data = None
        callback_error = None
        
        def completion_callback(*args):
            """Handle join completion callback."""
            nonlocal callback_called, callback_data, callback_error
            callback_called = True
            print(f"[JOIN] Completion callback called with {len(args)} arguments")
            try:
                if len(args) >= 2:
                    # (data, error) format
                    print(f"[JOIN] Callback args[0] type: {type(args[0])}, args[1] type: {type(args[1])}")
                    print(f"[JOIN] Callback args[0]: {args[0]}")
                    print(f"[JOIN] Callback args[1]: {args[1]}")
                    callback_data = args[0]
                    callback_error = args[1]
                    # Only set result if future is not done/cancelled
                    if not future.done():
                        future.set_result((args[0], args[1]))
                    else:
                        print(f"[JOIN] ⚠️  Future already done, callback was delayed")
                elif len(args) == 1:
                    print(f"[JOIN] Callback single arg type: {type(args[0])}, value: {args[0]}")
                    callback_data = args[0]
                    callback_error = None
                    if not future.done():
                        future.set_result((args[0], None))
                    else:
                        print(f"[JOIN] ⚠️  Future already done, callback was delayed")
                else:
                    print(f"[JOIN] Callback no args")
                    callback_data = None
                    callback_error = None
                    if not future.done():
                        future.set_result((None, None))
                    else:
                        print(f"[JOIN] ⚠️  Future already done, callback was delayed")
            except Exception as e:
                print(f"[JOIN] Error in completion callback: {e}")
                import traceback
                traceback.print_exc()
                callback_error = str(e)
                if not future.done():
                    future.set_exception(e)
        
        print(f"[JOIN] Calling call_client.join()...")
        # Pass camera device in client_settings (like pipecat does)
        # Include both inputs AND publishing settings
        call_client.join(
            room_url,
            token if token else None,
            completion=completion_callback,
            client_settings={
                "inputs": {
                    "camera": {
                        "isEnabled": True,
                        "settings": {
                            "deviceId": camera_name,
                        },
                    },
                },
                "publishing": {
                    "camera": {
                        "sendSettings": {
                            "maxQuality": "high",
                            "encodings": {
                                "high": {
                                    "maxBitrate": 2000000,  # 2 Mbps
                                    "maxFramerate": video_track.fps,
                                }
                            },
                        }
                    }
                }
            }
        )
        print(f"[JOIN] call_client.join() called, waiting for completion...")
        
        # Wait for join to complete with longer timeout
        # The callback may be delayed, so we use a longer timeout
        try:
            data, error = await asyncio.wait_for(future, timeout=30.0)
            print(f"[JOIN] Future completed")
            print(f"[JOIN] Data: {data}")
            print(f"[JOIN] Error: {error}")
        except asyncio.TimeoutError:
            print(f"[JOIN] ⚠️  Join timed out after 30 seconds!")
            print(f"[JOIN] Callback was called: {callback_called}")
            
            # If callback was called but future timed out, use callback data
            if callback_called and callback_data is not None:
                print(f"[JOIN] ✅ Using callback data (callback was delayed)")
                data = callback_data
                error = callback_error
            else:
                # Check if we're actually joined by checking participants
                try:
                    participants = call_client.participants()
                    if participants and 'local' in participants:
                        print(f"[JOIN] ✅ Actually joined! (verified via participants)")
                        print(f"[JOIN] Local participant: {participants['local']}")
                        data = participants
                        error = None
                    else:
                        raise Exception("Join operation timed out and not actually joined")
                except Exception as e:
                    print(f"[JOIN] ❌ Not actually joined: {e}")
                    raise Exception("Join operation timed out")
        
        if error:
            print(f"[JOIN] ❌ Join error: {error}")
            raise Exception(f"Failed to join room: {error}")
        
        print("✅ Successfully joined the room!")
        print(f"   Participant data: {data}")
        
        # Create virtual camera device BEFORE joining (like pipecat does)
        print(f"[CAMERA] Creating virtual camera device...")
        print(f"[CAMERA] Width: {video_track.width}, Height: {video_track.height}, FPS: {video_track.fps}")
        camera_name = "video-bot-camera"
        try:
            camera = Daily.create_camera_device(
                camera_name,
                width=video_track.width,
                height=video_track.height,
                color_format="RGB"
            )
            print(f"[CAMERA] ✅ Camera device created: {camera}")
            print(f"[CAMERA] Camera device type: {type(camera)}")
        except Exception as e:
            print(f"[CAMERA] ❌ Error creating camera device: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        # Wait a moment for connection to stabilize
        print(f"[SETUP] Waiting 3 seconds for connection to stabilize...")
        await asyncio.sleep(3)
        print(f"[SETUP] Wait complete")
        
        # Verify camera track is active
        print(f"[CAMERA] Verifying camera track status...")
        try:
            participants = call_client.participants()
            local_participant = participants.get('local', {})
            local_media = local_participant.get('media', {})
            camera_info = local_media.get('camera', {})
            print(f"[CAMERA] Camera state: {camera_info.get('state')}")
            print(f"[CAMERA] Camera track ID: {camera_info.get('track', {}).get('id') if camera_info.get('track') else 'None'}")
            if camera_info.get('state') != 'playable':
                print(f"[CAMERA] ⚠️  Camera state is not 'playable', it's: {camera_info.get('state')}")
        except Exception as e:
            print(f"[CAMERA] Could not verify camera status: {e}")
        
        # Camera device is already configured in client_settings when joining
        # No need to update inputs separately - frames are written directly to the camera device
        print(f"[CAMERA] Camera device configured and ready for frame writing")
        
        # Video publishing is enabled via client_settings when joining
        # No need to call set_video_publish_settings (that method doesn't exist)
        print(f"[VIDEO] Video publishing configured via client_settings in join()")
        
        # Check participants to see if we're visible
        try:
            participants = call_client.participants()
            print(f"[VIDEO] Current participants: {participants}")
        except Exception as e:
            print(f"[VIDEO] Could not get participants: {e}")
        
        # Wait a bit more to ensure camera device is fully ready
        print(f"[FRAMES] Waiting 1 second for camera device to be fully ready...")
        await asyncio.sleep(1)
        
        # Start sending video frames
        print(f"[FRAMES] Starting video playback...")
        print(f"[FRAMES] Frame interval: {1.0 / video_track.fps:.4f} seconds ({video_track.fps} fps)")
        frame_interval = 1.0 / video_track.fps
        frame_count = 0
        error_count = 0
        
        # Verify camera device is ready
        print(f"[FRAMES] Camera device object: {camera}")
        print(f"[FRAMES] Camera device name: {camera_name}")
        
        async def send_video_frames():
            """Continuously send video frames to the camera device."""
            nonlocal frame_count, error_count
            loop_count = 0
            
            while True:
                try:
                    frame = video_track.read_frame()
                    if frame is None:
                        # Loop the video
                        print(f"[FRAMES] End of video reached, looping...")
                        video_track.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        frame = video_track.read_frame()
                        if frame is None:
                            print(f"[FRAMES] ❌ Could not read frame after loop reset")
                            break
                        loop_count += 1
                        print(f"[FRAMES] Video loop #{loop_count}")
                    
                    frame_count += 1
                    if frame_count % 30 == 0:  # Log every 30 frames
                        print(f"[FRAMES] Sent {frame_count} frames (loop #{loop_count})")
                    
                    # Convert numpy array to bytes (RGB format)
                    # Frame is already RGB from VideoFileTrack.read_frame()
                    frame_bytes = frame.tobytes()
                    frame_size = len(frame_bytes)
                    expected_size = video_track.width * video_track.height * 3  # RGB = 3 bytes per pixel
                    
                    if frame_count == 1:
                        print(f"[FRAMES] First frame - size: {frame_size} bytes, expected: {expected_size} bytes")
                        print(f"[FRAMES] Frame shape: {frame.shape}, dtype: {frame.dtype}")
                    
                    if frame_size != expected_size:
                        print(f"[FRAMES] ⚠️  Frame size mismatch! Expected {expected_size}, got {frame_size}")
                    
                    # Write frame to camera device
                    try:
                        # For the first few frames, write immediately to establish the stream
                        if frame_count <= 5:
                            camera.write_frame(frame_bytes)
                            if frame_count == 1:
                                print(f"[FRAMES] ✅ First frame written successfully ({frame_size} bytes)")
                                # Also try writing a test pattern to verify camera works
                                print(f"[FRAMES] Writing test pattern to verify camera...")
                                test_frame = np.ones((video_track.height, video_track.width, 3), dtype=np.uint8) * 255  # White frame
                                test_frame[:, :, 0] = 0  # Red channel = 0 (cyan frame)
                                test_bytes = test_frame.tobytes()
                                camera.write_frame(test_bytes)
                                await asyncio.sleep(0.1)
                                # Write actual frame again
                                camera.write_frame(frame_bytes)
                        else:
                            camera.write_frame(frame_bytes)
                    except Exception as e:
                        error_count += 1
                        if error_count <= 5:  # Only log first 5 errors
                            print(f"[FRAMES] ❌ Error writing frame #{frame_count}: {e}")
                            import traceback
                            traceback.print_exc()
                        if error_count == 5:
                            print(f"[FRAMES] ⚠️  Suppressing further write errors...")
                    
                    await asyncio.sleep(frame_interval)
                    
                except Exception as e:
                    print(f"[FRAMES] ❌ Exception in send_video_frames: {e}")
                    import traceback
                    traceback.print_exc()
                    await asyncio.sleep(1)  # Wait a bit before retrying
        
        # Start sending frames in background
        print(f"[FRAMES] Creating frame sending task...")
        frame_task = asyncio.create_task(send_video_frames())
        print(f"[FRAMES] ✅ Frame task created and started")
        
        print("\n✅ Bot is connected and streaming video!")
        print("   Video should appear in the room now.")
        print("   Press Ctrl+C to stop.\n")
        
        # Keep the bot running
        try:
            await frame_task
        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Stopping bot...")
            frame_task.cancel()
            try:
                await frame_task
            except asyncio.CancelledError:
                print("[SHUTDOWN] Frame task cancelled")
        
        print(f"[SHUTDOWN] Total frames sent: {frame_count}")
        print(f"[SHUTDOWN] Total errors: {error_count}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if video_track:
            video_track.release()
        try:
            await call_client.leave()
            print("Left the room")
        except:
            pass


def main():
    if len(sys.argv) < 2:
        print("Usage: python bot.py <room_url> [token] <video_path>")
        sys.exit(1)
    
    room_url = sys.argv[1]
    token = ""
    video_path = ""
    
    if len(sys.argv) == 3:
        # Only video path provided
        video_path = sys.argv[2]
    elif len(sys.argv) == 4:
        # Token and video path provided
        token = sys.argv[2]
        video_path = sys.argv[3]
    else:
        print("Usage: python bot.py <room_url> [token] <video_path>")
        sys.exit(1)
    
    print(f"Room URL: {room_url}")
    print(f"Token: {'Provided' if token else 'None'}")
    print(f"Video Path: {video_path}")
    print()
    
    asyncio.run(publish_video_file(room_url, token, video_path))


if __name__ == "__main__":
    main()
