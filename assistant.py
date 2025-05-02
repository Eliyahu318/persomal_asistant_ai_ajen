import json
import logging
import os
from datetime import date, datetime
from typing import Callable, Optional

from config import settings
from prompts import PARSE_DELETE_QUESTION_WITH_GPT_PROMPT
from prompts import PARSE_QUESTION_WITH_GPT_PROMPT
from prompts import PARSE_TASK_WITH_GPT_PROMPT
from storege import ensure_file_exists, save_json_file, load_json_file, log_deleted_message, log_deleted_task
from gpt_client import ask_gpt

# Enable debug logging
DEBUG_MODE = True
logging.basicConfig(level=logging.DEBUG)

# משתיק לוגים של openai, httpx, httpcore
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# logging = logging.getlogging(__name__)
# logging.setLevel(logging.DEBUG)


# Set your OpenAI API key
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# client = OpenAI(api_key=settings.openai_api_key)
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FILE_TASKS_NAME = str(settings.data_dir / settings.lead_template)  # os.path.join(BASE_DIR, "data", "todo_list_{name}.json")
FILE_MESSAGES_NAME = str(settings.data_dir / settings.chat_template)  # os.path.join(BASE_DIR, "data", "chat_log_{name}.json")

WELCOME_MESSAGE = "היי! התחלת שיחה עם {name} - העוזר האישי שלך. מה ברצונך?"
TODAY = date.today().isoformat()  # Current date for temporal context


