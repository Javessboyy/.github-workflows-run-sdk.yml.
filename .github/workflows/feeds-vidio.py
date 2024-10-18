import hashlib
import hmac
import json
import time
from datetime import datetime
from http.client import HTTPSConnection
import csv
import gspread
from google.oauth2.service_account import Credentials

# Fungsi untuk menandatangani permintaan
def sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

# Kredensial API Tencent Cloud
SECRET_ID = "IKIDIvqurmrsplcZQDwY6e9d2Ql1BSky9JTd"
SECRET_KEY = "GTaflporpkbdins5V6eI6206Mi9gSPNI"

# Pengaturan permintaan
SERVICE = "vod"
HOST = "vod.tencentcloudapi.com"
VERSION = "2018-07-17"
ACTION_SEARCH = "SearchMedia"
ACTION_STAT = "DescribeMediaPlayStatDetails"

def create_authorization(action: str, payload: str) -> str:
    timestamp = int(time.time())
    date = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
    canonical_uri = "/"
    canonical_querystring = ""
    ct = "application/json; charset=utf-8"
    canonical_headers = f"content-type:{ct}\nhost:{HOST}\nx-tc-action:{action.lower()}\n"
    signed_headers = "content-type;host;x-tc-action"
    hashed_request_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = (f"POST\n{canonical_uri}\n{canonical_querystring}\n" +
                         f"{canonical_headers}\n{signed_headers}\n{hashed_request_payload}")

    credential_scope = f"{date}/{SERVICE}/tc3_request"
    hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = (f"TC3-HMAC-SHA256\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}")

    secret_date = sign(("TC3" + SECRET_KEY).encode("utf-8"), date)
    secret_service = sign(secret_date, SERVICE)
    secret_signing = sign(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (f"TC3-HMAC-SHA256 Credential={SECRET_ID}/{credential_scope}, " +
                     f"SignedHeaders={signed_headers}, Signature={signature}")
    return authorization

def search_media() -> list:
    payload = json.dumps({
        "Limit": 100,
        "Offset": 0
    })
    
    action = ACTION_SEARCH
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-TC-Action": action,
        "X-TC-Timestamp": str(int(time.time())),
        "X-TC-Version": VERSION,
        "Authorization": create_authorization(action, payload)
    }

    conn = HTTPSConnection(HOST)
    conn.request("POST", "/", payload, headers)
    response = conn.getresponse()
    data = response.read().decode()
    conn.close()
    
    result = json.loads(data)
    
    file_ids = []
    if 'Response' in result and 'MediaInfoSet' in result['Response']:
        for media in result['Response']['MediaInfoSet']:
            file_ids.append(media['FileId'])
    else:
        print("Tidak ada media ditemukan.")
    
    return file_ids

def fetch_media_statistics(file_id: str) -> dict:
    start_time = "2024-10-01T00:00:00Z"
    end_time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = json.dumps({
        "FileId": file_id,
        "StartTime": start_time,
        "EndTime": end_time
    })
    
    action = ACTION_STAT
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-TC-Action": action,
        "X-TC-Timestamp": str(int(time.time())),
        "X-TC-Version": VERSION,
        "Authorization": create_authorization(action, payload)
    }
    
    conn = HTTPSConnection(HOST)
    conn.request("POST", "/", payload, headers)
    response = conn.getresponse()
    data = response.read().decode()
    conn.close()
    
    result = json.loads(data)
    return result

def fetch_all_statistics() -> list:
    file_ids = search_media()
    all_statistics = []

    for file_id in file_ids:
        statistics = fetch_media_statistics(file_id)
        all_statistics.append(statistics)

    return all_statistics

def save_statistics_to_csv(all_statistics: list, file_name: str = "media_statistics.csv") -> None:
    with open(file_name, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['FileId', 'PlayTimes', 'Time', 'Traffic']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()

        for result in all_statistics:
            if 'Response' in result and 'PlayStatInfoSet' in result['Response']:
                for stat in result['Response']['PlayStatInfoSet']:
                    writer.writerow({
                        'FileId': stat['FileId'],
                        'PlayTimes': stat['PlayTimes'],
                        'Time': stat['Time'],
                        'Traffic': stat['Traffic']
                    })
            else:
                writer.writerow({'FileId': 'Tidak ada statistik tersedia', 'PlayTimes': '', 'Time': '', 'Traffic': ''})

def connect_to_google_sheets(spreadsheet_url: str):
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file("Credential.json", scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(spreadsheet_url).sheet1
    return sheet

def save_statistics_to_google_sheets(all_statistics, sheet):
    header = ['FileId', 'PlayTimes', 'Time', 'Traffic']
    sheet.clear()
    sheet.append_row(header)

    rows = []
    for result in all_statistics:
        if 'Response' in result and 'PlayStatInfoSet' in result['Response']:
            for stat in result['Response']['PlayStatInfoSet']:
                row = [stat['FileId'], stat['PlayTimes'], stat['Time'], stat['Traffic']]
                rows.append(row)
        else:
            rows.append(['Tidak ada statistik tersedia', '', '', ''])

    sheet.append_rows(rows)

def main_task():
    spreadsheet_url = "https://docs.google.com/spreadsheets/d/1CdwAK6-8r1xxgrfx-fzKoECo2uc2rIuJAaK3C1LsWKI/edit?usp=sharing"
    sheet = connect_to_google_sheets(spreadsheet_url)
    all_statistics = fetch_all_statistics()
    save_statistics_to_google_sheets(all_statistics, sheet)
    save_statistics_to_csv(all_statistics)  # Simpan ke CSV
    print("Statistik disimpan ke dalam Google Sheets.")

if __name__ == "__main__":
    main_task()
    
