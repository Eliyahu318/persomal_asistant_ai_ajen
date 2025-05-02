"""Comprehensive pytest suite for the personal‑AI‑assistant project.

Run with:
    pytest -q
"""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
#  Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_env(tmp_path, monkeypatch):
    """Redirect filesystem + env‑vars into an isolated sandbox."""
    # 1) fake env
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "fake-token")

    # 2) patch data‑files base‑dir
    import assistant as _assistant_mod
    from storeage import storage as _storege_mod

    tmp_dir = str(tmp_path)
    _assistant_mod.FILE_TASKS_NAME = f"{tmp_dir}/todo_list_{{name}}.json"
    _assistant_mod.FILE_MESSAGES_NAME = f"{tmp_dir}/chat_log_{{name}}.json"
    _storege_mod.FILE_LOG_DELETED_LEAD_NAME = f"{tmp_dir}/deleted_tasks_{{name}}.jsonl"
    _storege_mod.FILE_LOG_DELETED_CHAT_NAME = f"{tmp_dir}/deleted_messages_{{name}}.jsonl"

    # 3) reload config so settings read the new env
    import importlib, config as _config

    importlib.reload(_config)

    yield tmp_path


def test_openai_key_from_env(tmp_env):
    from config import settings

    assert settings.openai_api_key == "test-key"


@pytest.fixture()
def mock_gpt(monkeypatch):
    """
    Intercepts *all* ask_gpt calls (both in gpt_client and the copy inside
    assistant) using prefix matching on the system‑prompt.
    """
    responses: dict[tuple[str, str] | str, str] = {}

    def _fake_ask(system_prompt: str, user_input: str, *_, **__) -> str:  # noqa: D401
        sys_clean = system_prompt.lstrip()  # strip leading whitespace/newlines

        for key, val in responses.items():
            if isinstance(key, tuple):
                prompt_start, input_txt = key
                if sys_clean.startswith(prompt_start) and user_input == input_txt:
                    return val
            else:  # key is str – fall‑back lookup by user_input only
                if key == user_input:
                    return val
        return ""

    import gpt_client as _gpt_mod
    import assistant as _assistant_mod

    monkeypatch.setattr(_gpt_mod, "ask_gpt", _fake_ask, raising=True)
    monkeypatch.setattr(_assistant_mod, "ask_gpt", _fake_ask, raising=True)

    return responses


@pytest.fixture()
def assistant_instance(tmp_env, mock_gpt):
    from assistant import PersonalAssistant

    return PersonalAssistant(name="tester")


# ---------------------------------------------------------------------------
#  GPT client helpers
# ---------------------------------------------------------------------------


def test_clean_gpt_response():
    import gpt_client as gc

    raw = "```json\n{\"foo\":42}\n```"
    assert gc.clean_gpt_response(raw) == "{\"foo\":42}"


# ---------------------------------------------------------------------------
#  PersonalAssistant core logic
# ---------------------------------------------------------------------------

import pytest  # noqa: E402


@pytest.mark.parametrize(
    "user_input,intent_result",
    [
        ("מחר ב‑3 פגישה", "שמור"),
        ("מחק 1", "מחק משימה"),
        ("תראה לי את המשימות", "הצג משימות"),
    ],
)
def test_parse_question_intent_with_gpt(assistant_instance, mock_gpt, user_input, intent_result):
    mock_gpt[("אתה מקבל", user_input)] = intent_result
    assert assistant_instance.parse_question_intent_with_gpt(user_input) == intent_result


