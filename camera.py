import cv2
import mediapipe as mp
import numpy as np
import time
import threading

class VideoCamera(object):
    def __init__(self):
        self.video = cv2.VideoCapture(0)
        # Explicitly set resolution to prevent webcam defaulting to HD
        self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        # --- Threaded Frame Capture ---
        # A background thread continuously pulls frames from the webcam
        # so get_frame() always has the freshest frame instantly without blocking
        self.grabbed, self.current_frame = self.video.read()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        
        # --- MediaPipe Setup ---
        self.mp_holistic = mp.solutions.holistic
        self.mp_drawing = mp.solutions.drawing_utils
        self.holistic = self.mp_holistic.Holistic(
            model_complexity=0,            # Lite pose model — we don't use pose landmarks,
                                           # so this gives a big FPS boost with zero accuracy loss
                                           # on the face/hand landmarks we actually use (#33, #263, #9)
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        # --- Thresholds ---
        # Tightened MAX_DIST for palm center (#9) — palm center sits closer to the eye
        # than the wrist (#0), so a smaller threshold is more accurate
        self.MAX_DIST = 0.20
        self.MIN_DIST = 0.01
        self.FRAME_MARGIN = 0.05
        
        # --- State Variables ---
        self.start_time = None
        self.session_duration = 0
        self.is_currently_palming = False
        self.last_face_pos = None
        
        # --- Stretch Tracking ---
        # Each completed palming stretch is recorded automatically
        self.completed_stretches = []     # List of {"duration": int, "start_time": float, "end_time": float}
        self.current_stretch_start = None # Epoch time when current palming stretch began

    def _capture_loop(self):
        """Background thread: continuously reads frames from the webcam hardware."""
        while True:
            grabbed, frame = self.video.read()
            if not grabbed:
                continue
            with self._lock:
                self.grabbed = grabbed
                self.current_frame = frame

    def __del__(self):
        self.video.release()

    def get_distance(self, p1, p2):
        return np.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)

    def get_all_stretches(self):
        """Return all completed stretches plus any currently active one."""
        stretches = list(self.completed_stretches)
        # If user is still palming when this is called, include the ongoing stretch
        if self.is_currently_palming and self.session_duration > 0 and self.current_stretch_start:
            stretches.append({
                "duration": self.session_duration,
                "start_time": self.current_stretch_start,
                "end_time": time.time()
            })
        return stretches

    def get_frame(self):
        # Grab the latest frame from the background thread (non-blocking)
        with self._lock:
            if not self.grabbed or self.current_frame is None:
                return None
            frame = self.current_frame.copy()

        # Flip horizontally for mirror effect
        frame = cv2.flip(frame, 1)

        # 1. Processing
        image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.holistic.process(image_rgb)
        
        warning_msg = ""
        d_l, d_r = 0, 0
        
        # Capture previous state to detect when the user STOPS palming
        was_palming = self.is_currently_palming
        
        # 2. Logic: Face Tracking with Memory
        if results.face_landmarks:
            e_l = results.face_landmarks.landmark[33]
            e_r = results.face_landmarks.landmark[263]
            self.last_face_pos = (e_l, e_r)
            if self.is_currently_palming:
                self.is_currently_palming = False 
        elif self.last_face_pos:
            e_l, e_r = self.last_face_pos
        else:
            e_l, e_r = None, None

        # 3. Logic: Hand Tracking — using palm center (#9, Middle Finger MCP)
        #    instead of wrist (#0) for more accurate palming verification
        if results.left_hand_landmarks and results.right_hand_landmarks and e_l and e_r:
            p_l = results.left_hand_landmarks.landmark[9]   # Palm center (Middle Finger MCP)
            p_r = results.right_hand_landmarks.landmark[9]  # Palm center (Middle Finger MCP)

            # Boundary Check
            if not (self.FRAME_MARGIN < p_l.x < 1-self.FRAME_MARGIN and self.FRAME_MARGIN < p_l.y < 1-self.FRAME_MARGIN):
                warning_msg = "CENTER HANDS"

            d_l = self.get_distance(p_l, e_l)
            d_r = self.get_distance(p_r, e_r)

            if (self.MIN_DIST < d_l < self.MAX_DIST) and (self.MIN_DIST < d_r < self.MAX_DIST):
                self.is_currently_palming = True
            elif d_l > self.MAX_DIST + 0.1 or d_r > self.MAX_DIST + 0.1:
                self.is_currently_palming = False

        # --- LOGIC: DETECT STRETCH END & AUTO-RECORD ---
        if was_palming and not self.is_currently_palming:
            # Save the completed stretch if it had meaningful duration
            if self.session_duration > 0 and self.current_stretch_start:
                self.completed_stretches.append({
                    "duration": self.session_duration,
                    "start_time": self.current_stretch_start,
                    "end_time": time.time()
                })
                print(f"\n🏁 Stretch #{len(self.completed_stretches)} Finished! "
                      f"Duration: {self.session_duration}s\n")

        # 4. Timer Logic
        if self.is_currently_palming:
            if self.start_time is None:
                self.start_time = time.time()
                self.current_stretch_start = time.time()
            self.session_duration = int(time.time() - self.start_time)
        else:
            self.start_time = None
            self.session_duration = 0

        # 5. UI Overlay — subtle, themed status badge
        h, w = frame.shape[:2]
        overlay = frame.copy()

        if self.is_currently_palming:
            label = f"Active  {self.session_duration}s"
            dot_color = (130, 210, 160)     # Green dot
        else:
            label = warning_msg if warning_msg else "Waiting..."
            dot_color = (180, 180, 180)     # Grey dot

        # Measure text size for pill background
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        thickness = 2
        (text_w, text_h), baseline = cv2.getTextSize(label, font, font_scale, thickness)

        # Position: top-left with padding
        pad_x, pad_y = 16, 10
        x1, y1 = 14, 14
        x2 = x1 + text_w + pad_x * 2 + 22  # extra space for dot
        y2 = y1 + text_h + pad_y * 2

        # Semi-transparent rounded rectangle
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (40, 40, 40), -1)
        alpha = 0.55
        frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)

        # Status dot
        dot_x = x1 + pad_x + 5
        dot_y = y1 + pad_y + text_h // 2
        cv2.circle(frame, (dot_x, dot_y), 5, dot_color, -1)

        # Text
        text_x = dot_x + 16
        text_y = y1 + pad_y + text_h
        cv2.putText(frame, label, (text_x, text_y), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

        # 6. Encode for Web Streaming
        ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return jpeg.tobytes()