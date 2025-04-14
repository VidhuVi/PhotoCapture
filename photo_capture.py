import cv2
import mediapipe as mp
import time
import qrcode
import threading
import os
import platform
from flask import Flask, send_file
import socket
import subprocess

# === CONFIG ===
PHOTO_LIFETIME = 10  # Auto-delete photos and QR codes after 10 seconds
QR_DISPLAY_DURATION = 10  # Seconds QR stays open
IMG_DISPLAY_DURATION = 5  # Seconds image stays open

# === Flask Setup ===
app = Flask(__name__)
latest_photo = "photo_0.jpg"

@app.route("/")
def serve_qr_image():
    return send_file(latest_photo, mimetype='image/jpeg')

def run_server():
    print("🚀 Starting local server...")
    app.run(port=5000, host="0.0.0.0", debug=False)

server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()

# === Cleanup Thread ===
def cleanup_files(folder=".", lifetime=PHOTO_LIFETIME):
    while True:
        now = time.time()
        for filename in os.listdir(folder):
            if (filename.startswith("photo_") and filename.endswith(".jpg")) or \
               (filename.startswith("qr_") and filename.endswith(".png")):
                path = os.path.join(folder, filename)
                try:
                    if os.path.isfile(path) and (now - os.path.getmtime(path)) > lifetime:
                        os.remove(path)
                        print(f"🗑️ Deleted {filename}")
                except Exception as e:
                    print(f"Error deleting {filename}: {e}")
        time.sleep(10)

cleanup_thread = threading.Thread(target=cleanup_files, daemon=True)
cleanup_thread.start()

# === Utility ===
def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        IP = s.getsockname()[0]
    except:
        IP = "127.0.0.1"
    finally:
        s.close()
    return IP

local_ip = get_ip()
print(f"🌐 Local IP: http://{local_ip}:5000")

def open_file_fullscreen(filepath, duration=5):
    try:
        if platform.system() == "Windows":
            subprocess.Popen(["start", "/max", filepath], shell=True)
            time.sleep(duration)
            if filepath.endswith(".png") or filepath.endswith(".jpg"):
                # Give some time for the image viewer to open
                time.sleep(0.5)
                subprocess.call(['powershell', '-Command', '(Get-Process Microsoft.Photos).MainWindowHandle | ForEach-Object { [System.Windows.Forms.SendKeys]::SendWait("%{F11}") }'], stderr=subprocess.DEVNULL)
                time.sleep(0.5) # Give time for fullscreen transition
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-a", "Preview", "-F", filepath])
            time.sleep(duration)
        else:  # Linux
            subprocess.Popen(["xdg-open", filepath])
            time.sleep(duration)

    except Exception as e:
        print(f"Error opening file {filepath}: {e}")

# === MediaPipe Setup ===
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=1)
cap = cv2.VideoCapture(0)
photo_count = 0
last_capture_time = 0

# === Gesture Detection ===
def is_thumbs_up(landmarks):
    thumb_tip = landmarks[4]
    thumb_ip = landmarks[3]
    index_tip = landmarks[8]
    middle_tip = landmarks[12]
    ring_tip = landmarks[16]
    pinky_tip = landmarks[20]

    thumb_up = thumb_tip.y < thumb_ip.y
    fingers_down = (
        index_tip.y > landmarks[6].y and
        middle_tip.y > landmarks[10].y and
        ring_tip.y > landmarks[14].y and
        pinky_tip.y > landmarks[18].y
    )
    return thumb_up and fingers_down

cv2.namedWindow("Gesture Capture", cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty("Gesture Capture", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

# === Main Loop ===
while True:
    success, img = cap.read()
    if not success:
        break

    img = cv2.flip(img, 1)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)

    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            if is_thumbs_up(hand_landmarks.landmark):
                current_time = time.time()
                if current_time - last_capture_time > 2:
                    filename = f"photo_{photo_count}.jpg"
                    cv2.imwrite(filename, img)
                    latest_photo = filename
                    print(f"📸 Photo saved as {filename}")

                    # Show captured image fullscreen briefly
                    threading.Thread(target=open_file_fullscreen, args=(filename, IMG_DISPLAY_DURATION), daemon=True).start()

                    # Generate QR code
                    url = f"http://{local_ip}:5000"
                    qr = qrcode.make(url)
                    qr_filename = f"qr_{photo_count}.png"
                    qr.save(qr_filename)
                    print(f"📎 QR code saved as {qr_filename}")

                    # Show QR code fullscreen after a short delay
                    def delayed_qr():
                        time.sleep(IMG_DISPLAY_DURATION + 1)  # Wait for image display to finish
                        open_file_fullscreen(qr_filename, QR_DISPLAY_DURATION)
                    threading.Thread(target=delayed_qr, daemon=True).start()

                    last_capture_time = current_time
                    photo_count += 1
                    cv2.setWindowProperty("Gesture Capture", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN) # Ensure fullscreen after capture

    cv2.imshow("Gesture Capture", img)
    cv2.setWindowProperty("Gesture Capture", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN) # Keep it fullscreen in the loop
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()