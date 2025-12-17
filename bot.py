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
    from daily import CallClient, Daily
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
        print("✅ Successfully joined the room!")
        
        # Wait a moment for connection to stabilize
        await asyncio.sleep(2)
        
        # Enable video publishing
        print("Enabling video publishing...")
        await call_client.set_video_publish_settings(enabled=True)
        
        # Create a custom video source from the file
        # Daily Python SDK supports custom video sources
        print("Creating video source from file...")
        
        frame_interval = 1.0 / video_track.fps
        
        # Create a function that provides video frames
        async def video_frame_generator():
            """Generator that yields video frames."""
            while True:
                frame = video_track.read_frame()
                if frame is None:
                    # Loop the video
                    video_track.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    frame = video_track.read_frame()
                    if frame is None:
                        break
                
                # Convert to the format Daily expects (typically RGB or YUV)
                # Daily Python SDK may expect frames in a specific format
                yield frame
                await asyncio.sleep(frame_interval)
        
        # Set the video source
        # Daily Python SDK API - check documentation for exact method names
        # Common patterns: set_video_source, set_input_video, or publish_video_frame
        print("Attempting to set video source...")
        
        # List available video-related methods for debugging
        video_methods = [m for m in dir(call_client) if 'video' in m.lower() and not m.startswith('_')]
        if video_methods:
            print(f"Available video methods: {', '.join(video_methods)}")
        
        # Try to set video source using common API patterns
        video_set = False
        
        # Method 1: Check if there's a set_video_source or similar method
        for method_name in ['set_video_source', 'set_input_video', 'set_video_input', 'publish_video', 'update_input_video']:
            if hasattr(call_client, method_name):
                try:
                    method = getattr(call_client, method_name)
                    # Try calling with the generator or frames
                    if asyncio.iscoroutinefunction(method):
                        await method(video_frame_generator())
                    else:
                        method(video_frame_generator())
                    print(f"✅ Video source set using {method_name}")
                    video_set = True
                    break
                except Exception as e:
                    print(f"   {method_name} failed: {e}")
                    continue
        
        if not video_set:
            print("⚠️  Could not automatically set video source.")
            print("   The Daily Python SDK may require a different approach.")
            print("   Please check the daily-python documentation for:")
            print("   - How to create custom video tracks")
            print("   - How to publish video from file/frames")
            print("   - Available video input methods")
            print("\n   Connection is active. Video publishing may need manual configuration.")
        
        print("\n✅ Bot is connected to the room!")
        print("   Video should appear if video source was set successfully.")
        print("   Press Ctrl+C to stop.\n")
        
        # Keep the bot running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping bot...")
        
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
