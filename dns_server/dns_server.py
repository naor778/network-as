import socket
import json
import datetime
from pathlib import Path
from common.protocol import encode_message, decode_message, DNS_QUERY, DNS_RESPONSE


# פונקציית עזר להדפסת הודעות לוג עם שעה.
# עוזרת לעקוב אחרי פעולות השרת בזמן ריצה (בקשות, תגובות וכו').
def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")


# הפונקציה טוענת את קובץ ההגדרות config.json.
# הקובץ כולל:
# - כתובת ופורט של שרת DNS
# - זמן TTL
# - טבלת שירותים (שם -> IP + port)
def load_config():
    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "config" / "config.json"

    with open(config_path, "r") as f:
        return json.load(f)


# הפונקציה הראשית של שרת ה-DNS.
# תפקידה:
# - להאזין לבקשות DNS מהלקוח
# - לתרגם שם שירות ל-IP ו-port
# - להחזיר תשובה ללקוח
def main():
    # טעינת ההגדרות מתוך config.json
    config = load_config()

    # כתובת ופורט שעליהם השרת יאזין
    server_ip = config["dns_server"]["ip"]
    server_port = config["dns_server"]["port"]

    # זמן חיים של תשובת DNS (TTL)
    ttl = config["dns_server"]["ttl"]

    # יצירת socket מסוג UDP (DNS עובד מעל UDP)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # קישור הסוקט לכתובת ולפורט
    sock.bind((server_ip, server_port))

    log(f"DNS Server listening on {server_ip}:{server_port}")

    # לולאה אינסופית שממתינה לבקשות מהלקוח
    while True:
        # קבלת הודעה מהלקוח + כתובת השולח
        data, client_address = sock.recvfrom(1024)

        # פענוח ההודעה (bytes -> dict)
        message = decode_message(data)

        log(f"Received from {client_address}: {message}")

        # בודקים אם מדובר בבקשת DNS_QUERY
        if message.get("type") == DNS_QUERY:
            # שם השירות שהלקוח מבקש (למשל files.local)
            service_name = message.get("name")

            # בדיקה האם השירות קיים בטבלת השירותים
            if service_name in config["services"]:
                service_info = config["services"][service_name]

                # בניית תשובת DNS תקינה
                response = {
                    "type": DNS_RESPONSE,
                    "name": service_name,
                    "ip": service_info["ip"],
                    "port": service_info["port"],
                    "ttl": ttl
                }

                log(f"Resolved service '{service_name}' to {service_info['ip']}:{service_info['port']}")

            else:
                # אם השירות לא קיים, מחזירים שגיאה
                response = {
                    "type": DNS_RESPONSE,
                    "name": service_name,
                    "error": "Service not found",
                    "ttl": 0
                }

                log(f"Service '{service_name}' not found")

            # שליחת התשובה ללקוח
            sock.sendto(encode_message(response), client_address)

            log(f"Sent DNS_RESPONSE to {client_address}: {response}")


# נקודת כניסה לקובץ
# אם הקובץ מורץ ישירות -> תופעל הפונקציה main
if __name__ == "__main__":
    main()