class PersonalAssistant:
    def __init__(self, name: str, todo_list=None, messages=None, confirm_callback=None, settings=settings):
        """
        Initializes the PersonalAssistant instance.

        @param name: Name identifier for the assistant instance.
        @param todo_list: Optional initial task list.
        @param messages: Optional chat history.
        @param confirm_callback: Optional callback for yes/no confirmations.
        """
        self._name = name
        self._confirm_callback = confirm_callback
        self._awaiting_confirmation = None
        self._todo_file = FILE_TASKS_NAME.format(name=name)
        self._chat_file = FILE_MESSAGES_NAME.format(name=name)
        self._settings = settings

        ensure_file_exists(self._todo_file)
        ensure_file_exists(self._chat_file)

        self._todo_list = todo_list if todo_list is not None else []
        self._messages = messages if messages is not None else [{
            "role": "system",
            "content": "אתה עוזר אישי חכם. תזכור את מה שהמשתמש אומר וענה בצורה ברורה ונעימה."
        }]

    def personal_welcome_message(self) -> str:
        """Returns a welcome message personalized with the assistant's name."""
        return WELCOME_MESSAGE.format(name=self._name)

    def parse_question_intent_with_gpt(self, question: str) -> str:
        """Uses GPT to classify the user's intent from the input question."""
        response = ask_gpt(system_prompt=PARSE_QUESTION_WITH_GPT_PROMPT, user_input=question)
        if DEBUG_MODE:
            logging.debug(response)
        return response

    def dispatch_command(self, intent: str) -> Callable[..., str] | None:
        """Returns the appropriate handler function based on the detected intent."""
        intent_handlers = {
            "שמור": self.save_question,
            "מחק משימה": self.ensure_delete_intent,
            "איפוס": self.ensure_reset_intent,
            "הצג משימות": self.show_tasks_question,
            "מחק כל המשימות": self.ensure_delete_all_tasks_intent

        }
        try:
            user_intent = intent_handlers[intent]
            return user_intent
        except KeyError:
            return None

    def process_user_input(self, question: str) -> str:
        """
        Processes the user's message and returns the assistant's response.

        This method is the main entry point for user interaction. It checks if the assistant is
        currently waiting for a yes/no confirmation. If so, it handles that confirmation.
        Otherwise, it uses GPT to determine the user's intent and routes it to the appropriate handler.

        @param question: The user's message as a string.
        @return: A string response from the assistant.
        """
        if self._awaiting_confirmation:
            answer = question.strip().lower()
            if answer == "כן":
                func, args = self._awaiting_confirmation
                self._awaiting_confirmation = None
                if args:
                    response_text = func(*args)
                else:
                    response_text = func()
                if func != self.reset_all:
                    self.keep_chat_history(question, response_text)
                return response_text

            elif answer == "לא":
                self._awaiting_confirmation = None
                response_text = "הפעולה בוטלה. איך אפשר לעזור?"
                self.keep_chat_history(question, response_text)
                return response_text
            else:
                return "ענה בבקשה 'כן' או 'לא' כדי שאוכל להמשיך."

        elif question.lower() == "exit":
            self.save_state()
            return "להתראות!"

        elif question == "בקרה":
            # logging.debug(self._messages)
            return str(self._messages)  # "📊 היסטוריית השיחה הודפסה ללוג."

        else:
            intent = self.parse_question_intent_with_gpt(question)
            handler = self.dispatch_command(intent)
            if handler:
                try:
                    response = handler(question)
                    return response
                except TypeError:
                    response = handler()
                    return response
                finally:
                    self.keep_chat_history(question, response)

            else:
                self.keep_chat_history(question, intent)
                return intent

    def parse_save_question_with_gpt(self, question: str) -> list:
        """Uses GPT to extract task information from the user's input."""
        prompt = PARSE_TASK_WITH_GPT_PROMPT.format(today=TODAY)
        response = ask_gpt(system_prompt=prompt, user_input=question)
        try:
            tasks = json.loads(response)  # Parse JSON string to Python object
            if isinstance(tasks, dict):
                tasks = [tasks]  # Ensure it's always a list
            assert isinstance(tasks, list)  # Validate format of each task
            for task in tasks:
                assert "description" in task and "time" in task
            return tasks

        except json.JSONDecodeError:
            if DEBUG_MODE:
                logging.debug("❌ JSON לא תקין – מנסה ניסוח מחודש...")
            # Retry once with a simpler prompt
            fallback_prompt = (
                f"היום זה {TODAY}. החזר רק JSON תקין! לדוגמה: "
                '[{"description": "לשלם חשבון", "time": "03/04/2025 18:00"}]'
            )
            retry_response = ask_gpt(system_prompt=fallback_prompt, user_input=question)
            try:
                tasks = json.loads(retry_response)
                if isinstance(tasks, dict):
                    tasks = [tasks]
                for task in tasks:
                    assert "description" in task and "time" in task
                return tasks
            except Exception as e:
                if DEBUG_MODE:
                    logging.exception("❌ גם הניסיון השני נכשל – שגיאה:")
                raise

        except AssertionError:
            if DEBUG_MODE:
                logging.debug("הפלט לא כולל description ו-time כנדרש:")
            raise
        except Exception:
            if DEBUG_MODE:
                logging.debug("שגיאה לא צפויה:")
            raise

    def save_question(self, question: str) -> str:
        """Handles task saving based on user input and returns a success/failure message."""
        try:
            task = self.parse_save_question_with_gpt(question)
            if task:
                self._todo_list.extend(task)
                save_json_file(self._todo_file, self._todo_list)
                response_text = f"{len(task)} משימות נשמרו בהצלחה. איך עוד אפשר לעזור?"
                # self.keep_chat_history(question, response_text)
                return response_text
            else:
                raise Exception("No tasks returned from GPT")

        except Exception as e:
            response_text = "לא הצלחתי להבין את המשימה. נסה לנסח שוב."
            # self.keep_chat_history(question, response_text)
            if DEBUG_MODE:
                logging.debug(f"שגיאה: {e}")
            return response_text

    def show_tasks_question(self) -> str:
        """Returns a string of all tasks currently saved."""
        if not self._todo_list:
            return "אין משימות כרגע."
        show_str = ""
        for i, task in enumerate(self._todo_list, 1):
            desc = task.get("description", "ללא תיאור")
            time = task.get("time")
            if time:
                show_str += f"{i}. {desc} ({time})\n"
            else:
                show_str += f"{i}. {desc}\n"
        return show_str

    def parse_delete_task_question_with_gpt(self, question: str) -> dict | None:
        """Uses GPT to determine which task the user wants to delete."""
        task_list_json = json.dumps(self._todo_list, ensure_ascii=False, indent=2)
        prompt = PARSE_DELETE_QUESTION_WITH_GPT_PROMPT.format(task_list=task_list_json)

        response = ask_gpt(system_prompt=prompt, user_input=question)
        try:
            task_parsed = json.loads(response)
            if not task_parsed:
                raise
            if not ("index" in task_parsed and "description" in task_parsed):
                raise
            return task_parsed

        except Exception as e:
            if DEBUG_MODE:
                logging.exception("❌ לא הצלחתי להבין את בקשת המחיקה.", e)
            return None

    def delete_task(self, index: int, desc: str, original_question: str) -> str:
        """Prepares task deletion by asking for confirmation from the user."""
        try:
            task = self._todo_list.pop(index - 1)
            log_deleted_task(self._name, task)
            save_json_file(self._todo_file, self._todo_list)
            response = f"המשימה '{desc}' נמחקה."
        except IndexError:
            logging.error("אינדקס לא חוקי")
            response = "אינדקס לא חוקי"
        except Exception as e:
            if DEBUG_MODE:
                logging.debug("debug:  ", e)
            response = "שגיאה בעת מחיקה."
        # self.keep_chat_history(original_question, response)
        return response

    def ensure_delete_intent(self, question: str) -> str:
        """Executes confirmed deletion of a task by index."""
        try:
            task = self.parse_delete_task_question_with_gpt(question)
            index = task["index"]
            desc = task["description"]
            self._awaiting_confirmation = (self.delete_task, (index, desc, question))
            response_text = f'האם למחוק את המשימה: "{desc}" (#{index})? [כן/לא]'
            # self.keep_chat_history(question, response_text)
            return response_text
        except Exception:
            response_text = "❌ לא הצלחתי להבין מה למחוק."
            # self.keep_chat_history(question, response_text)
            return response_text

    def clear_all_tasks(self):
        """Clears all saved tasks."""
        save_json_file(self._todo_file, self._todo_list)
        self._todo_list.clear()
        response_text = "רשימת המשימות נמחקה, איך עוד אפשר לעזור?."
        # self.keep_chat_history(question, response_text)
        return response_text

    def ensure_delete_all_tasks_intent(self, original_question: str):
        """Executes confirmed deletion all task."""
        self._awaiting_confirmation = (self.clear_all_tasks, None)
        response_text = "האם למחוק את כל המשימות? [כן/לא]"
        # self.keep_chat_history(original_question, response_text)
        return response_text

    def clear_messages(self) -> str:
        """Clears the assistant's message history."""
        entry = {
            "deleted_at": datetime.now().isoformat(timespec="seconds"),
            "task": self._messages
        }
        log_deleted_message(self._name, entry=entry)
        self._messages.clear()
        return "היסטוריית השיחות נמחקה"

    def reset_all(self) -> str:
        """Performs a full reset of tasks and messages."""
        self.clear_all_tasks()
        self.clear_messages()
        self._messages.append({
            "role": "system",
            "content": "אתה עוזר אישי חכם. תזכור את מה שהמשתמש אומר וענה בצורה ברורה ונעימה."
        })
        return self.personal_welcome_message()

    def ensure_reset_intent(self, original_question: str):
        """Executes confirmed reset"""
        self._awaiting_confirmation = (self.reset_all, None)
        response_text = "האם ברצונך לאפס הכל ולמחוק את המשמיות ואת היסטוריית השיחה? [כן/לא]"
        # self.keep_chat_history(original_question, response_text)
        return response_text

    def keep_chat_history(self, question, response):
        """Appends the latest exchange to the assistant's memory."""
        self._messages.append({"role": "user", "content": question})
        self._messages.append({"role": "assistant", "content": f"{response}"})

    @classmethod
    def load_state(cls, name: str, confirm_callback=None) -> "PersonalAssistant":
        """
        Loads a saved PersonalAssistant instance by name.
        Read tasks and messages from files if they exist, otherwise initializes them with default values.
        """
        todo_file = FILE_TASKS_NAME.format(name=name)
        chat_file = FILE_MESSAGES_NAME.format(name=name)
        if os.path.exists(todo_file):
            todo_list = load_json_file(todo_file)
        else:
            todo_list = []

        if os.path.exists(chat_file):
            messages = load_json_file(chat_file)
        else:
            messages = None  # Makes to __init__ enter system to messages

        return cls(name=name, todo_list=todo_list, messages=messages, confirm_callback=confirm_callback)

    def save_state(self):
        """Saves current task list and message history to disk."""
        save_json_file(self._todo_file, self._todo_list)
        save_json_file(self._chat_file, self._messages)
