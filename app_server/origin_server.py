import socket
import json
from pathlib import Path


def load_config():
    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "config" / "config.json"
    with open(config_path, "r") as f:
        return json.load(f)


def get_content_type(file_name):
    if file_name.endswith(".html"):
        return "text/html; charset=utf-8"
    if file_name.endswith(".txt"):
        return "text/plain; charset=utf-8"
    return "application/octet-stream"


def build_http_response(status_code, status_text, body_bytes, content_type):
    headers = (
        f"HTTP/1.1 {status_code} {status_text}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode("utf-8")
    return headers + body_bytes


def handle_request(request_text):
    lines = request_text.splitlines()
    if not lines:
        return build_http_response(400, "Bad Request", b"Bad Request", "text/plain; charset=utf-8")

    parts = lines[0].split()
    if len(parts) < 3:
        return build_http_response(400, "Bad Request", b"Bad Request", "text/plain; charset=utf-8")

    method, path, _ = parts
    if method != "GET":
        return build_http_response(405, "Method Not Allowed", b"Method Not Allowed", "text/plain; charset=utf-8")

    files_dir = Path(__file__).resolve().parent / "files"

    if path == "/":
        file_list = [p.name for p in files_dir.iterdir() if p.is_file()] if files_dir.exists() else []
        body = ("Available files:\n" + "\n".join(file_list)).encode("utf-8")
        return build_http_response(200, "OK", body, "text/plain; charset=utf-8")

    file_name = path.lstrip("/")
    file_path = files_dir / file_name

    if not file_path.exists() or not file_path.is_file():
        return build_http_response(404, "Not Found", b"File not found", "text/plain; charset=utf-8")

    body = file_path.read_bytes()
    return build_http_response(200, "OK", body, get_content_type(file_name))


def main():
    config = load_config()
    server_ip = config["origin_server"]["ip"]
    server_port = config["origin_server"]["port"]

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((server_ip, server_port))
    sock.listen()

    print(f"Origin Server listening on {server_ip}:{server_port}")

    while True:
        conn, addr = sock.accept()
        with conn:
            data = conn.recv(4096)
            if not data:
                continue

            request_text = data.decode("utf-8", errors="ignore")
            response = handle_request(request_text)
            conn.sendall(response)


if __name__ == "__main__":
    main()