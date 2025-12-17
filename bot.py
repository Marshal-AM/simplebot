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
        
        # Join the room
        # CallClient.join() takes positional arguments: room_url, token, completion, client_settings
        print(f"Joining room: {room_url}")
        
        # Set user name
        call_client.set_user_name("Video Bot")
        
        # Join with positional arguments (room_url, token, completion callback)
        future = asyncio.get_event_loop().create_future()
        
        def completion_callback(*args):
            """Handle join completion callback."""
            try:
                if len(args) >= 2:
                    # (data, error) format
                    future.set_result((args[0], args[1]))
                elif len(args) == 1:
                    future.set_result((args[0], None))
                else:
                    future.set_result((None, None))
            except Exception as e:
                future.set_exception(e)
        
        call_client.join(
            room_url,
            token if token else None,
            completion=completion_callback
        )
        
        # Wait for join to complete
        data, error = await future
        if error:
            raise Exception(f"Failed to join room: {error}")
        
        print("✅ Successfully joined the room!")
        print(f"   Participant data: {data}")
        
        # Wait a moment for connection to stabilize
        await asyncio.sleep(2)
        
        # Create virtual camera device (like pipecat does)
        print("Creating virtual camera device...")
        camera = Daily.create_camera_device(
            "video-bot-camera",
            width=video_track.width,
            height=video_track.height,
            color_format="RGB"
        )
        
        # Select the camera device
        Daily.select_camera_device("video-bot-camera")
        print("✅ Camera device created and selected")
        
        # Enable video publishing
        print("Enabling video publishing...")
        call_client.set_video_publish_settings(enabled=True)
        
        # Start sending video frames
        print("Starting video playback...")
        frame_interval = 1.0 / video_track.fps
        
        async def send_video_frames():
            """Continuously send video frames to the camera device."""
            while True:
                frame = video_track.read_frame()
                if frame is None:
                    # Loop the video
                    video_track.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    frame = video_track.read_frame()
                    if frame is None:
                        break
                
                # Convert numpy array to bytes (RGB format)
                # Frame is already RGB from VideoFileTrack.read_frame()
                frame_bytes = frame.tobytes()
                
                # Write frame to camera device
                camera.write_frame(frame_bytes)
                
                await asyncio.sleep(frame_interval)
        
        # Start sending frames in background
        frame_task = asyncio.create_task(send_video_frames())
        
        print("\n✅ Bot is connected and streaming video!")
        print("   Video should appear in the room now.")
        print("   Press Ctrl+C to stop.\n")
        
        # Keep the bot running
        try:
            await frame_task
        except KeyboardInterrupt:
            print("\nStopping bot...")
            frame_task.cancel()
            try:
                await frame_task
            except asyncio.CancelledError:
                pass
        
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
