import socket
import json
import random
from pathlib import Path
from common.protocol import (
    encode_message,
    decode_message,
    DHCP_DISCOVER,
    DNS_QUERY
)

SERVER_TIMEOUT = 6


def load_config():
    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "config" / "config.json"

    with open(config_path, "r") as f:
        return json.load(f)


def generate_mac():
    return "AA:BB:CC:" + ":".join(f"{random.randint(0, 255):02X}" for _ in range(3))


def do_dhcp(config):
    dhcp_ip = config["dhcp_server"]["ip"]
    dhcp_port = config["dhcp_server"]["port"]

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    client_mac = generate_mac()
    print(f"\nGenerated client MAC: {client_mac}")

    discover_message = {
        "type": DHCP_DISCOVER,
        "client_mac": client_mac
    }

    sock.sendto(encode_message(discover_message), (dhcp_ip, dhcp_port))
    print(f"Sent DHCP_DISCOVER to {dhcp_ip}:{dhcp_port}")

    data, _ = sock.recvfrom(1024)
    response = decode_message(data)

    print("\nReceived DHCP response:")
    print(response)

    if "lease_time" in response:
        print(f"Lease time: {response['lease_time']} seconds")

    sock.close()
    return response


def do_dns(dns_ip, dns_port, service_name):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    query_message = {
        "type": DNS_QUERY,
        "name": service_name
    }

    sock.sendto(encode_message(query_message), (dns_ip, dns_port))
    print(f"\nSent DNS_QUERY for '{service_name}' to {dns_ip}:{dns_port}")

    data, _ = sock.recvfrom(1024)
    response = decode_message(data)

    print("\nReceived DNS response:")
    print(response)

    if "ttl" in response:
        print(f"DNS TTL: {response['ttl']} seconds")

    sock.close()
    return response


def send_http_get(server_ip, server_port, host_name, path):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(SERVER_TIMEOUT)

    try:
        sock.connect((server_ip, server_port))

        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host_name}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )

        print(f"\nSending HTTP GET request for {path}")
        sock.sendall(request.encode("utf-8"))

        response_chunks = []
        while True:
            data = sock.recv(4096)
            if not data:
                break
            response_chunks.append(data)

        return b"".join(response_chunks)

    except socket.timeout:
        print("### TCP CLIENT TIMEOUT: server response took too long ###")
        return b""

    finally:
        sock.close()


def parse_http_response(response_bytes):
    header_end = response_bytes.find(b"\r\n\r\n")
    if header_end == -1:
        return None, None

    headers = response_bytes[:header_end].decode("utf-8", errors="ignore")
    body = response_bytes[header_end + 4:]
    return headers, body


def get_available_files(server_ip, server_port, host_name):
    print("\nRequesting available files list...")
    response = send_http_get(server_ip, server_port, host_name, "/")

    headers, body = parse_http_response(response)
    if headers is None:
        print("Invalid HTTP response")
        return []

    print("\nReceived HTTP headers:")
    print(headers)

    body_text = body.decode("utf-8", errors="ignore")
    print("\nAvailable files from server:")
    print(body_text)

    files = []
    for line in body_text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("available files"):
            continue
        files.append(line)

    return files


def choose_file(files):
    if not files:
        return None

    print("\nChoose file to download:")
    for i, file_name in enumerate(files, start=1):
        print(f"{i} - {file_name}")
    print("Or type the exact file name")

    choice = input("\nEnter number or file name [default: test.txt]: ").strip()

    if not choice:
        return "test.txt"

    if choice.isdigit():
        choice_num = int(choice)
        if 1 <= choice_num <= len(files):
            return files[choice_num - 1]
        print("Invalid number")
        return None

    return choice


def download_file(server_ip, server_port, host_name, file_name):
    print(f"\nRequesting file: {file_name}")

    response = send_http_get(server_ip, server_port, host_name, f"/{file_name}")
    headers, body = parse_http_response(response)

    if headers is None:
        print("Invalid HTTP response")
        return

    print("\nReceived HTTP headers:")
    print(headers)

    status_line = headers.splitlines()[0] if headers.splitlines() else ""
    if "200 OK" not in status_line:
        print("\nDownload failed.")
        print("Response body:")
        print(body.decode("utf-8", errors="ignore"))
        return

    output_file = f"downloaded_{file_name}"
    output_path = Path(output_file).resolve()

    Path(output_file).write_bytes(body)

    print(f"\nFile downloaded successfully: {output_path}")


def main():
    config = load_config()

    dhcp_response = do_dhcp(config)
    if "error" in dhcp_response:
        print("DHCP error:", dhcp_response["error"])
        return

    dns_ip = dhcp_response["dns_server"]
    dns_port = config["dns_server"]["port"]
    service_name = "files.local"

    dns_response = do_dns(dns_ip, dns_port, service_name)
    if "error" in dns_response:
        print("DNS error:", dns_response["error"])
        return

    app_ip = dns_response["ip"]
    app_port = dns_response["port"]

    files = get_available_files(app_ip, app_port, service_name)
    if not files:
        print("No files received from server")
        return

    file_name = choose_file(files)
    if not file_name:
        return

    download_file(app_ip, app_port, service_name, file_name)


if __name__ == "__main__":
    main()