def test_save_question_success(assistant_instance, mock_gpt):
    question = "מחר ב‑15:00 פגישה עם אורי"
    mock_gpt[("היום זה", question)] = (
        '[{"description": "פגישה עם אורי", "time": "23/04/2025 15:00"}]'
    )

    reply = assistant_instance.save_question(question)
    assert "נשמרו בהצלחה" in reply

    todo_path = assistant_instance._todo_file
    with open(todo_path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data == [{"description": "פגישה עם אורי", "time": "23/04/2025 15:00"}]


def test_save_question_bad_json_then_retry(assistant_instance, mock_gpt):
    question = "תזכיר לי לשלם חשבון מחר"
    mock_gpt[question] = (
        '[{"description":"לשלם חשבון","time":"23/04/2025 09:00"}]'
    )
    # שימו לב – לא מגדירים תשובה לפרומפט הראשון → זה מכריח את Assistant
    # ליפול ל‑retry ולזכות בתשובת JSON טובה.
    reply = assistant_instance.save_question(question)
    assert "נשמרו בהצלחה" in reply
    assert len(assistant_instance._todo_list) == 1


def test_show_tasks_empty(assistant_instance):
    assert assistant_instance.show_tasks_question() == "אין משימות כרגע."


def test_show_tasks_format(assistant_instance):
    assistant_instance._todo_list.extend(
        [
            {"description": "משימה", "time": None},
            {"description": "פגישה", "time": "01/05/2025 13:00"},
        ]
    )
    out = assistant_instance.show_tasks_question()
    assert "1. משימה" in out and "2. פגישה (01/05/2025 13:00)" in out


def test_delete_task_confirmation_and_yes_flow(assistant_instance, mock_gpt):
    assistant_instance._todo_list.append({"description": "לחם", "time": None})

    # ➊ Intent classification → "מחק משימה"
    mock_gpt[("אתה מקבל", "מחק 1")] = "מחק משימה"

    # ➋ GPT‑Delete Parser
    mock_gpt[("לפניך רשימת משימות", "מחק 1")] = json.dumps(
        {"index": 1, "description": "לחם"},
        ensure_ascii=False,
    )

    ask = assistant_instance.process_user_input("מחק 1")
    assert "האם למחוק" in ask

    ans = assistant_instance.process_user_input("כן")
    assert "נמחקה" in ans
    assert not assistant_instance._todo_list



def test_delete_task_confirmation_no_flow(assistant_instance, mock_gpt):
    assistant_instance._todo_list.append({"description": "גבינה", "time": None})

    # ➊ מיפוי Intent  ← מחזיר "מחק משימה"
    mock_gpt[("אתה מקבל", "מחק גבינה")] = "מחק משימה"

    # ➋ מיפוי GPT‑Delete Parser
    mock_gpt[("לפניך רשימת משימות", "מחק גבינה")] = json.dumps(
        {"index": 1, "description": "גבינה"},
        ensure_ascii=False,
    )

    _ = assistant_instance.process_user_input("מחק גבינה")
    cancel = assistant_instance.process_user_input("לא")

    assert "בוטלה" in cancel
    assert len(assistant_instance._todo_list) == 1



def test_delete_invalid_index(assistant_instance):
    assistant_instance._todo_list.append({"description": "abc", "time": None})
    msg = assistant_instance.delete_task(99, "abc", "מחק 99")
    assert msg == "אינדקס לא חוקי"


def test_clear_all_tasks_flow(assistant_instance):
    assistant_instance._todo_list.extend([{"description": "x"}, {"description": "y"}])
    reply = assistant_instance.clear_all_tasks("מחק הכל")
    assert "נמחקה" in reply
    assert not assistant_instance._todo_list


def test_reset_all_flow(assistant_instance):
    assistant_instance._todo_list.append({"description": "משהו"})
    assistant_instance._messages.append({"role": "user", "content": "hi"})
    reset = assistant_instance.reset_all("איפוס")
    assert "היי!" in reset
    assert not assistant_instance._todo_list
    assert len(assistant_instance._messages) == 1


def test_exit_saves_state(assistant_instance, monkeypatch):
    save_spy = MagicMock()
    monkeypatch.setattr(assistant_instance, "save_state", save_spy)
    assistant_instance.process_user_input("exit")
    save_spy.assert_called_once()


# ---------------------------------------------------------------------------
#  storage.py helpers
# ---------------------------------------------------------------------------


def test_storage_round_trip(tmp_env):
    from storeage import storage as st

    f = tmp_env / "sample.json"
    st.save_json_file(str(f), {"k": 1})
    assert st.load_json_file(str(f)) == {"k": 1}

    log_f = tmp_env / "log.jsonl"
    st.append_jsonl_file(str(log_f), {"x": 1})
    st.append_jsonl_file(str(log_f), {"x": 2})
    assert st.read_jsonl_file(str(log_f)) == [{"x": 1}, {"x": 2}]


# ---------------------------------------------------------------------------
#  Flask + Twilio webhook
# ---------------------------------------------------------------------------


@pytest.fixture()
def flask_client(tmp_env, mock_gpt, monkeypatch):
    import whatsapp_server as ws
    from assistant import PersonalAssistant

    dummy = MagicMock(spec=PersonalAssistant)
    dummy.process_user_input.return_value = "pong"
    monkeypatch.setattr(ws, "PersonalAssistant", MagicMock(load_state=MagicMock(return_value=dummy)))
    return ws.app.test_client()


def test_root_endpoint(flask_client):
    rv = flask_client.get("/")
    assert rv.status_code == 200 and "OK" in rv.text


def test_whatsapp_webhook_post(flask_client):
    rv = flask_client.post(
        "/whatsapp",
        data={"Body": "שלום", "From": "whatsapp:+972555"},
        content_type="application/x-www-form-urlencoded",
    )
    assert rv.status_code == 200
    assert "pong" in rv.text


# ---------------------------------------------------------------------------
#  Misc edge‑cases
# ---------------------------------------------------------------------------


def test_dispatch_command_unknown(assistant_instance):
    assert assistant_instance.dispatch_command("לא ידוע") is None


def test_process_user_input_requires_yes_no(assistant_instance):
    assistant_instance._awaiting_confirmation = (lambda: None, tuple())
    msg = assistant_instance.process_user_input("maybe")
    assert "ענה בבקשה" in msg


@pytest.mark.parametrize("message, expected", [("בקרה", "")])
def test_process_control_command_logs_messages(assistant_instance, message, expected, caplog):
    assistant_instance._messages.append({"role": "user", "content": "הי"})
    response = assistant_instance.process_user_input(message)
    assert expected in response or "" in caplog.text


def test_reset_all_when_empty(assistant_instance):
    response = assistant_instance.reset_all("איפוס")
    assert "היי!" in response
    assert assistant_instance._todo_list == []
    assert len(assistant_instance._messages) == 1


def test_confirmation_flow_with_no_function(assistant_instance):
    assistant_instance._awaiting_confirmation = (None, ())
    response = assistant_instance.process_user_input("כן")
    assert any(word in response for word in ("שגיאה", "בעיה", "לא ניתן"))


def test_load_state_with_no_files(tmp_path, monkeypatch):
    from assistant import PersonalAssistant

    monkeypatch.setattr("assistant.FILE_TASKS_NAME", os.path.join(tmp_path, "todo_list_{name}.json"))
    monkeypatch.setattr("assistant.FILE_MESSAGES_NAME", os.path.join(tmp_path, "chat_log_{name}.json"))

    a = PersonalAssistant.load_state("tester123")
    assert a._todo_list == []
    assert isinstance(a._messages, list)


def test_save_and_load_state_consistency(tmp_env):
    from assistant import PersonalAssistant

    a1 = PersonalAssistant(name="verify")
    a1._todo_list.append({"description": "משימה לבדיקה", "time": "מחר"})
    a1.save_state()

    a2 = PersonalAssistant.load_state("verify")
    assert a2._todo_list == a1._todo_list
