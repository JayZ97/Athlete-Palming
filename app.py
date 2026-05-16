from flask import Flask, render_template, jsonify, request
from database import save_session, get_all_sessions, get_session_stats
from datetime import datetime

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/save_session', methods=['POST'])
def save_session_endpoint():
    """Receives JSON data from the browser when a palming session ends."""
    data = request.get_json()
    stretches = data.get('stretches', [])
    audio_track = data.get('audio_track')
    
    saved_count = 0
    total_duration = 0
    
    for s in stretches:
        start_dt = datetime.fromtimestamp(s['start_time'])
        end_dt = datetime.fromtimestamp(s['end_time'])
        duration = s['duration']
        
        # Save to MongoDB
        save_session(
            start_time=start_dt,
            end_time=end_dt,
            duration_seconds=duration,
            audio_track=audio_track
        )
        saved_count += 1
        total_duration += duration

    return jsonify({
        "status": "success",
        "message": f"Saved {saved_count} stretch(es)",
        "total_duration": total_duration
    })

@app.route('/api/sessions')
def api_sessions():
    """Return all recorded sessions as JSON."""
    return jsonify(get_all_sessions())

@app.route('/api/sessions/stats')
def api_session_stats():
    """Return aggregate session statistics."""
    return jsonify(get_session_stats())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)