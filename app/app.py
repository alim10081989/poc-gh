# PR workflow test — verifying build-test CI trigger
from flask import Flask, jsonify
import os

app = Flask(__name__)

APP_VERSION = os.environ.get("APP_VERSION", "dev")


@app.route("/")
def home():
    return jsonify({"message": "Hello from myapp", "version": APP_VERSION})


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"}), 200


@app.route("/readyz")
def readyz():
    return jsonify({"status": "ready"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
