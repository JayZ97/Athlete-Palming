from flask import Flask, render_template, Response, jsonify, request
from camera import VideoCamera
from database import save_session, get_all_sessions, get_session_stats
from datetime import datetime
import time

app = Flask(__name__)

# Global variables to control state and hold the camera object
camera_active = False
global_camera = None
session_start_time = None
current_audio_track = None

@app.route('/')
def index():
    return render_template('index.html')

def gen():
    global camera_active, global_camera
    while True:
        if camera_active and global_camera:
            frame = global_camera.get_frame()
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')
            # Cap at ~24 FPS to reduce CPU load
            time.sleep(0.042)
        else:
            break 

@app.route('/video_feed')
def video_feed():
    global camera_active
    if camera_active:
        # We now run the generator without creating a new camera here
        return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')
    else:
        return "Camera Off"

@app.route('/start_session', methods=['POST'])
def start_session():
    global camera_active, global_camera, session_start_time, current_audio_track
    
    # Initialize the camera ONCE when the session starts
    if global_camera is None:
        global_camera = VideoCamera()
    
    # Record the start time and which audio track is playing
    session_start_time = datetime.now()
    
    data = request.get_json(silent=True)
    current_audio_track = data.get("audio_track") if data else None
        
    camera_active = True
    return jsonify({"status": "started", "message": "Camera started"})

@app.route('/stop_session', methods=['POST'])
def stop_session():
    global camera_active, global_camera, session_start_time, current_audio_track
    camera_active = False
    
    saved_stretches = []
    total_duration = 0
    
    # Grab all completed stretches (including any ongoing one) before destroying camera
    if global_camera:
        stretches = global_camera.get_all_stretches()
        
        # Save each stretch as its own session in MongoDB
        for s in stretches:
            start_dt = datetime.fromtimestamp(s["start_time"])
            end_dt = datetime.fromtimestamp(s["end_time"])
            save_session(
                start_time=start_dt,
                end_time=end_dt,
                duration_seconds=s["duration"],
                audio_track=current_audio_track
            )
            saved_stretches.append(s["duration"])
            total_duration += s["duration"]
        
        global_camera.video.release()  # Release hardware
        global_camera = None           # Clear memory

    # Reset tracking globals
    session_start_time = None
    current_audio_track = None

    # Send all stretch durations back to the frontend
    return jsonify({
        "status": "stopped", 
        "message": f"Saved {len(saved_stretches)} stretch(es)", 
        "stretches": saved_stretches,
        "total_duration": total_duration,
        "duration": total_duration  # backward compat for history refresh
    })

@app.route('/api/sessions')
def api_sessions():
    """Return all recorded sessions as JSON."""
    sessions = get_all_sessions()
    return jsonify(sessions)

@app.route('/api/sessions/stats')
def api_session_stats():
    """Return aggregate session statistics."""
    stats = get_session_stats()
    return jsonify(stats)

@app.route('/update_audio', methods=['POST'])
def update_audio():
    """Update the currently playing audio track mid-session."""
    global current_audio_track
    data = request.get_json(silent=True)
    current_audio_track = data.get("audio_track") if data else None
    return jsonify({"status": "ok", "audio_track": current_audio_track})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)