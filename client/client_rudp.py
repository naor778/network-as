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
MAX_TIMEOUT_RETRIES = 3
SERVER_TIMEOUT = 2
CLIENT_RWND = 4


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


def request_file_list(server_ip, server_port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(SERVER_TIMEOUT)

    request = {
        "type": "LIST"
    }

    sock.sendto(json.dumps(request).encode(), (server_ip, server_port))
    print(f"\nSent LIST request to {server_ip}:{server_port}")

    try:
        data, _ = sock.recvfrom(4096)
        message = json.loads(data.decode())

        if message.get("type") == "ERROR":
            print("Server error:", message.get("error"))
            sock.close()
            return []

        if message.get("type") != "LIST_RESPONSE":
            print("Unexpected response from server")
            sock.close()
            return []

        files = message.get("files", [])
        sock.close()
        return files

    except socket.timeout:
        print("Timeout while waiting for file list")
        sock.close()
        return []


def choose_file(files):
    print("\nAvailable files from application server:")
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


def request_file_rudp(server_ip, server_port, filename):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(SERVER_TIMEOUT)
    timeout_retries = 0    ## נוסף
    request = {
        "type": "DOWNLOAD",
        "filename": filename,
        "rwnd": CLIENT_RWND
    }

    sock.sendto(json.dumps(request).encode(), (server_ip, server_port))
    print(f"\nSent RUDP DOWNLOAD request for: {filename} to {server_ip}:{server_port}")

    received_chunks = {}
    finished = False

    while not finished:
        try:
            data, addr = sock.recvfrom(4096)
            message = json.loads(data.decode())

            msg_type = message.get("type")

            if msg_type == "DATA":
                seq = message["seq"]
                chunk = message["data"]

                cwnd = message.get("cwnd")
                rwnd = message.get("rwnd")

                print(f"Received DATA seq={seq} | sender cwnd={cwnd} client rwnd={rwnd}")

                if seq not in received_chunks:
                    received_chunks[seq] = chunk

                ack = {
                    "type": "ACK",
                    "seq": seq
                }

                sock.sendto(json.dumps(ack).encode(), addr)
                print(f"Sent ACK seq={seq}")

            elif msg_type == "END":
                print("Received END")

                ack = {
                    "type": "ACK_END"
                }
                sock.sendto(json.dumps(ack).encode(), addr)
                finished = True

            elif msg_type == "ERROR":
                print("Server error:", message.get("error"))
                sock.close()
                return

##  נוסף מחדש פה שינינו
        except socket.timeout:

            timeout_retries += 1

            print(f"Timeout while waiting for server response ({timeout_retries}/{MAX_TIMEOUT_RETRIES})")

            if timeout_retries >= MAX_TIMEOUT_RETRIES:
                print("Too many timeouts, stopping download")

                sock.close()

                return

            continue

    ordered_data = ""
    for seq in sorted(received_chunks.keys()):
        ordered_data += received_chunks[seq]

    output_file = f"downloaded_rudp_{filename}"
    output_path = Path(output_file).resolve()

    Path(output_file).write_text(ordered_data, encoding="utf-8")

    print(f"\nRUDP file downloaded successfully: {output_path}")
    sock.close()


def main():
    config = load_config()

    dhcp_response = do_dhcp(config)
    if "error" in dhcp_response:
        print("DHCP error:", dhcp_response["error"])
        return

    dns_ip = dhcp_response["dns_server"]
    dns_port = config["dns_server"]["port"]
    service_name = "files-rudp.local"

    dns_response = do_dns(dns_ip, dns_port, service_name)
    if "error" in dns_response:
        print("DNS error:", dns_response["error"])
        return

    server_ip = dns_response["ip"]
    server_port = dns_response["port"]

    files = request_file_list(server_ip, server_port)
    if not files:
        print("No files received from server")
        return

    filename = choose_file(files)
    if not filename:
        return

    request_file_rudp(server_ip, server_port, filename)


if __name__ == "__main__":
    main()