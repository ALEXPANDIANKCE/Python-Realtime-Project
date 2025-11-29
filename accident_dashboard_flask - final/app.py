from flask import Flask, render_template, Response, jsonify, request, redirect, url_for, session, send_from_directory
import cv2
import os
import datetime
import numpy as np
import smtplib
import mysql.connector
import json
import threading
from email.message import EmailMessage
from geopy.geocoders import OpenCage
from deep_sort_realtime.deepsort_tracker import DeepSort
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from ultralytics import YOLO

app = Flask(__name__)
app.secret_key = '5fc6674bf560ecb1bbde71fe1e472e75e4ba7a3d945acfb5ce599ecdf0d27652'  # Change this!

# Global detection status
detection_status = {
    'accident_detected': False,
    'fire_detected': False,
    'last_event': None,
    'last_image_path': None,
    'location': None,
    'alert_sent': False,
    'camera_connected': False  # Add camera connection status
}

class AccidentDetector:
    def __init__(self, status_callback):
        # Initialize all components
        self.model = YOLO("yolov8n.pt")
        self.tracker = DeepSort(max_age=30)
        self.status_callback = status_callback
        self.cap = cv2.VideoCapture(0)  # Corrected: Moved inside __init__
        self.running = False
        self.camera_connected = False # Track connection

        # Vehicle class IDs
        self.VEHICLE_CLASSES = [2, 3, 5, 7]

        # Fire detection range
        self.LOWER_FIRE = np.array([10, 150, 150], dtype=np.uint8)
        self.UPPER_FIRE = np.array([30, 255, 255], dtype=np.uint8)

        # Create directories
        self.accident_folder = "static/accident_frames"
        self.fire_folder = "static/fire_frames"
        os.makedirs(self.accident_folder, exist_ok=True)
        os.makedirs(self.fire_folder, exist_ok=True)

        # Configuration
        self.OPENCAGE_API_KEY = "04b06bcfe73946a0a9a0b669acd88343"  # Change this!
        self.geolocator = OpenCage(self.OPENCAGE_API_KEY)

        # Database config
        self.DB_CONFIG = {
            'host': "localhost",
            'user': "root",
            'password': "Alex@0307",  # Change this!
            'database': "accident_detection"
        }

        # Email config
        self.EMAIL_CONFIG = {
            'server': "smtp.gmail.com",  # Or your email provider
            'port': 587,
            'sender': "alexpandian0307@gmail.com",  # Change this!
            'password': "yaga ezmu sbtx zyky",  # Change this!  Use an App Password
            'receiver': "dhanushdarkshine@gmail.com"  # Change this!
        }
        self.thread = None #added thread

    def calculate_iou(self, box1, box2):
        x1, y1, x2, y2 = box1
        x1_, y1_, x2_, y2_ = box2

        xi1, yi1 = max(x1, x1_), max(y1, y1_)
        xi2, yi2 = min(x2, x2_), min(y2, y2_)
        inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
        box1_area = (x2 - x1) * (y2 - y1)
        box2_area = (x2_ - x1_) * (y2_ - y1_)
        return inter_area / float(box1_area + box2_area - inter_area)

    def is_collision(self, box1, box2, iou_threshold=0.4):
        return self.calculate_iou(box1, box2) > iou_threshold

    def get_location(self, lat=12.9716, lon=77.5946):  # Default Bangalore
        try:
            location = self.geolocator.reverse((lat, lon), exactly_one=True)
            return location.address if location else "Unknown Location"
        except Exception as e:
            print(f"Geocoding Error: {e}")
            return "Location Error"

    def send_email(self, image_path, event_type, gps_location):
        try:
            msg = MIMEMultipart()
            msg['From'] = self.EMAIL_CONFIG['sender']
            msg['To'] = self.EMAIL_CONFIG['receiver']
            msg['Subject'] = f"🚨 Alert: {event_type} Detected!"

            body = f"An event has been detected: {event_type}\nLocation: {gps_location}\nGoogle Maps: https://maps.app.goo.gl/mzvQ5Jn7oBGb38Se9?q={gps_location}"
            msg.attach(MIMEText(body, 'plain'))

            with open(image_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(image_path)}")
                msg.attach(part)

            with smtplib.SMTP(self.EMAIL_CONFIG['server'], self.EMAIL_CONFIG['port']) as server:
                server.starttls()
                server.login(self.EMAIL_CONFIG['sender'], self.EMAIL_CONFIG['password'])
                server.send_message(msg)
            print("✅ Email alert sent successfully!")
            return True
        except Exception as e:
            print(f"❌ Error sending email: {e}")
            return False

    def save_to_database(self, event_type, gps_location, image_path):
        try:
            conn = mysql.connector.connect(**self.DB_CONFIG)
            cursor = conn.cursor()
            sql = "INSERT INTO detections (event_type, location, image_path, timestamp) VALUES (%s, %s, %s, NOW())"
            cursor.execute(sql, (event_type, gps_location, image_path))
            conn.commit()
            print("✅ Data saved to MySQL database!")
            return True
        except mysql.connector.Error as err:
            print(f"❌ MySQL Error: {err}")
            return False

    def generate_frames(self):
        self.running = True
        self.camera_connected = True #set
        self.status_callback({'camera_connected': True})
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                self.running = False
                self.camera_connected = False
                self.status_callback({'camera_connected': False})
                break

            # Process frame
            results = self.model(frame, conf=0.5)
            detection_list = []

            for r in results:
                for box in r.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    cls = int(box.cls[0])
                    if cls in self.VEHICLE_CLASSES:
                        detection_list.append(([x1, y1, x2, y2], float(box.conf[0]), cls))

            tracker_outputs = self.tracker.update_tracks(detection_list, frame=frame)
            accident_detected = False
            fire_detected = False
            save_path = None
            event_type = None

            # Accident detection
            for track in tracker_outputs:
                ltrb = track.to_ltrb()
                for other_track in tracker_outputs:
                    if track.track_id != other_track.track_id and self.is_collision(ltrb, other_track.to_ltrb()):
                        accident_detected = True
                        event_type = "Accident"
                        x1, y1, x2, y2 = map(int, ltrb)
                        save_path = f"{self.accident_folder}/accident_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                        cv2.putText(frame, "ACCIDENT!", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                        break

            # Fire detection
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, self.LOWER_FIRE, self.UPPER_FIRE)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                if cv2.contourArea(cnt) > 1000:
                    x, y, w, h = cv2.boundingRect(cnt)
                    fire_detected = True
                    event_type = "Car on Fire"
                    save_path = f"{self.fire_folder}/fire_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                    cv2.putText(frame, "FIRE DETECTED!", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 165, 255), 3)
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 165, 255), 4)

            # Handle detected events
            if save_path and (accident_detected or fire_detected):
                cv2.imwrite(save_path, frame)
                gps_location = self.get_location()

                # Update status
                self.status_callback({
                    'accident_detected': accident_detected,
                    'fire_detected': fire_detected,
                    'last_event': event_type,
                    'last_image_path': save_path.replace('static/', ''),
                    'location': gps_location,
                    'alert_sent': False,
                    'camera_connected': True #keep
                })

                # Send alert in background
                threading.Thread(target=self.handle_alert, args=(save_path, event_type, gps_location)).start()

            # Convert frame to JPEG
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    def handle_alert(self, image_path, event_type, location):
        email_sent = self.send_email(image_path, event_type, location)
        db_saved = self.save_to_database(event_type, location, image_path)

        if email_sent and db_saved:
            self.status_callback({'alert_sent': True, 'camera_connected': self.camera_connected}) #keep

    def start(self):
        if not self.running:
            self.thread = threading.Thread(target=self.generate_frames)
            self.thread.start()

    def stop(self):
        if self.running:
            self.running = False
            self.cap.release()
            cv2.destroyAllWindows()
            self.thread.join()  # Wait for thread to finish
            self.camera_connected = False
            self.status_callback({'camera_connected': False})

