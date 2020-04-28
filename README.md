Wrote using Python 3.7 and Flask 1.1.1

Install Dependencies:

```
pip install -r requirements.txt
redis (brew install redis if on MacOS)
```


Running the application:
```
python -c 'from app import db; db.create_all()' // to create the db
python app.py
```

Starting the worker:
```
python3 worker.py --with-scheduler
rqscheduler
```
Functionality:

- Implemented the CRUD (Create Read Update Delete) functionality of the task feature
- Ability to upload files for respective tasks 
- Job scheduler for sending the user an email about their task that is close to being due


Most of the application is written in `app.py` which includes the application setup, creation of models, and endpoints - as opposed to a MVC structure
to reduce vertical distance.

Due to time boxing myself for the 3 hours, unfortunetly I wasn't able to add tests or one of the features which I thought would be pretty interesting
which would be the ability to string search by Title or Description - would've been interesting to set up elasticsearch for it, even though it would
be overkill.
