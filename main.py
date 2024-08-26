from flask import Flask, jsonify
import json
from flask_mysqldb import MySQL
from GetAppData import GetAppData  
from GetAccessToken import get_access_token  
from GetUser import get_User

app = Flask(__name__)

# Database configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'ghl_api'

mysql = MySQL(app)

# Load config from JSON file
try:
    with open('config.json') as config_file:
        config = json.load(config_file)
    app.config.update(config)
except FileNotFoundError:
    raise Exception("Error: config.json file not found.")
except json.JSONDecodeError:
    raise Exception("Error: config.json file is not a valid JSON.")
except KeyError as e:
    raise Exception(f"Error: Missing key in config.json - {e}")

# Register the blueprints
app.register_blueprint(GetAppData, url_prefix='/GetAppData')
app.register_blueprint(get_access_token, url_prefix='/GetAccessToken')
app.register_blueprint(get_User, url_prefix='/GetUser')

if __name__ == '__main__':
    app.run(debug=True, port=8000)
