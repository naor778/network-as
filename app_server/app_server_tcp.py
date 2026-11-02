import socket
import json
from pathlib import Path
import time

DELAY_ON = False
DELAY_SECONDS = 4


def load_config():
    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "config" / "config.json"
    with open(config_path, "r") as f:
        return json.load(f)


def fetch_file_from_origin(origin_ip, origin_port, filename):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((origin_ip, origin_port))

    request = (
        f"GET /{filename} HTTP/1.1\r\n"
        f"Host: origin.local\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )

    sock.sendall(request.encode("utf-8"))

    chunks = []
    while True:
        data = sock.recv(4096)
        if not data:
            break
        chunks.append(data)

    sock.close()
    return b"".join(chunks)


def build_http_response(status, body, content_type="text/plain; charset=utf-8"):
    return (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode() + body


def extract_body(http_response_bytes):
    parts = http_response_bytes.split(b"\r\n\r\n", 1)
    if len(parts) == 2:
        return parts[1]
    return b""


def main():
    config = load_config()

    app_ip = config["app_server"]["ip"]
    app_port = config["app_server"]["port"]

    origin_ip = config["origin_server"]["ip"]
    origin_port = config["origin_server"]["port"]

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((app_ip, app_port))
    sock.listen()

    print(f"Application Server running on {app_ip}:{app_port}")
    print(f"Fetching files from origin {origin_ip}:{origin_port}")

    while True:
        conn, addr = sock.accept()
        with conn:
            data = conn.recv(4096)
            if not data:
                continue

            request_text = data.decode("utf-8", errors="ignore")
            first_line = request_text.splitlines()[0]

            print(f"\nClient request: {first_line}")

            parts = first_line.split()
            if len(parts) < 2:
                response = build_http_response("400 Bad Request", b"Bad Request")
                conn.sendall(response)
                continue

            path = parts[1]

            # בקשת רשימת קבצים - בלי delay
            if path == "/":
                print("Application handling LIST request")
                origin_response = fetch_file_from_origin(origin_ip, origin_port, "")
                body = extract_body(origin_response)

                response = build_http_response(
                    "200 OK",
                    body,
                    "application/json; charset=utf-8"
                )
                conn.sendall(response)
                continue

            # בקשת קובץ - עם delay
            filename = path.lstrip("/")
            print(f"Application handling file request: {filename}")

            origin_response = fetch_file_from_origin(origin_ip, origin_port, filename)

            if DELAY_ON:
                print(f"### TCP DELAY: sleeping {DELAY_SECONDS} seconds before sending file response ###")
                time.sleep(DELAY_SECONDS)

            conn.sendall(origin_response)


if __name__ == "__main__":
    main()