
from flask import Flask, request, jsonify
from pytube import YouTube

app = Flask(__name__)

@app.route("/info", methods=["GET"])
def get_info():
    url = request.args.get("url")
    try:
        yt = YouTube(url)
        return jsonify({
            "title": yt.title,
            "author": yt.author,
            "length": yt.length,
            "thumbnail": yt.thumbnail_url
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/download", methods=["GET"])
def get_download_url():
    url = request.args.get("url")
    try:
        yt = YouTube(url)
        stream = yt.streams.filter(progressive=True, file_extension="mp4") \
                        .order_by("resolution") \
                        .desc().first()
        return jsonify({
            "download_url": stream.url,
            "resolution": stream.resolution,
            "filesize_mb": round(stream.filesize / 1024 / 1024, 2),
            "title": yt.title
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    app.run(debug=True)