from assistant import PersonalAssistant


def ask_user_confirm(msg):
    return input(msg)


def main():
    ai_assistant = PersonalAssistant.load_state("Ajent 1", confirm_callback=ask_user_confirm)
    while True:
        user_input = input("")
        response = ai_assistant.process_user_input(question=user_input)
        if response == "break":
            break
        print(response)

    # print(ai_assistant.todo_list)
    # ai2 = PersonalAssistant.load_state("2")
    # ai2.analyze_question()
    # print(ai2.todo_list)
    # ai_assistant.analyze_question()


if __name__ == "__main__":
    main()
