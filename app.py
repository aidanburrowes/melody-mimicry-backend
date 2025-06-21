from flask import Flask, request, jsonify
from songs import getSong
from artists import getAllArtists
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route("/get_all_artists", methods=['GET'])
def get_all_artists():
    all_artists = getAllArtists()
    return jsonify([a[0].replace("'", "") for a in all_artists])

@app.route("/get_all_songs", methods=['GET'])
def get_all_songs():
    from songs import getAllSongs
    all_songs = getAllSongs()
    return jsonify([s[0].replace("'", "") for s in all_songs])

@app.route("/get_song", methods=['POST'])
def get_song():
    try:
        data = request.get_json()
        artist_name = data.get("artist")
        song_name = data.get("song")
        if not artist_name or not song_name:
            return jsonify({"error": "Missing artist or song"}), 400
        result = getSong(song_name, artist_name)
        return jsonify({"path": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860)
