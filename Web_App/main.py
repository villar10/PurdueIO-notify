import string
import pytz
from datetime import datetime
from google.cloud import datastore

from flask import Flask, request, render_template, send_file
from flask.helpers import url_for
from flask_restful import Api, Resource, reqparse
import requests

app = Flask(__name__, static_folder='static', static_url_path='/static', template_folder='templates')
api = Api(app)



if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)