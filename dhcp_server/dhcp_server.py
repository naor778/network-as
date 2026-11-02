import socket
import json
import random
import datetime
import time
from pathlib import Path
from common.protocol import encode_message, decode_message, DHCP_DISCOVER, DHCP_OFFER


# מילון גלובלי ששומר את מצב ההקצאות הנוכחי.
# לכל כתובת MAC נשמר:
# - ה-IP שהוקצה
# - זמן תחילת ה-lease
# - זמן סיום ה-lease
# המבנה הוא:
# MAC -> {"ip": ..., "lease_start": ..., "lease_end": ...}
allocated_ips = {}


# פונקציית עזר להדפסת הודעות לוג עם שעה.
# המטרה היא שיהיה קל לעקוב אחרי מה שהשרת עושה בזמן ריצה:
# מתי קיבל בקשה, מתי שלח תשובה, ומתי lease פג.
def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")


# הפונקציה טוענת את קובץ ההגדרות config.json מתוך תיקיית הפרויקט.
# בצורה הזאת כל ההגדרות של השרת מרוכזות במקום אחד:
# כתובת השרת, פורט, pool של כתובות, gateway, DNS וכו'.
def load_config():
    # parent.parent מחזיר אותנו מתיקיית dhcp_server אל תיקיית הפרויקט הראשית
    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "config" / "config.json"

    # פתיחת קובץ ההגדרות והמרתו מ-JSON למילון Python
    with open(config_path, "r") as f:
        return json.load(f)


# הפונקציה בודקת האם יש leases שפג תוקפם, ואם כן מוחקת אותם.
# כך אפשר לשחרר כתובות IP ישנות ולהחזיר אותן ל-pool.
# זה מדמה התנהגות בסיסית של שרת DHCP אמיתי.
def cleanup_expired_leases():
    # הזמן הנוכחי בשניות מאז epoch
    now = time.time()

    # נשמור כאן את כל ה-MAC-ים שצריך למחוק אחרי הסריקה
    expired_macs = []

    # מעבר על כל הלקוחות שיש להם כרגע lease
    for mac, lease_info in allocated_ips.items():
        # אם זמן הסיום קטן או שווה לזמן הנוכחי -> ה-lease פג
        if lease_info["lease_end"] <= now:
            expired_macs.append(mac)

    # מוחקים בפועל רק אחרי שסיימנו לעבור על המילון,
    # כדי לא לשנות מילון תוך כדי איטרציה עליו
    for mac in expired_macs:
        expired_ip = allocated_ips[mac]["ip"]
        del allocated_ips[mac]
        log(f"Lease expired for MAC {mac}, released IP {expired_ip}")


# הפונקציה אחראית לקבוע איזה IP להחזיר ללקוח מסוים.
# הלוגיקה היא:
# 1. קודם מנקים leases שפגו
# 2. אם ללקוח כבר יש lease תקף -> מחזירים את אותו IP
# 3. אם אין לו lease -> מחפשים IP פנוי מתוך ה-pool
# 4. אם אין כתובות פנויות -> מחזירים None
def get_assigned_ip(config, client_mac):
    # זמן ה-lease מוגדר בקובץ ההגדרות
    lease_time = config["dhcp_server"]["lease_time"]

    # כל הכתובות האפשריות לחלוקה
    ip_pool = config["network_config"]["ip_pool"]

    # הזמן הנוכחי
    now = time.time()

    # לפני שמחפשים כתובת פנויה, מנקים leases ישנים שפגו
    cleanup_expired_leases()

    # אם כבר יש ללקוח lease תקף, מחזירים לו את אותו IP
    # ולא מקצים לו כתובת חדשה.
    if client_mac in allocated_ips:
        lease_info = allocated_ips[client_mac]

        # מחזירים גם את הזמן שנותר ל-lease בשניות
        return lease_info["ip"], int(lease_info["lease_end"] - now)

    # אוספים את כל הכתובות שכבר נמצאות בשימוש כרגע
    used_ips = {lease_info["ip"] for lease_info in allocated_ips.values()}

    # בונים רשימה חדשה של כתובות שעדיין פנויות
    free_ips = [ip for ip in ip_pool if ip not in used_ips]

    # אם אין כתובות פנויות בכלל -> אין מה להקצות
    if not free_ips:
        return None, None

    # בוחרים כתובת פנויה אקראית מתוך ה-pool
    assigned_ip = random.choice(free_ips)

    # שומרים את ההקצאה במילון הגלובלי
    allocated_ips[client_mac] = {
        "ip": assigned_ip,
        "lease_start": now,
        "lease_end": now + lease_time
    }

    # מחזירים את ה-IP החדש ואת זמן ה-lease
    return assigned_ip, lease_time


# הפונקציה הראשית של שרת ה-DHCP.
# כאן השרת:
# - טוען את ההגדרות
# - פותח socket מסוג UDP
# - מאזין לבקשות מהלקוח
# - ואם מגיעה בקשת DHCP_DISCOVER, הוא מחזיר DHCP_OFFER
def main():
    # טעינת כל ההגדרות מתוך config.json
    config = load_config()

    # כתובת ופורט שעליהם שרת ה-DHCP יאזין
    server_ip = config["dhcp_server"]["ip"]
    server_port = config["dhcp_server"]["port"]

    # יצירת socket מסוג UDP
    # DHCP עובד אצלנו מעל UDP, לכן משתמשים ב-SOCK_DGRAM
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # קישור הסוקט לכתובת ולפורט של השרת
    sock.bind((server_ip, server_port))

    log(f"DHCP Server listening on {server_ip}:{server_port}")

    # השרת עובד בלולאה אינסופית ומחכה כל הזמן לבקשות חדשות
    while True:
        # recvfrom מחזיר גם את תוכן ההודעה וגם את כתובת הלקוח ששלח אותה
        data, client_address = sock.recvfrom(1024)

        # פענוח ההודעה מפורמט bytes למילון Python
        message = decode_message(data)

        log(f"Received from {client_address}: {message}")

        # בודקים האם זו בקשת DHCP_DISCOVER
        if message.get("type") == DHCP_DISCOVER:
            # מוציאים את כתובת ה-MAC שהלקוח שלח
            client_mac = message.get("client_mac")

            # מבקשים מהפונקציה להחזיר IP מתאים ללקוח הזה
            assigned_ip, lease_time = get_assigned_ip(config, client_mac)

            # אם לא נשארו כתובות פנויות, מחזירים שגיאה
            if assigned_ip is None:
                response = {
                    "type": DHCP_OFFER,
                    "error": "No available IP addresses"
                }
            else:
                # אם נמצא IP פנוי, בונים תשובת DHCP_OFFER מלאה
                response = {
                    "type": DHCP_OFFER,
                    "client_ip": assigned_ip,
                    "subnet_mask": config["network_config"]["subnet_mask"],
                    "gateway": config["network_config"]["gateway"],
                    "dns_server": config["network_config"]["dns_ip"],
                    "lease_time": lease_time
                }

            # קידוד התשובה ל-bytes ושליחה חזרה ללקוח
            sock.sendto(encode_message(response), client_address)

            log(f"Sent DHCP_OFFER to {client_address}: {response}")
            log(f"Current leases: {allocated_ips}")


# נקודת הכניסה של הקובץ.
# אם מריצים את הקובץ ישירות, תופעל הפונקציה הראשית main().
if __name__ == "__main__":
    main()