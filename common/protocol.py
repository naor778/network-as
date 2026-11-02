import json


# ==========================================================
# קובץ זה מגדיר את "שפת התקשורת" בין כל הרכיבים במערכת:
# - לקוח
# - DHCP Server
# - DNS Server
# - Application Server
#
# התפקיד שלו:
# 1. להגדיר איך מקודדים הודעה (לפני שליחה)
# 2. להגדיר איך מפענחים הודעה (אחרי קבלה)
# 3. להגדיר סוגי הודעות קבועים כדי לשמור על אחידות
# ==========================================================


# ===== Serialization (קידוד ופענוח הודעות) =====

# הפונקציה מקבלת מילון (dict) בפייתון
# וממירה אותו ל-bytes כדי שנוכל לשלוח אותו דרך socket
#
# למה צריך את זה?
# כי socket יודע לשלוח רק bytes ולא אובייקטים של Python
def encode_message(data: dict) -> bytes:
    # json.dumps -> ממיר dict למחרוזת JSON
    # encode -> ממיר מחרוזת ל-bytes
    return json.dumps(data).encode()


# הפונקציה מקבלת bytes שהתקבלו מה־socket
# וממירה אותם חזרה למילון Python
#
# למה צריך את זה?
# כי הנתונים מגיעים כ-bytes, ואנחנו רוצים לעבוד איתם כ-dict
def decode_message(data: bytes) -> dict:
    # decode -> ממיר bytes למחרוזת
    # json.loads -> ממיר JSON למילון Python
    return json.loads(data.decode())


# ===== Message Types (סוגי הודעות במערכת) =====

# במקום להשתמש במחרוזות "קשיחות" בכל הקוד,
# אנחנו מגדירים קבועים (constants)
#
# למה זה טוב?
# - מונע טעויות כתיב
# - שומר על אחידות
# - הופך את הקוד ליותר ברור


# ===== DHCP =====

# הודעה שהלקוח שולח כדי לבקש כתובת IP
DHCP_DISCOVER = "DHCP_DISCOVER"

# תשובה של שרת DHCP עם פרטי ההקצאה
DHCP_OFFER = "DHCP_OFFER"


# ===== DNS =====

# בקשה מהלקוח לתרגם שם שירות ל-IP
DNS_QUERY = "DNS_QUERY"

# תשובה משרת DNS עם IP + port
DNS_RESPONSE = "DNS_RESPONSE"


# ===== Application Layer =====

# הודעת בקשה כללית לשרת האפליקציה
# (לא חובה בשימוש בכל חלקי הפרויקט, אבל נשאר כבסיס להרחבה)
APP_REQUEST = "APP_REQUEST"

# תשובת השרת ללקוח
APP_RESPONSE = "APP_RESPONSE"