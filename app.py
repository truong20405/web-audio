import threading
import time
import logging
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, jsonify
from googleapiclient.discovery import build
import yt_dlp
from flask_caching import Cache
from pyngrok import ngrok
from circuitbreaker import circuit

# region [Cấu hình ứng dụng]
app = Flask(__name__)

# Cấu hình từ lớp Config
class Config:
    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = 600  # 10 phút
    YOUTUBE_API_KEY = "AIzaSyBX_-obwbQ3MZKeMTYS9x8SzjiXojl3nWs"  # Giữ nguyên hardcode
    NGROK_TOKEN = "2t6vMW5EgLfy49FXzMQttNqZtOZ_2Tf1QcsPquPSXAvZPtavZ"

app.config.from_object(Config())

# Khởi tạo YouTube API client một lần
youtube = build(
    "youtube",
    "v3",
    developerKey=app.config["YOUTUBE_API_KEY"],
    cache_discovery=False  # Tối ưu hiệu năng
)
# endregion

# region [Cấu hình Cache và Logging]
cache = Cache(app)
handler = RotatingFileHandler('app.log', maxBytes=10000, backupCount=3)
handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
app.logger.addHandler(handler)
# endregion

# region [Xử lý đa luồng]
thread_pool = ThreadPoolExecutor(max_workers=10)
active_threads = {}
thread_lock = threading.Lock()

def send_ping(user_id):
    try:
        while True:
            with thread_lock:
                if user_id not in active_threads:
                    break
            app.logger.info(f"Ping từ user {user_id}")
            time.sleep(300)
    except Exception as e:
        app.logger.error(f"Lỗi ping: {str(e)}")
# endregion

# region [Routes]
@app.route("/start_ping", methods=["POST"])
def start_ping():
    user_id = request.form.get("user_id")
    if not user_id:
        return jsonify({"error": "Thiếu user_id"}), 400

    with thread_lock:
        if user_id in active_threads:
            return jsonify({"message": "Ping đã được bắt đầu"}), 200

        future = thread_pool.submit(send_ping, user_id)
        active_threads[user_id] = future
        app.logger.info(f"Bắt đầu ping cho user {user_id}")

    return jsonify({"message": "Ping bắt đầu"}), 200

@app.route("/stop_ping", methods=["POST"])
def stop_ping():
    user_id = request.form.get("user_id")
    if not user_id:
        return jsonify({"error": "Thiếu user_id"}), 400

    with thread_lock:
        if user_id in active_threads:
            del active_threads[user_id]
            app.logger.info(f"Dừng ping cho user {user_id}")

    return jsonify({"message": "Ping dừng"}), 200

@circuit(failure_threshold=3, recovery_timeout=60)  # Circuit Breaker
@cache.memoize(timeout=600)  # Cache 10 phút
def search_youtube(query):
    try:
        search_response = youtube.search().list(
            q=query,
            part="id,snippet",
            maxResults=10,
            type="video"
        ).execute()

        return [{
            "id": item["id"]["videoId"],
            "title": item["snippet"]["title"].replace('&quot;', ''),
            "thumbnail": item["snippet"]["thumbnails"]["high"]["url"],
            "channel": item["snippet"]["channelTitle"]
        } for item in search_response["items"]]
    
    except Exception as e:
        app.logger.error(f"Lỗi YouTube API: {str(e)}")
        raise

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        query = request.form.get("query")
        return render_template("index.html", videos=search_youtube(query))
    return render_template("index.html", videos=[])

@app.route("/play/<video_id>", methods=["GET"])
def play_audio(video_id):
    try:
        ydl_opts = {'format': 'bestaudio/best', 'quiet': True}
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            audio_url = info['url']
            title = info.get('title', '')

        related_videos = [v for v in search_youtube(title) if v["id"] != video_id]
        return render_template("player.html", 
                             video_title=title,
                             audio_url=audio_url,
                             related_videos=related_videos)
    
    except yt_dlp.utils.DownloadError as e:
        app.logger.error(f"Lỗi tải video: {str(e)}")
        return jsonify({"error": "Không thể tải video"}), 500
    
    except yt_dlp.utils.ExtractorError as e:
        app.logger.error(f"Lỗi trích xuất: {str(e)}")
        return jsonify({"error": "Lỗi xử lý video"}), 500

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "timestamp": time.time(),
        "active_threads": len(active_threads)
    })
# endregion

if __name__ == "__main__":
    ngrok.set_auth_token(app.config["NGROK_TOKEN"]) 
    public_url = ngrok.connect(5000).public_url
    app.logger.info(f"Khởi chạy ứng dụng tại: {public_url}")
    app.run(host="0.0.0.0", port=5000)
