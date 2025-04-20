import os
import json
import pytest
from assistant import PersonalAssistant, BASE_DIR
from unittest.mock import patch
from types import SimpleNamespace
from gpt_client import ask_gpt


def test_dispatch_command_shmor():
    assistant = PersonalAssistant.load_state(name="test", confirm_callback=lambda msg: "כן")
    result = assistant.dispatch_command("שמור")
    assert result == assistant.handle_save_question


def test_handle_save_question_mocked():
    assistant = PersonalAssistant.load_state(name="test2", confirm_callback=lambda msg: "כן")

    fake_gpt_output = [{
        "description": "פגישה חשובה",
        "time": "15/04/2025 09:00"
    }]

    with patch.object(PersonalAssistant, "parse_save_question_with_gpt", return_value=fake_gpt_output):
        result = assistant.handle_save_question("יש לי פגישה מחר ב9")
        assert "נשמרו בהצלחה" in result
        assert len(assistant.todo_list) == 1
        assert assistant.todo_list[0]["description"] == "פגישה חשובה"


def test_handle_delete_task_question_mocked():
    assistant = PersonalAssistant.load_state(name="test2", confirm_callback=lambda msg: "כן")
    assistant.todo_list = [{"description": "פגישה חשובה", "time": "10/10/2025 09:00"}]
    fake_gpt_output = {
        "index": 0,
        "description": "פגישה חשובה"
    }

    with patch.object(PersonalAssistant, "parse_delete_task_question_with_gpt", return_value=fake_gpt_output):
        result = assistant.handle_delete_task_with_gpt("תמחק את הםגישה מחר")  # "אין לי פגישה מחר" -> הוא לא מבין

        assert len(assistant.todo_list) == 0
        assert "נמחקה" in result


def test_parse_question_intent_mocked():
    assistant = PersonalAssistant.load_state(name="test_intent", confirm_callback=lambda msg: "כן")

    # נזייף את התגובה מ-GPT כאילו היא מחזירה את intent "שמור"
    fake_gpt_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="שמור"))]
    )

    with patch("gpt_client.ask_gpt", return_value=fake_gpt_response):
        intent = assistant.parse_question_intent_with_gpt("יש לי פגישה מחר ב־2")
        assert intent == "שמור"


# =========== GPT TEST'S ==============


# === CONFIG ===
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TEST_NAME = "test_user"
TEST_FILE_TASKS = os.path.join(BASE_DIR, "data", f"todo_list_{TEST_NAME}.json")
TEST_FILE_MESSAGES = os.path.join(BASE_DIR, "data", f"chat_log_{TEST_NAME}.json")


@pytest.fixture(autouse=True)
def clean_test_files():
    os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
    yield
    for file in [TEST_FILE_TASKS, TEST_FILE_MESSAGES]:
        if os.path.exists(file):
            os.remove(file)


# === DISPATCH ===
def test_dispatch_command():
    pa = PersonalAssistant.load_state(TEST_NAME, confirm_callback=lambda msg: "כן")
    assert pa.dispatch_command("שמור") == pa.handle_save_question
    assert pa.dispatch_command("מחק משימה") == pa.handle_delete_task_with_gpt
    assert pa.dispatch_command("הצג משימות") == pa.handle_show_tasks_question
    assert pa.dispatch_command("מחק כל המשימות") == pa.handle_clear_tasks_question
    assert pa.dispatch_command("איפוס") == pa.handle_reset_question
    assert pa.dispatch_command("משהו אחר") is None


# === INTENT PARSING ===
def test_parse_question_intent_with_gpt():
    pa = PersonalAssistant.load_state(TEST_NAME, confirm_callback=lambda msg: "כן")
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="שמור"))]
    )
    with patch("gpt_client.ask_gpt", return_value=fake_response):
        result = pa.parse_question_intent_with_gpt("יש לי פגישה מחר")
        assert result == "שמור"


# === SAVE TASK ===
def test_handle_save_question():
    pa = PersonalAssistant.load_state(TEST_NAME, confirm_callback=lambda msg: "כן")
    pa.todo_list = []
    mock_tasks = [{"description": "פגישה חשובה", "time": "15/04/2025 09:00"}]
    with patch.object(PersonalAssistant, 'parse_save_question_with_gpt', return_value=mock_tasks):
        response = pa.handle_save_question("יש לי פגישה מחר ב־9")
        assert "נשמרו בהצלחה" in response
        assert len(pa.todo_list) == 1
        assert pa.todo_list[0]["description"] == "פגישה חשובה"


