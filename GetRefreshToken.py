from flask import current_app
import requests
import time
from flask_mysqldb import MySQL

# Initialize MySQL object (assuming you have MySQL configuration)
mysql = MySQL()

def get_oauth_settings():
    """Retrieve OAuth settings from app config."""
    base_url = current_app.config.get('baseUrl')
    client_id = current_app.config.get('clientId')
    client_secret = current_app.config.get('clientSecret')
    user_type = current_app.config.get('userType')
    return base_url, client_id, client_secret, user_type

def get_expired_tokens():
    """Retrieve tokens that are expired or will expire soon from the database."""
    cursor = mysql.connection.cursor()
    current_timestamp = int(time.time())
    
    try:
        cursor.execute("SELECT access_token, refresh_token, token_type, userType, companyId, locationId, code, expire FROM token WHERE expire <= %s", (current_timestamp,))
        tokens = cursor.fetchall()
    except Exception as e:
        cursor.close()
        raise Exception(f"Database query error: {str(e)}")
    
    cursor.close()
    return tokens

def refresh_access_token(client_id, client_secret, refresh_token, user_type, code):
    """Use the refresh token to get a new access token."""
    url = "https://services.leadconnectorhq.com/oauth/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "user_type": user_type
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }
    
    try:
        response = requests.post(url, data=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        raise Exception(f"HTTP error: {str(e)}, Response: {response.text}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Request error: {str(e)}")

def update_token_in_db(token_data, code, expire_timestamp):
    """Update or insert the new token data in the database."""
    cursor = mysql.connection.cursor()
    
    location_id = token_data.get("locationId", "")
    company_id = token_data.get("companyId", "")
    
    stmt = """
        INSERT INTO token (access_token, refresh_token, token_type, userType, companyId, locationId, code, expire, date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE access_token=%s, refresh_token=%s, token_type=%s, userType=%s, companyId=%s, locationId=%s, expire=%s, date=NOW()
    """
    params = (
        token_data['access_token'], token_data['refresh_token'], token_data['token_type'], token_data['userType'], company_id, location_id, code, expire_timestamp,
        token_data['access_token'], token_data['refresh_token'], token_data['token_type'], token_data['userType'], company_id, location_id, expire_timestamp
    )
    
    try:
        cursor.execute(stmt, params)
        mysql.connection.commit()
        message = "Token data updated successfully."
        print('update')
    except Exception as e:
        mysql.connection.rollback()
        message = f"Database update error: {str(e)}"
    finally:
        cursor.close()
    
    return message
