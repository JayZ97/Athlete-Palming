import cv2
import mediapipe as mp
import numpy as np
import time

class VideoCamera(object):
    def __init__(self):
        self.video = cv2.VideoCapture(0)
        
        # --- MediaPipe Setup ---
        self.mp_holistic = mp.solutions.holistic
        self.mp_drawing = mp.solutions.drawing_utils
        self.holistic = self.mp_holistic.Holistic(min_detection_confidence=0.5, min_tracking_confidence=0.5)
        
        # --- Thresholds ---
        self.MAX_DIST = 0.25
        self.MIN_DIST = 0.01
        self.FRAME_MARGIN = 0.05
        
        # --- State Variables ---
        self.start_time = None
        self.session_duration = 0
        self.is_currently_palming = False
        self.last_face_pos = None

    def __del__(self):
        self.video.release()

    def get_distance(self, p1, p2):
        return np.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)

    def get_frame(self):
        success, frame = self.video.read()
        if not success:
            return None

        # 1. Processing
        image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.holistic.process(image_rgb)
        
        warning_msg = ""
        d_l, d_r = 0, 0
        
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

        # 3. Logic: Hand Tracking
        if results.left_hand_landmarks and results.right_hand_landmarks and e_l and e_r:
            p_l = results.left_hand_landmarks.landmark[0]
            p_r = results.right_hand_landmarks.landmark[0]

            # Boundary Check
            if not (self.FRAME_MARGIN < p_l.x < 1-self.FRAME_MARGIN and self.FRAME_MARGIN < p_l.y < 1-self.FRAME_MARGIN):
                warning_msg = "CENTER HANDS"

            d_l = self.get_distance(p_l, e_l)
            d_r = self.get_distance(p_r, e_r)

            if (self.MIN_DIST < d_l < self.MAX_DIST) and (self.MIN_DIST < d_r < self.MAX_DIST):
                self.is_currently_palming = True
            elif d_l > self.MAX_DIST + 0.1 or d_r > self.MAX_DIST + 0.1:
                self.is_currently_palming = False

        # --- DRAWING SECTION (COMMENTED OUT FOR CLEAN LOOK) ---
        # if results.face_landmarks:
        #     self.mp_drawing.draw_landmarks(frame, results.face_landmarks, self.mp_holistic.FACEMESH_CONTOURS,
        #                                   self.mp_drawing.DrawingSpec(color=(0,255,0), thickness=1, circle_radius=1))
        # self.mp_drawing.draw_landmarks(frame, results.left_hand_landmarks, self.mp_holistic.HAND_CONNECTIONS)
        # self.mp_drawing.draw_landmarks(frame, results.right_hand_landmarks, self.mp_holistic.HAND_CONNECTIONS)
        # -------------------------------------------------------

        # 5. UI & Feedback
        if self.is_currently_palming:
            if self.start_time is None:
                self.start_time = time.time()
            self.session_duration = int(time.time() - self.start_time)
            cv2.putText(frame, f"ACTIVE: {self.session_duration}s", (10, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 3)
        else:
            self.start_time = None
            cv2.putText(frame, warning_msg if warning_msg else "WAITING...", (10, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        # 6. Encode for Web Streaming
        ret, jpeg = cv2.imencode('.jpg', frame)
        return jpeg.tobytes()