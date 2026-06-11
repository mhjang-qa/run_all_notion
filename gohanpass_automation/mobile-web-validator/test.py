import os

import requests
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DB_ID")

if not NOTION_TOKEN or not DATABASE_ID:
    raise RuntimeError(f"NOTION_TOKEN / NOTION_DB_ID 값을 {ROOT_DIR / '.env'}에 설정하세요.")

url = "https://api.notion.com/v1/pages"

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

today = datetime.now().strftime("%Y-%m-%d")

payload = {
    "parent": {"database_id": DATABASE_ID},
    "properties": {
        "제목": {
            "title": [
                {
                    "text": {
                        "content": f"자동리포트_{today}"
                    }
                }
            ]
        },
        "버전": {
            "rich_text": [
                {
                    "text": {
                        "content": "1.0.0"
                    }
                }
            ]
        },
        "플랫폼": {
            "select": {
                "name": "WEB_CHROME"
            }
        },
        "날짜": {
            "date": {
                "start": today
            }
        },
        "PASS": {
            "number": 10
        },
        "FAIL": {
            "number": 2
        },
        "NA": {
            "number": 1
        },
        "TOTAL": {
            "number": 13
        },
        "상태": {
            "status": {
                "name": "Blocked"
            }
        },
        "결과": {
            "rich_text": [
                {
                    "text": {
                        "content": "테스트 실패 발생"
                    }
                }
            ]
        }
    }
}

res = requests.post(url, headers=headers, json=payload, timeout=20)

print("status_code:", res.status_code)
print("response:", res.text)