# === SHOW TASKS ===
def test_handle_show_tasks():
    pa = PersonalAssistant.load_state(TEST_NAME, confirm_callback=lambda msg: "כן")
    pa.todo_list = [
        {"description": "לשלם חשבון", "time": "15/04/2025 10:00"},
        {"description": "פגישה", "time": None}
    ]
    response = pa.handle_show_tasks_question()
    assert "1. לשלם חשבון (15/04/2025 10:00)" in response
    assert "2. פגישה" in response


# === DELETE TASK ===
def test_handle_delete_task():
    pa = PersonalAssistant.load_state(TEST_NAME, confirm_callback=lambda msg: "כן")
    pa.todo_list = [{"description": "פגישה חשובה", "time": "10/10/2025 09:00"}]
    pa.todo_list = [
        {"description": "פגישה", "time": "15/04/2025 09:00"}
    ]
    mock_delete = {"index": 1, "description": "פגישה"}
    with patch.object(PersonalAssistant, 'parse_delete_task_question_with_gpt', return_value=mock_delete):
        response = pa.handle_delete_task_with_gpt("מחק את הפגישה")
        assert "נמחקה" in response
        assert len(pa.todo_list) == 0


# === CLEAR TASKS ===
def test_handle_clear_tasks_yes():
    pa = PersonalAssistant.load_state(TEST_NAME, confirm_callback=lambda msg: "כן")
    pa.todo_list = [{"description": "משימה", "time": None}]
    response = pa.handle_clear_tasks_question("מחק הכל")
    assert "נמחקה" in response
    assert len(pa.todo_list) == 0

def test_handle_clear_tasks_no():
    pa = PersonalAssistant.load_state(TEST_NAME, confirm_callback=lambda msg: "לא")
    pa.todo_list = [{"description": "משימה", "time": None}]
    response = pa.handle_clear_tasks_question("מחק הכל")
    assert "לא נחמקה" in response
    assert len(pa.todo_list) == 1


# === CHAT HISTORY ===
def test_keep_chat_history():
    pa = PersonalAssistant.load_state(TEST_NAME, confirm_callback=lambda msg: "כן")
    pa.keep_chat_history("מה השעה?", "עכשיו 12:00")
    assert pa.messages[-2]["content"] == "מה השעה?"
    assert pa.messages[-1]["content"] == "עכשיו 12:00"


# === SAVE / LOAD ===
def test_save_and_load_state():
    pa = PersonalAssistant.load_state(TEST_NAME, confirm_callback=lambda msg: "כן")
    pa.todo_list = [{"description": "בדיקה", "time": None}]
    pa.messages.append({"role": "user", "content": "שלום"})
    pa.save_state()

    pa2 = PersonalAssistant.load_state(TEST_NAME, confirm_callback=lambda msg: "כן")
    assert pa2.todo_list == pa.todo_list
    assert pa2.messages[-1]["content"] == "שלום"


# === RESET ===
def test_handle_reset_question_yes():
    pa = PersonalAssistant.load_state(TEST_NAME, confirm_callback=lambda msg: "כן")
    pa.todo_list = [{"description": "משימה", "time": None}]
    pa.messages.append({"role": "user", "content": "שלום"})
    response = pa.handle_reset_question("איפוס")
    assert "התחלת שיחה" in response
    assert len(pa.todo_list) == 0
    assert pa.messages[-1]["role"] == "system"

def test_handle_reset_question_no():
    pa = PersonalAssistant.load_state(TEST_NAME, confirm_callback=lambda msg: "לא")
    pa.todo_list = [{"description": "משימה", "time": None}]
    response = pa.handle_reset_question("איפוס")
    assert "הבקשה בוטלה" in response
    assert len(pa.todo_list) == 1


# === LOAD EXISTING ===
def test_load_existing_agent_state():
    unique_name = "test_load_state"
    todo_file = os.path.join(BASE_DIR, "data", f"todo_list_{unique_name}.json")
    # todo_file = f"data/todo_list_{unique_name}.json"

    initial_tasks = [{"description": "פגישה ישנה", "time": "10/10/2025 10:00"}]

    # כתיבה רגילה ואז בדיקה ישירה שהקובץ נטען נכון
    with open(todo_file, "w", encoding="utf-8") as f:
        json.dump(initial_tasks, f, ensure_ascii=False, indent=2)

    pa = PersonalAssistant.load_state(unique_name, confirm_callback=lambda m: "כן")
    assert pa.todo_list == initial_tasks
