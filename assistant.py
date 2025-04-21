import json
import logging
import os
from datetime import date, datetime
from openai import OpenAI
from typing import Callable, Optional

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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FILE_TASKS_NAME = os.path.join(BASE_DIR, "data", "todo_list_{name}.json")
FILE_MESSAGES_NAME = os.path.join(BASE_DIR, "data", "chat_log_{name}.json")

WELCOME_MESSAGE = "היי! התחלת שיחה עם {name} - העוזר האישי שלך. מה ברצונך?"
TODAY = date.today().isoformat()  # Current date for temporal context


class PersonalAssistant:
    def __init__(self, name: str, todo_list=None, messages=None, confirm_callback=None):
        self._name = name
        self._confirm_callback = confirm_callback
        self._awaiting_confirmation = None
        self._todo_file = FILE_TASKS_NAME.format(name=name)
        self._chat_file = FILE_MESSAGES_NAME.format(name=name)

        ensure_file_exists(self._todo_file)
        ensure_file_exists(self._chat_file)

        self._todo_list = todo_list if todo_list is not None else []
        self._messages = messages if messages is not None else [{
            "role": "system",
            "content": "אתה עוזר אישי חכם. תזכור את מה שהמשתמש אומר וענה בצורה ברורה ונעימה."
        }]

    def personal_welcome_message(self) -> str:
        return WELCOME_MESSAGE.format(name=self._name)


    def parse_question_intent_with_gpt(self, question: str) -> str:
        # Perses the user intent and return the right code word.
        prompt = PARSE_QUESTION_WITH_GPT_PROMPT
        # Send request to GPT and clean the text response - wrapping triple backticks (```) if present
        response = ask_gpt(system_prompt= prompt, user_input=question)
        if DEBUG_MODE:
            logging.debug(response)
            logging.debug(question)
        return response

    def dispatch_command(self, intent: str) -> Callable[..., str] | None:
        # Get the user intent code from parse_question_intent_with_gpt, and return the right function or None.
        intent_handlers = {
            "שמור": self.handle_save_question,
            "מחק משימה": self.handle_delete_task_with_gpt,
            "איפוס": self.handle_reset_question,
            "הצג משימות": self.handle_show_tasks_question,
            "מחק כל המשימות": self.handle_clear_tasks_question

        }
        try:
            user_intent = intent_handlers[intent]
            return user_intent
        except KeyError:
            return None

    """def process_user_input(self, question) -> str | Callable[..., str]:
        
        The main loop that handles user input and routes it to the correct handler This acts as the central
        controller for the assistant.
        Uses parse_question_intent_with_gpt to get the word code, and active the
        right func with dispatch_command or just send the question to gpt if it's not a command quest.
        
        # while True:
        # question = question
        if question.lower() == "exit":
            self.save_state()
            return "break"

        question_intent_with_gpt = self.parse_question_intent_with_gpt(question)
        func = self.dispatch_command(question_intent_with_gpt)
        if func:
            try:
                response = func(question)
                return response
            except TypeError:
                response = func()
                return response

        elif question == "בקרה":
            logging.debug(self.messages)
            return "📊 היסטוריית השיחה הודפסה ללוג."
        else:
            # logging.info(question_intent_with_gpt)  # It's not a command, so the ajent keep chat with the user.
            response = question_intent_with_gpt
            self.keep_chat_history(question=question, response=question_intent_with_gpt)
            return response"""

    def process_user_input(self, question: str) -> str:
        if self._awaiting_confirmation:
            answer = question.strip().lower()
            if answer == "כן":
                func, args = self._awaiting_confirmation
                self._awaiting_confirmation = None
                return func(*args)
            elif answer == "לא":
                self._awaiting_confirmation = None
                return "הפעולה בוטלה. איך אפשר לעזור?"
            else:
                return "ענה בבקשה 'כן' או 'לא' כדי שאוכל להמשיך."

        if question.lower() == "exit":
            self.save_state()
            return "להתראות!"

        intent = self.parse_question_intent_with_gpt(question)
        handler = self.dispatch_command(intent)
        if handler:
            try:
                return handler(question)
            except TypeError:
                return handler()
        elif question == "בקרה":
            logging.debug(self._messages)
            return self._messages  # "📊 היסטוריית השיחה הודפסה ללוג."
        else:
            self.keep_chat_history(question, intent)
            return intent


    def parse_save_question_with_gpt(self, question: str) -> list:
        # Sends the user's text to GPT for task extraction.
        prompt = PARSE_TASK_WITH_GPT_PROMPT.format(today=TODAY)
        # Send request to GPT and clean the text response - wrapping triple backticks (```) if present
        response = ask_gpt(system_prompt=prompt, user_input=question)
        try:
            tasks = json.loads(response)  # Parse JSON string to Python object
            if isinstance(tasks, dict):
                tasks = [tasks]  # Ensure it's always a list
            # Validate format of each task
            assert isinstance(tasks, list)
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

    def handle_save_question(self, question: str) -> str:
        # Handle the extract task from parse_task_with_gpt. Adds to todo_list, and to todo_file.
        try:
            task = self.parse_save_question_with_gpt(question)  # Extract task(s) from user input
            if task:
                self._todo_list.extend(task)  # Add to current todo_list
                save_json_file(self._todo_file, self._todo_list)  # Persist to file
                response_text = f"{len(task)} משימות נשמרו בהצלחה. איך עוד אפשר לעזור?"
                # logging.info(response_text)
                self.keep_chat_history(question, response_text)
                return response_text
            else:
                raise Exception("No tasks returned from GPT")
        except Exception as e:
            response_text = "לא הצלחתי להבין את המשימה. נסה לנסח שוב."
            self.keep_chat_history(question, response_text)
            logging.error(response_text)  # מה התפקיד של זה? האם זה נצרך?
            if DEBUG_MODE:
                logging.debug(f"שגיאה: {e}")
            return response_text

    def handle_show_tasks_question(self) -> str:
        # Print all tasks in the list in a numbered format
        if not self._todo_list:
            # logging.info("אין משימות כרגע.")
            show_response = "אין משימות כרגע."
            return show_response
        show_str = ""
        for i, task in enumerate(self._todo_list, 1):
            desc = task.get("description", "ללא תיאור")
            time = task.get("time")
            if time:
                show_str += f"{i}. {desc} ({time})\n"
                # logging.info(show_str)
            else:
                show_str += f"{i}. {desc}\n"
                # logging.info(show_str)
        return show_str

    def parse_delete_task_question_with_gpt(self, question: str) -> dict | None:
        # Sends the deletion request and current tasks to GPT, asking which task the user meant to delete.
        task_list_json = json.dumps(self._todo_list, ensure_ascii=False, indent=2)
        prompt = PARSE_DELETE_QUESTION_WITH_GPT_PROMPT.format(task_list=task_list_json)

        response = ask_gpt(system_prompt=prompt, user_input=question)
        try:
            parsed = json.loads(response)
            if not parsed:
                raise
            if not ("index" in parsed and "description" in parsed):
                raise
            return parsed
        except Exception as e:
            if DEBUG_MODE:
                logging.exception("❌ לא הצלחתי להבין את בקשת המחיקה.", e)
            return None

    """def handle_delete_task_with_gpt(self, question: str) -> str | Exception:
        # Get the exact index task to delete from parse_delete_task_question_with_gpt func and handle it.
        exact_task = self.parse_delete_task_question_with_gpt(question)
        if not exact_task:
            logging.error("לא הובן מה למחוק")
            response_to_user = "❌ לא הצלחתי להבין מה למחוק."
            return response_to_user

        index = exact_task["index"]
        description = exact_task["description"]
        # confirm = self.confirm_callback(f'האם למחוק את המשימה: "{description}" (#{index})? [כן/לא] ')  # input(f'האם למחוק את המשימה: "{description}" (#{index})? [כן/לא] ')
        self._awaiting_confirmation = (self._delete_task, (index, description, question))
        if confirm.strip() != "כן":
            logging.info("ביטול פעולה.")
            response_to_user = "הפעולה בוטלה"
            return response_to_user

        try:
            task_to_remove = self._todo_list[index]
            self._todo_list.pop(index - 1)
            log_deleted_task(name=self._name, task=task_to_remove)
            save_json_file(self._todo_file, self._todo_list)
            response_text = f"המשימה '{description}' נמחקה מהרשימה."
            # logging.info(response_text)
            self.handle_show_tasks_question()
            self.keep_chat_history(question, response_text)
            response_to_user = response_text
            return response_to_user
        except IndexError as i:
            logging.error("אינדקס לא חוקי.")
            return "אינדקס לא חוקי"
        except Exception as e:
            if DEBUG_MODE:
                logging.debug("debug:  ", e)
            return "שגיאה לא צפויה"""

    def handle_delete_task_with_gpt(self, question: str) -> str:
        try:
            task = self.parse_delete_task_question_with_gpt(question)
            index = task["index"]
            desc = task["description"]
            self._awaiting_confirmation = (self.delete_task, (index, desc, question))
            return f'האם למחוק את המשימה: "{desc}" (#{index})? [כן/לא]'
        except Exception:
            return "❌ לא הצלחתי להבין מה למחוק."

    def delete_task(self, index: int, desc: str, original_question: str) -> str:
        try:
            task = self._todo_list.pop(index)
            log_deleted_task(self._name, task)
            save_json_file(self._todo_file, self._todo_list)
            response = f"המשימה '{desc}' נמחקה."
        except Exception:
            response = "שגיאה בעת מחיקה."
        self.keep_chat_history(original_question, response)
        return response

    def handle_clear_tasks_question(self, question: str) -> str:
        # Clear all saved tasks from memory and file
        confirm = self._confirm_callback("אתה בטוח שאתה מעוניין למחוק את כל המשימות? (כן/לא)")  # input("אתה בטוח שאתה מעוניין למחוק את כל המשימות? (כן/לא)")
        if confirm == "כן":
            save_json_file(self._todo_file, self._todo_list)
            self._todo_list.clear()
            response_text = "רשימת המשימות נמחקה, איך עוד אפשר לעזור?."
            # logging.info(response_text)
            self.keep_chat_history(question, response_text)
            return response_text
        else:
            response_text = "הבקשה בוטלה והרשימה לא נחמקה, איך עוד אפשר לעזור?."
            # logging.info(response_text)
            self.keep_chat_history(question, response_text)
            return response_text

    def handle_clear_messages_question(self) -> str:
        # Clear the chat history from main ajent file' and save it to log deleted chat file.
        # TODO: Add try/except in case 'chat_log_{name}.json' fails to write. Optionally, rotate or timestamp backups.
        entry = {
                "deleted_at": datetime.now().isoformat(timespec="seconds"),
                "task": self._messages
            }
        log_deleted_message(self._name, entry=entry)
        self._messages.clear()
        # logging.info("היסטוריית השיחות נמחקה")
        return "היסטוריית השיחות נמחקה"

    def handle_reset_question(self, question: str) -> str:
        # Perform full reset of conversation and tasks
        confirm = self._confirm_callback("אתה בטוח שאתה מעוניין לאפס את כל המשימות ואת היסטוריית השיחה בנינו? (כן/לא)")  # input("אתה בטוח שאתה מעוניין לאפס את כל המשימות ואת היסטוריית השיחה בנינו? (כן/לא)")
        if confirm == "כן":
            self.handle_clear_tasks_question(question)
            self.handle_clear_messages_question()
            self._messages.append({
                "role": "system",
                "content": "אתה עוזר אישי חכם. תזכור את מה שהמשתמש אומר וענה בצורה ברורה ונעימה."
            })
            # logging.info(WELCOME_MESSAGE)
            return WELCOME_MESSAGE
        else:
            # logging.info("הבקשה בוטלה.")
            response_text = "לא, אני לא מעוניין לאפס הכל"
            self.keep_chat_history(question, response_text)
            return ", איך עוד אפשר לעזור? הבקשה בוטלה."


    def keep_chat_history(self, question, response):
        # Append user question and GPT response to the message history
        self._messages.append({"role": "user", "content": question})
        self._messages.append({"role": "assistant", "content": f"{response}"})

    @classmethod
    def load_state(cls, name: str, confirm_callback = None) -> "PersonalAssistant":
        """
        Loads a saved PersonalAssistant instance by name.

        Reads tasks and messages from files if they exist,
        otherwise initializes them with default values.
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
        save_json_file(self._todo_file, self._todo_list)
        save_json_file(self._chat_file, self._messages)

