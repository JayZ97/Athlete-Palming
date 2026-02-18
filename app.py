from flask import Flask, render_template, Response, jsonify, request
from camera import VideoCamera

app = Flask(__name__)

# Global variable to control the camera state
camera_active = False

@app.route('/')
def index():
    return render_template('index.html')

def gen(camera):
    global camera_active
    while True:
        if camera_active:
            frame = camera.get_frame()
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')
        else:
            # If camera is off, yield a blank or placeholder frame (optional)
            # For now, we just yield nothing or a small pause to save CPU
            camera.video.release() # Release resource
            break 

@app.route('/video_feed')
def video_feed():
    global camera_active
    if camera_active:
        return Response(gen(VideoCamera()),
                        mimetype='multipart/x-mixed-replace; boundary=frame')
    else:
        # Return a static image or empty response if stopped
        return "Camera Off"

# NEW: Routes to handle buttons
@app.route('/start_session', methods=['POST'])
def start_session():
    global camera_active
    camera_active = True
    return jsonify({"status": "started", "message": "Camera started"})

@app.route('/stop_session', methods=['POST'])
def stop_session():
    global camera_active
    camera_active = False
    # HERE is where we will eventually save data to the database!
    # duration = request.json.get('duration') 
    # save_to_db(duration)
    return jsonify({"status": "stopped", "message": "Session saved"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)