from flask import Blueprint, request, jsonify, current_app
import requests
import time
from flask_mysqldb import MySQL

# Initialize MySQL object
mysql = MySQL()

get_access_token = Blueprint('get_accesstoken', __name__)

def get_oauth_settings():
    """Retrieve OAuth settings from app config."""
    base_url = current_app.config.get('baseUrl')
    client_id = current_app.config.get('clientId')
    client_secret = current_app.config.get('clientSecret')
    user_type = current_app.config.get('userType')
    
    return base_url, client_id, client_secret, user_type

@get_access_token.route("/", methods=['GET'])
def get_access_token_route():
    """
    Handles the callback from the OAuth provider to exchange authorization code for an access token.
    """
    base_url, client_id, client_secret, user_type = get_oauth_settings()
    
    if not client_id or not client_secret:
        return jsonify({"error": "CLIENT_ID or CLIENT_SECRET not configured in settings"}), 500
    
    code = request.args.get('code')
    if not code:
        return jsonify({"error": "Authorization code is required"}), 400
    
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "user_type": user_type if user_type else "Location"
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }
    
    try:
        # Request the access token from OAuth provider
        response = requests.post("https://services.leadconnectorhq.com/oauth/token", data=payload, headers=headers)
        response.raise_for_status()  # Raise HTTPError for bad responses
        
        # Parse the access token response
        access_token_data = response.json()
        access_token = access_token_data.get('access_token')
        refresh_token = access_token_data.get('refresh_token')
        expires_in = access_token_data.get('expires_in')
        token_type = access_token_data.get('token_type')
        user_type = access_token_data.get('userType')
        company_id = access_token_data.get('companyId')
        location_id = access_token_data.get('locationId', '')
        user_id = access_token_data.get('userId')
        
        expire_timestamp = int(time.time()) + int(expires_in)
        
        # Manage database cursor
        cursor = mysql.connection.cursor()
        
        try:
            if user_type == "Location":
                cursor.execute("SELECT `locationId`, `expire` FROM `token` WHERE `locationId` = %s", (location_id,))
            else:
                cursor.execute("SELECT `companyId`, `expire` FROM `token` WHERE `companyId` = %s AND (`locationId` IS NULL OR `locationId` = '')", (company_id,))
            
            result = cursor.fetchone()
            
            if result:
                if user_type == "Location":
                    cursor.execute("""
                        UPDATE `token`
                        SET `access_token`=%s, `refresh_token`=%s, `token_type`=%s, `userType`=%s, `companyId`=%s, `locationId`=%s, `code`=%s, `expire`=%s, `date`=NOW()
                        WHERE `locationId`=%s
                    """, (access_token, refresh_token, token_type, user_type, company_id, location_id, code, expire_timestamp, location_id))
                else:
                    cursor.execute("""
                        UPDATE `token`
                        SET `access_token`=%s, `refresh_token`=%s, `token_type`=%s, `userType`=%s, `companyId`=%s, `locationId`=%s, `code`=%s, `expire`=%s, `date`=NOW()
                        WHERE `companyId`=%s AND (`locationId` IS NULL OR `locationId` = '')
                    """, (access_token, refresh_token, token_type, user_type, company_id, location_id, code, expire_timestamp, company_id))
                message = "Token updated successfully."
            else:
                cursor.execute("""
                    INSERT INTO `token` (`access_token`, `refresh_token`, `token_type`, `userType`, `companyId`, `locationId`, `code`, `expire`, `date`)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, (access_token, refresh_token, token_type, user_type, company_id, location_id, code, expire_timestamp))
                message = "Token inserted successfully."
            
            mysql.connection.commit()
        
        except Exception as e:
            mysql.connection.rollback()
            return jsonify({"error": f"Database error: {str(e)}"}), 500
        
        finally:
            cursor.close()
        
        return jsonify({
            "message": message,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
            "token_type": token_type,
            "user_type": user_type,
            "company_id": company_id,
            "location_id": location_id,
            "user_id": user_id
        })
    
    except requests.exceptions.HTTPError as e:
        return jsonify({"error": f"HTTP error: {str(e)}", "response": response.text}), 500
    
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Request error: {str(e)}"}), 500
    
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500
