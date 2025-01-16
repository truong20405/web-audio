import threading
import time
from flask import Flask, render_template, request, jsonify
from googleapiclient.discovery import build
from pytubefix import YouTube
from flask_caching import Cache
from pyngrok import ngrok

# Cấu hình ứng dụng Flask
app = Flask(__name__)

# Cấu hình cache
cache = Cache(app, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300})

# API Key của YouTube (Thay YOUR_YOUTUBE_API_KEY bằng API Key của bạn)
YOUTUBE_API_KEY = "AIzaSyBX_-obwbQ3MZKeMTYS9x8SzjiXojl3nWs"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

# Lưu trữ các luồng đang hoạt động
active_threads = {}
thread_lock = threading.Lock()

# Hàm gửi ping mỗi 5 phút
def send_ping(user_id):
    while True:
        with thread_lock:
            if user_id not in active_threads:
                break
        print(f"Ping từ user {user_id}")
        time.sleep(300)  # 5 phút

# Endpoint để bắt đầu gửi ping
@app.route("/start_ping", methods=["POST"])
def start_ping():
    user_id = request.form.get("user_id")
    if not user_id:
        return jsonify({"error": "Thiếu user_id"}), 400

    with thread_lock:
        if user_id in active_threads:
            return jsonify({"message": "Ping đã được bắt đầu"}), 200

        thread = threading.Thread(target=send_ping, args=(user_id,), daemon=True)
        active_threads[user_id] = thread
        thread.start()

    return jsonify({"message": "Ping bắt đầu"}), 200

# Endpoint để dừng gửi ping
@app.route("/stop_ping", methods=["POST"])
def stop_ping():
    user_id = request.form.get("user_id")
    if not user_id:
        return jsonify({"error": "Thiếu user_id"}), 400

    with thread_lock:
        if user_id in active_threads:
            del active_threads[user_id]

    return jsonify({"message": "Ping dừng"}), 200

# Hàm tìm kiếm video trên YouTube
@cache.memoize()
def search_youtube(query):
    youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=YOUTUBE_API_KEY)
    search_response = youtube.search().list(
        q=query,
        part="id,snippet",
        maxResults=10,
        type="video"
    ).execute()

    results = []
    for item in search_response["items"]:
        video_id = item["id"]["videoId"]
        title = item["snippet"]["title"]
        thumbnail = item["snippet"]["thumbnails"]["high"]["url"]
        channel = item["snippet"]["channelTitle"]
        results.append({"id": video_id, "title": title.replace('&quot;',''), "thumbnail": thumbnail, "channel": channel})
    return results

# Trang chủ
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        query = request.form.get("query")
        videos = search_youtube(query)
        return render_template("index.html", videos=videos)
    return render_template("index.html", videos=[])

# Phát âm thanh từ video
@app.route("/play/<video_id>", methods=["GET"])
def play_audio(video_id):
    try:
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        yt = YouTube(youtube_url)

        # Lấy danh sách gợi ý video
        related_videos = search_youtube(yt.title)  # Sử dụng tiêu đề của video để lấy gợi ý
        filtered_videos = [video for video in related_videos if video["id"] != video_id]

        # Lấy URL audio stream
        audio_stream = yt.streams.filter(only_audio=True).first()

        return render_template(
            "player.html",
            video_title=yt.title,
            audio_url=audio_stream.url,
            related_videos=filtered_videos,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    ngrok.set_auth_token("2rhX6ha9t6ZOuTGr06RguARDoRm_6UuwvzFwweMfFhPGL8gn8") 
    public_url = ngrok.connect(5000).public_url
    print(f"Ngrok URL: {public_url}")
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
    app.run(host="0.0.0.0", port=5000, threaded=True)