USERS_FILE = 'users.json'
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'w') as f:
        json.dump({}, f)

def load_users():
    with open(USERS_FILE, 'r') as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f)
 #roudes

@app.route('/')
def login():
    return render_template('login.html')

@app.route('/register')
def register():
    return render_template('register.html')

@app.route('/submit_login', methods=['POST'])
def submit_login():
    data = request.get_json()
    users = load_users()
    username = data.get('username')
    password = data.get('password')
    if username in users and users[username] == password:
        session['username'] = username  # Set session
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/submit_register', methods=['POST'])
def submit_register():
    data = request.get_json()
    users = load_users()
    username = data.get('username')
    password = data.get('password')
    if username in users:
        return jsonify({'success': False, 'message': 'User already exists'})
    users[username] = password
    save_users(users)
    return jsonify({'success': True})

@app.route('/dashboard')
def dashboard():
    return render_template('accident_dashboard.html')

@app.route('/video_feed')
def video_feed():
    if 'detector' not in globals():
        global detector
        detector = AccidentDetector(status_callback=lambda status: print(status))
    return Response(detector.generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/alerts')
def get_alerts():
    return jsonify({
        'latest_alert': latest_alert,
        'accident_count': accident_count,
        'fire_count': fire_count
    })

@app.route('/start_detection', methods=['POST'])
def start_detection():
    global detector
    if 'detector' not in globals():
        detector = AccidentDetector(status_callback=lambda status: print(status))
    detector.start()  # Start the detection thread
    return jsonify({'success': True, 'message': 'Camera started'})

@app.route('/stop_detection', methods=['POST'])
def stop_detection():
    global detector
    if 'detector' in globals():
        detector.stop()  # Stop the detection thread
    return jsonify({'success': True, 'message': 'Camera stopped'})

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True, threaded=True)

import cv2

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Camera not accessible")
else:
    print("Camera is working")
cap.release()
