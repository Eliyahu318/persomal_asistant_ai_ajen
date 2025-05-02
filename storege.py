import os
import json
from config import settings

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_LOG_DELETED_TASKS_NAME = str(settings.data_dir / settings.log_lead_template)  # os.path.join(BASE_DIR, "data", "deleted_tasks_{name}.jsonl")
FILE_LOG_DELETED_MESSAGES = str(settings.data_dir / settings.log_chat_template)  # os.path.join(BASE_DIR, "data", "deleted_messages_{name}.jsonl")


def ensure_file_exists(file_path: str):
    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)


def save_json_file(path: str, data: any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data


def append_jsonl_file(path: str, entry: dict):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def log_deleted_task(name: str, task: dict):
    path = FILE_LOG_DELETED_TASKS_NAME.format(name=name)
    ensure_file_exists(file_path=path)
    append_jsonl_file(path=path, entry=task)


def log_deleted_message(name: str, entry: dict):
    path = FILE_LOG_DELETED_MESSAGES.format(name=name)
    ensure_file_exists(file_path=path)
    save_json_file(path=path, data=entry)


def read_jsonl_file(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
