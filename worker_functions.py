import yagmail

def send_notification_message(task_title, task_status, task_due_date, task_description, task_email_address):
    # horrible practice but more of a example - instead store credentials in hashed key
    yag = yagmail.SMTP('mygmailusername', 'mygmailpassword')
    contents = [
        f"Your task is about to be due with the following details:\n"
        f"Title: {task_title}\n"
        f"Description: {task_description}\n"
        f"Due date: {task_due_date}\n"
        f"Status: {task_due_date}\n"
    ]
    yag.send(task_email_address, f'Task about to be due: {task_title}', contents)
