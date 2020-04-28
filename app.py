from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
import os
import uuid
from dateutil import parser
from functools import wraps
from worker import conn
from datetime import timedelta, datetime
from worker_functions import send_notification_message
from rq_scheduler import Scheduler


app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(
    basedir, "crud.sqlite"
)
messaging_scheduler = Scheduler(connection=conn)
db = SQLAlchemy(app)
ma = Marshmallow(app)

# used to store files for respective tasks
BASE_FILE_PATH = "tasks/"


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, nullable=False)
    due_date = db.Column(db.DateTime, nullable=False)
    file_path = db.Column(db.Text, nullable=True)
    email_address = db.Column(db.Text, nullable=True)

    def __init__(self, title, description, status, due_date, file_path, email_address):
        self.title = title
        self.description = description
        self.status = status
        self.due_date = due_date
        self.file_path = file_path
        self.email_address = email_address

    STATUS_TYPES = ["Blocked", "Backlog", "Pending", "In Progress", "Done"]


class TaskSchema(ma.Schema):
    class Meta:
        fields = (
            "id",
            "title",
            "description",
            "status",
            "due_date",
            "file_path",
            "email_address",
        )


task_schema = TaskSchema()
tasks_schema = TaskSchema(many=True)


def api_version(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if kwargs["version"] != "1.0":
            return (
                f"Error sending request to invalid api version: {kwargs['version']}",
                400,
            )
        else:
            return f(*args, **kwargs)

    return wrapped

# GET specific task details from task id
# returns a JSON object of the specified task id
# expected output:
# {
#   "id": int
#   "description": string
#   "due_date": timestamp
#   "status": string 
#   "title": string
#   "email_address": string
#   "file_path": string
# }
@app.route("/api/<version>/task/<id>", methods=["GET"])
@api_version
def task_detail(version, id):
    task = Task.query.get(id)
    return task_schema.jsonify(task)

# GET list of tasks
# potential filtering options:
#
# status: status of task
# title: specific title of the task
# due_before_date: date (ex 2020-11-02)
# due_after_date: date (ex 2020-11-02)
# sort due_date: asc/desc
#
# Example output:
#{
#  "tasks": [
#    {
#      "description": "okay",
#      "due_date": "2020-04-27T19:30:00",
#      "email_address": null,
#      "file_path": "tasks/7d7c8049d02b4e1894d493c8aa24d32a",
#      "id": 69,
#      "status": "done",
#      "title": "test"
#    },
#    {
#      "description": "okay",
#      "due_date": "2020-04-27T19:09:00",
#      "email_address": null,
#      "file_path": "tasks/efbb31f386de48f397960512f05c21a9",
#      "id": 78,
#      "status": "done",
#      "title": "test"
#    },
#  ]
#}
@app.route("/api/<version>/task", methods=["GET"])
@api_version
def get_task(version):

    tasks = Task.query

    if request.args.get("status"):
        tasks = tasks.filter(
            Task.status.in_(request.args.get("status").lower().split(","))
        )

    if request.args.get("title"):
        tasks = tasks.filter(Task.title == request.args.get("title").lower())

    if request.args.get("due_before_date"):
        tasks = tasks.filter(
            Task.due_date < parser.parse(request.args.get("due_before_date"))
        )

    if request.args.get("due_after_date"):
        tasks = tasks.filter(
            Task.due_date > parser.parse(request.args.get("due_after_date"))
        )

    if request.args.get("due_date_sort_by"):
        if request.args.get("due_date_sort_by").lower() == "asc":
            tasks = tasks.order_by(Task.due_date.asc())
        elif request.args.get("due_date_sort_by").lower() == "desc":
            tasks = tasks.order_by(Task.due_date.desc())
        else:
            return {"tasks": {}}, 400

    result = tasks_schema.dump(tasks.all())
    return {"tasks": result}, 200


# POST to create new task
# Parameters:
#
# status: string (required)
# title: string (required) 
# due_date: string (required) - date (ex "2020-04-27T19:08:40")
# description: string (required)
# email_address: string (optional) - used for sending notification messages
#
# Returns the new task object in JSON
# ex:
#{
#  "description": "something",
#  "due_date": "2020-04-27T19:08:40",
#  "email_address": null,
#  "file_path": "tasks/21fa32c937a148809cd4462389153eb3",
#  "id": 80,
#  "status": "done",
#  "title": "test"
#}
@app.route("/api/<version>/task", methods=["POST"])
def add_task(version):
    try:
        title = request.json["title"]
        description = request.json["description"]
        status = request.json["status"]
        due_date = parser.parse(request.json["due_date"])
        email_address = request.json.get("email_address")

        if status.lower() not in [status.lower() for status in Task.STATUS_TYPES]:
            raise Exception(
                f"Attempting to set invalid status type, must be within {Task.STATUS_TYPES}"
            )

        # generate the folder for which all respective files that link to the task will go
        task_folder = uuid.uuid4().hex
        file_path = BASE_FILE_PATH + task_folder
        os.makedirs(file_path)
        new_task = Task(title, description, status, due_date, file_path, email_address)

        db.session.add(new_task)
        db.session.commit()

        messaging_scheduler.enqueue_at(
            new_task.due_date - timedelta(hours=1),
            send_notification_message,
            new_task.title,
            new_task.status,
            new_task.due_date,
            new_task.description,
            new_task.email_address,
        )

        return task_schema.jsonify(new_task), 200
    except Exception as e:
        return f"An error occured while trying to add a task: {e}", 400

# PUT to update the task 
# Ability to update any of the follow parameters:
#  title: string
#  description: string 
#  due_date: string
#  status: string
#  email_address: string (nullable=True)
#  file_path: string (nullable=True)
#}
# Returns the updated task object in JSON
@app.route("/api/<version>/task/<id>", methods=["PUT"])
@api_version
def task_update(version, id):
    req = request.get_json()

    task = Task.query.get(id)
    if task:
        for key, value in req.items():
            setattr(task, key, value)

        db.session.commit()
        return task_schema.jsonify(task)
    else:
        return {}, 400


# DELETE to remove the task 
# Takes in the task id to be removed
# Returns the task in JSON if successfully delete
@app.route("/api/<version>/task/<id>", methods=["DELETE"])
@api_version
def user_delete(version, id):
    task = Task.query.get(id)
    if task:
        db.session.delete(task)
        db.session.commit()

        return task_schema.jsonify(task)
    else:
        return {}, 400


# POST to upload a file for the corresponding task id
# Saves the tasks file within it's respective folder which is generated on task creation
# Allows for any file to be uploaded
@app.route("/api/<version>/task/<id>/file_upload", methods=["POST"])
@api_version
def task_file_upload(version, id):
    try:
        task_file = request.files["file"]
        task = Task.query.get(id)

        task_file.save(f"{task.file_path}/{task_file.filename}")

        return f"Sucessfully uploaded {task_file.filename}", 200
    except Exception as e:
        return f"An error occured while trying to add a task: {e}", 400


if __name__ == "__main__":
    app.run(debug=True)
