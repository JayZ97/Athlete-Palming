from pymongo import MongoClient, errors
from datetime import datetime

# --- MongoDB Connection (Graceful) ---
try:
    client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
    # Force a connection check
    client.server_info()
    db = client["athlete_palming"]
    sessions_collection = db["palming_sessions"]
    db_available = True
    print("✅ MongoDB connected successfully.")
except errors.ServerSelectionTimeoutError:
    db_available = False
    sessions_collection = None
    print("⚠️  MongoDB not available — sessions will not be saved. Start mongod to enable persistence.")


def save_session(start_time, end_time, duration_seconds, audio_track=None):
    """Save a completed palming session to MongoDB."""
    if not db_available:
        print(f"   ⏩ Skipped saving session ({duration_seconds}s) — MongoDB offline")
        return None

    session_doc = {
        "session_date": start_time.strftime("%Y-%m-%d"),
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": duration_seconds,
        "day_of_week": start_time.strftime("%A"),
        "audio_track": audio_track,
        "created_at": datetime.now().isoformat()
    }
    result = sessions_collection.insert_one(session_doc)
    return str(result.inserted_id)


def get_all_sessions(limit=50):
    """Retrieve all sessions, most recent first."""
    if not db_available:
        return []

    sessions = list(
        sessions_collection.find({}, {"_id": 0})
        .sort("start_time", -1)
        .limit(limit)
    )
    return sessions


def get_session_stats():
    """Return aggregate stats for the dashboard."""
    if not db_available:
        return {"total_sessions": 0, "avg_duration": 0, "today_count": 0, "total_time_seconds": 0}

    total_sessions = sessions_collection.count_documents({})

    # Average duration
    pipeline = [{"$group": {"_id": None, "avg_duration": {"$avg": "$duration_seconds"}}}]
    avg_result = list(sessions_collection.aggregate(pipeline))
    avg_duration = round(avg_result[0]["avg_duration"], 1) if avg_result else 0

    # Today's sessions
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_count = sessions_collection.count_documents({"session_date": today_str})

    # Total time spent (sum of all durations)
    total_pipeline = [{"$group": {"_id": None, "total": {"$sum": "$duration_seconds"}}}]
    total_result = list(sessions_collection.aggregate(total_pipeline))
    total_time = total_result[0]["total"] if total_result else 0

    return {
        "total_sessions": total_sessions,
        "avg_duration": avg_duration,
        "today_count": today_count,
        "total_time_seconds": total_time
    }
