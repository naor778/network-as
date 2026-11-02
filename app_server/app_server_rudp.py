import socket
import json
import time
from pathlib import Path

SERVER_IP = "127.0.0.1"
SERVER_PORT = 9090
TIMEOUT = 2
CHUNK_SIZE = 256
MAX_RWND = 4
## הוספנו פה אופציות לאיבוד חבילות והשהיות
DROP_ONCE = False
DELAY_ON = False
DELAY_SECONDS = 6
DROP_SEQ = 1

def load_config():
    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "config" / "config.json"
    with open(config_path, "r") as f:
        return json.load(f)
   ##  פונקציה לדמות איבוד חבילות  והשהיות
def maybe_send(sock, data, addr, seq=None):
    global DROP_ONCE

    if DROP_ONCE and seq == DROP_SEQ:
        print(f"### SIMULATED LOSS: dropped packet seq={seq} ###")
        DROP_ONCE = False
        return

    if DELAY_ON:
        print(f"### SIMULATED DELAY: sleeping {DELAY_SECONDS} seconds ###")
        import time
        time.sleep(DELAY_SECONDS)

    sock.sendto(data, addr)

def fetch_http_body_from_origin(origin_ip, origin_port, path):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((origin_ip, origin_port))

    request = (
        f"GET {path} HTTP/1.1\r\n"
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
    response = b"".join(chunks)

    header_end = response.find(b"\r\n\r\n")
    if header_end == -1:
        return None, "Invalid HTTP response from origin"

    headers = response[:header_end].decode("utf-8", errors="ignore")
    body = response[header_end + 4:]

    status_line = headers.splitlines()[0] if headers.splitlines() else ""
    if "200 OK" not in status_line:
        return None, "Origin server failed to provide requested resource"

    return body.decode("utf-8", errors="ignore"), None


def fetch_file_from_origin(origin_ip, origin_port, file_name):
    return fetch_http_body_from_origin(origin_ip, origin_port, f"/{file_name}")


def fetch_file_list_from_origin(origin_ip, origin_port):
    body, error = fetch_http_body_from_origin(origin_ip, origin_port, "/")
    if error:
        return None, error

    lines = body.splitlines()
    files = []

    for line in lines:
        line = line.strip()
        if not line or line.lower().startswith("available files"):
            continue
        files.append(line)

    return files, None


def send_file_rudp(sock, client_addr, content, rwnd):
    chunks = [content[i:i + CHUNK_SIZE] for i in range(0, len(content), CHUNK_SIZE)]

    if not chunks:
        chunks = [""]

    base = 0
    next_seq = 0
    acked = set()
    total_packets = len(chunks)

    cwnd = 1
    ssthresh = 4
    sock.settimeout(TIMEOUT)

    while base < total_packets:
        effective_window = min(cwnd, rwnd)

        while next_seq < base + effective_window and next_seq < total_packets:
            packet = {
                "type": "DATA",
                "seq": next_seq,
                "data": chunks[next_seq],
                "cwnd": cwnd,
                "rwnd": rwnd
            }
            maybe_send(sock, json.dumps(packet).encode(), client_addr, seq=next_seq)
            print(f"Sent DATA seq={next_seq} | cwnd={cwnd} rwnd={rwnd}")
            next_seq += 1

        try:
            while True:
                try:
                    ## הוספנו פה שורה נוספת  כדי שהשרת לא יקרוס
                    ack_data, addr = sock.recvfrom(4096)
                except ConnectionResetError:
                    print("### Client disconnected after timeout / retransmission ###")
                    return
                if addr != client_addr:
                    continue

                ack = json.loads(ack_data.decode())
                if ack.get("type") != "ACK":
                    continue

                ack_seq = ack.get("seq")
                print(f"Received ACK seq={ack_seq}")

                if ack_seq is not None:
                    acked.add(ack_seq)

                while base in acked:
                    base += 1

                if cwnd < ssthresh:
                    cwnd *= 2
                else:
                    cwnd += 1

                if base == next_seq:
                    break

                effective_window = min(cwnd, rwnd)

                while next_seq < base + effective_window and next_seq < total_packets:
                    packet = {
                        "type": "DATA",
                        "seq": next_seq,
                        "data": chunks[next_seq],
                        "cwnd": cwnd,
                        "rwnd": rwnd
                    }
                    maybe_send(sock, json.dumps(packet).encode(), client_addr, seq=next_seq)

                    print(f"Sent DATA seq={next_seq} | cwnd={cwnd} rwnd={rwnd}")
                    next_seq += 1

        except socket.timeout:
            print("Timeout detected -> congestion assumed")
            ssthresh = max(1, cwnd // 2)
            cwnd = 1
            next_seq = base
            print(f"cwnd reset to {cwnd}, retransmitting from seq={base}")

    end_packet = {"type": "END"}

    while True:
        sock.sendto(json.dumps(end_packet).encode(), client_addr)
        print("Sent END")
        try:
            ack_data, addr = sock.recvfrom(4096)
            if addr != client_addr:
                continue

            ack = json.loads(ack_data.decode())
            if ack.get("type") == "ACK_END":
                print("Received ACK_END")
                break
        except socket.timeout:
            print("Timeout waiting for ACK_END, retransmitting END")

    sock.settimeout(None)


def main():
    config = load_config()
    origin_ip = config["origin_server"]["ip"]
    origin_port = config["origin_server"]["port"]

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((SERVER_IP, SERVER_PORT))

    print(f"RUDP Application Server listening on {SERVER_IP}:{SERVER_PORT}")
    print(f"Using origin server at {origin_ip}:{origin_port}")

    while True:
        data, client_addr = sock.recvfrom(4096)

        try:
            message = json.loads(data.decode())
        except json.JSONDecodeError:
            continue

        msg_type = message.get("type")

        if msg_type == "LIST":
            print(f"\nApplication received LIST request from {client_addr}")

            files, error = fetch_file_list_from_origin(origin_ip, origin_port)
            if error:
                error_msg = {
                    "type": "ERROR",
                    "error": error
                }
                sock.sendto(json.dumps(error_msg).encode(), client_addr)
                continue

            response = {
                "type": "LIST_RESPONSE",
                "files": files
            }
            sock.sendto(json.dumps(response).encode(), client_addr)
            print(f"Sent LIST_RESPONSE with {len(files)} files")
            continue

        if msg_type != "DOWNLOAD":
            continue

        file_name = message.get("filename")
        rwnd = int(message.get("rwnd", MAX_RWND))

        print(f"\nApplication received DOWNLOAD request: {file_name}")

        content, error = fetch_file_from_origin(origin_ip, origin_port, file_name)
        if error:
            error_msg = {
                "type": "ERROR",
                "error": error
            }
            sock.sendto(json.dumps(error_msg).encode(), client_addr)
            continue

        send_file_rudp(sock, client_addr, content, rwnd)


if __name__ == "__main__":
    main()