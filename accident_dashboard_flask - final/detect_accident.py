import cv2
import os
import datetime
import numpy as np
import smtplib
import mysql.connector
from email.message import EmailMessage
from ultralytics import YOLO
from geopy.geocoders import OpenCage
from deep_sort_realtime.deepsort_tracker import DeepSort
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# ✅ Load YOLOv8 model
model = YOLO("yolov8n.pt")

# ✅ Initialize DeepSORT Tracker
tracker = DeepSort(max_age=30)

# ✅ Create directories for saving images
accident_folder = "accident_frames"
fire_folder = "fire_frames"
os.makedirs(accident_folder, exist_ok=True)
os.makedirs(fire_folder, exist_ok=True)

# ✅ Vehicle class IDs from COCO dataset (car, motorcycle, bus, truck)
VEHICLE_CLASSES = [2, 3, 5, 7]

# ✅ Fire detection HSV range
LOWER_FIRE = np.array([10, 150, 150], dtype=np.uint8)
UPPER_FIRE = np.array([30, 255, 255], dtype=np.uint8)

# ✅ OpenCage API Configuration
OPENCAGE_API_KEY = "04b06bcfe73946a0a9a0b669acd88343"
geolocator = OpenCage(OPENCAGE_API_KEY)

# ✅ MySQL Database Configuration
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = "Alex@0307"
DB_NAME = "accident_detection"

# ✅ SMTP Email Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "alexpandian0307@gmail.com"
SENDER_PASSWORD = "yaga ezmu sbtx zyky"  # Use App Password if 2FA is enabled
RECEIVER_EMAIL = "dhanushdarkshine@gmail.com"

# ✅ Function to check if two bounding boxes overlap (collision detection)
def calculate_iou(box1, box2):
    x1, y1, x2, y2 = box1
    x1_, y1_, x2_, y2_ = box2

    xi1, yi1 = max(x1, x1_), max(y1, y1_)
    xi2, yi2 = min(x2, x2_), min(y2, y2_)
    inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    box1_area = (x2 - x1) * (y2 - y1)
    box2_area = (x2_ - x1_) * (y2_ - y1_)
    iou = inter_area / float(box1_area + box2_area - inter_area)
    return iou

def is_collision(box1, box2, iou_threshold=0.4):
    return calculate_iou(box1, box2) > iou_threshold

# ✅ Function to get Google Maps Location
def get_location(lat, lon):
    try:
        location = geolocator.reverse((lat, lon), exactly_one=True)
        return location.address if location else "Unknown Location"
    except:
        return "Location Error"

# ✅ Function to send email alerts
def send_email(image_path, event_type, gps_location):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL
        msg['Subject'] = f"🚨 Alert: {event_type} Detected!"

        body = f"An event has been detected: {event_type}\nLocation: {gps_location}\nGoogle Maps:https://maps.app.goo.gl/mzvQ5Jn7oBGb38Se9?q={gps_location}"
        msg.attach(MIMEText(body, 'plain'))

        with open(image_path, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(image_path)}")
            msg.attach(part)

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        server.quit()
        print("✅ Email alert sent successfully!")
    except Exception as e:
        print(f"❌ Error sending email: {e}")

# ✅ Function to save event details to MySQL
def save_to_database(event_type, gps_location, image_path):
    try:
        conn = mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
        cursor = conn.cursor()
        sql = "INSERT INTO detections (event_type, location, image_path, timestamp) VALUES (%s, %s, %s, NOW())"
        values = (event_type, gps_location, image_path)
        cursor.execute(sql, values)
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Data saved to MySQL database!")
    except mysql.connector.Error as err:
        print(f"❌ MySQL Error: {err}")

# ✅ Open webcam/video feed
cap = cv2.VideoCapture(0)
while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break
    results = model(frame, conf=0.5)

    detection_list = []
    for r in results:
        for box in r.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            cls = int(box.cls[0])
            if cls in VEHICLE_CLASSES:
                detection_list.append(([x1, y1, x2, y2], float(box.conf[0]), cls))

    tracker_outputs = tracker.update_tracks(detection_list, frame=frame)
    accident_detected = False
    fire_detected = False
    save_path = None  # ✅ Ensure `save_path` is always defined

    for track in tracker_outputs:
        track_id = track.track_id
        ltrb = track.to_ltrb()
        x1, y1, x2, y2 = map(int, ltrb)

        for other_track in tracker_outputs:
            if track.track_id != other_track.track_id:
                if is_collision(ltrb, other_track.to_ltrb()):
                    accident_detected = True
                    event_type = "Accident"
                    save_path = f"{accident_folder}/accident_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                    cv2.putText(frame, "Accident", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)

    # ✅ Fire Detection
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, LOWER_FIRE, UPPER_FIRE)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in contours:
        if cv2.contourArea(cnt) > 1000:
            x, y, w, h = cv2.boundingRect(cnt)
            fire_detected = True
            event_type = "Car on Fire"
            save_path = f"{fire_folder}/fire_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            cv2.putText(frame, "Car on Fire!", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 165, 255), 3)
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 165, 255), 4)

    # ✅ Save Image, Send Email & Store in Database (ONLY IF EVENT DETECTED)
    if save_path:
        cv2.imwrite(save_path, frame)
        gps_location = get_location(12.9716, 77.5946)
        send_email(save_path, event_type, gps_location)
        save_to_database(event_type, gps_location, save_path)

    cv2.imshow("Accident & Fire Detection", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break
cap.release()
cv2.destroyAllWindows()
