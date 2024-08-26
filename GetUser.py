from flask import Blueprint, request, jsonify, send_file
import requests
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
from openpyxl import Workbook
import os
import tempfile
from GetRefreshToken import get_expired_tokens, update_token_in_db, refresh_access_token, get_oauth_settings
from flask_mysqldb import MySQL

mysql = MySQL()
get_User = Blueprint('get_User', __name__)

# Configuration
company_id = "c4s6hoT5HnWnXXVZnC0E"
app_id = "66bc598205ef16d5f8f4e9a2"

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def fetch_with_retry(url, method='GET', headers=None, data=None, max_retries=5, backoff_factor=1.0, timeout=100):
    """Fetch a URL with retry logic."""
    for attempt in range(max_retries):
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, headers=headers, data=data, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.HTTPError as e:
            if response.status_code == 429:
                wait_time = backoff_factor * (2 ** attempt) + random.uniform(0, 1)
                logging.warning(f"Rate limit exceeded. Waiting for {wait_time:.2f} seconds...")
                time.sleep(wait_time)
            else:
                logging.error(f"Request failed: {e}")
                raise
        except requests.RequestException as e:
            logging.error(f"Request failed: {e}")
            if attempt == max_retries - 1:
                raise
            else:
                time.sleep(backoff_factor * (2 ** attempt))  # Exponential backoff
    logging.error("Max retries exceeded")
    raise Exception("Max retries exceeded")

def get_locations(token, company_id, app_id):
    """Fetch locations from the API."""
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
        'Version': '2021-07-28'
    }
    url = f'https://services.leadconnectorhq.com/oauth/installedLocations?companyId={company_id}&appId={app_id}&limit=500'
    try:
        logging.info(f"Fetching locations for company_id {company_id} and app_id {app_id}")
        response = fetch_with_retry(url, 'GET', headers)
        response_data = response.json()
        if 'locations' in response_data:
            return [loc['_id'] for loc in response_data['locations']]
        else:
            logging.warning("No locations found in response")
            return []
    except Exception as e:
        logging.error(f"Failed to fetch locations: {e}")
        raise

def get_location_access_token(token, company_id, location_id):
    """Fetch the access token for a specific location."""
    data = {
        'companyId': company_id,
        'locationId': location_id
    }
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Version': '2021-07-28'
    }
    url = 'https://services.leadconnectorhq.com/oauth/locationToken'
    try:
        logging.info(f"Fetching location access token for location_id {location_id}")
        response = fetch_with_retry(url, 'POST', headers, data)
        response_data = response.json()
        return {
            'locationId': response_data.get('locationId'),
            'access_token': response_data.get('access_token')
        }
    except Exception as e:
        logging.error(f"Failed to fetch location access token: {e}")
        raise

def get_locations_users(token, location_id):
    """Fetch users for a specific location."""
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
        'Version': '2021-07-28'
    }
    url = f'https://services.leadconnectorhq.com/users/?locationId={location_id}'
    try:
        logging.info(f"Fetching users for location_id {location_id}")
        response = fetch_with_retry(url, 'GET', headers)
        response_data = response.json()
        if 'users' in response_data:
            return response_data['users']
        else:
            logging.warning(f"No users found for location_id {location_id}")
            return []
    except Exception as e:
        logging.error(f"Failed to fetch users: {e}")
        raise

def save_data_to_excel(data, filename):
    """Save user data to an Excel file."""
    try:
        wb = Workbook()
        ws = wb.active
        ws.title = "User Data"

        headers = ['Name', 'Phone', 'Email', 'ID', 'Role', 'Location']
        ws.append(headers)

        for user in data:
            row = [
                user.get('name', ''),
                user.get('phone', ''),
                user.get('email', ''),
                user.get('id', ''),
                ', '.join(user.get('role', [])),
                ', '.join(user.get('locationIds', []))
            ]
            ws.append(row)

        wb.save(filename)
        logging.info(f"Data saved to '{filename}' successfully.")
    except Exception as e:
        logging.error(f"Error saving Excel file: {e}")

def refresh_tokens():
    """Handle token refresh logic."""
    base_url, client_id, client_secret, user_type = get_oauth_settings()

    expired_tokens = get_expired_tokens()
    if not expired_tokens:
        logging.info("No expired tokens to refresh.")
        return

    for token in expired_tokens:
        access_token, refresh_token, token_type, userType, companyId, locationId, code, expire = token
        try:
            new_token_data = refresh_access_token(client_id, client_secret, refresh_token, userType, code)
            expires_in = new_token_data.get('expires_in', 3600)  # Default to 1 hour if not provided
            expire_timestamp = int(time.time()) + int(expires_in)
            update_token_in_db(new_token_data, code, expire_timestamp)
            logging.info(f"Token refreshed successfully for {userType} with ID {companyId or locationId}.")
        except Exception as e:
            logging.error(f"Error refreshing token: {e}")

@get_User.route("/users", methods=['GET'])
def get_all_users():
    """Fetch and return all users, save to Excel, and send the file."""
    try:
        # Refresh tokens before proceeding
        refresh_tokens()

        # Fetch the access token (possibly refreshed)
        cursor = mysql.connection.cursor()
        try:
            cursor.execute("SELECT access_token FROM token WHERE companyId=%s", [company_id])
            access_token_data = cursor.fetchone()
            if access_token_data:
                access_token = access_token_data[0]
            else:
                logging.error("No access token found in the database.")
                return jsonify({'error': 'No access token available'}), 500
        except Exception as db_error:
            logging.error(f"Database error: {db_error}")
            return jsonify({'error': 'Database error'}), 500
        finally:
            cursor.close()

        with ThreadPoolExecutor(max_workers=10) as executor:
            location_ids = get_locations(access_token, company_id, app_id)

            all_user_data = []
            location_key_futures = {
                executor.submit(get_location_access_token, access_token, company_id, location_id): location_id
                for location_id in location_ids
            }

            for future in as_completed(location_key_futures):
                location_id = location_key_futures[future]
                try:
                    location_key = future.result()
                    if location_key:
                        token = location_key['access_token']
                        user_data_future = executor.submit(get_locations_users, token, location_id)
                        user_data = user_data_future.result()

                        for user in user_data:
                            filtered_user = {
                                'id': user.get('id'),
                                'name': user.get('name'),
                                'phone': user.get('phone'),
                                'email': user.get('email'),
                                'role': user.get('roles', {}).get('role', []),
                                'locationIds': user.get('roles', {}).get('locationIds', [])
                            }

                            all_user_data.append(filtered_user)
                except Exception as e:
                    logging.error(f"Error retrieving data for location_id {location_id}: {e}")

        # Use a temporary file to handle the Excel data
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            excel_filename = tmp_file.name
            save_data_to_excel(all_user_data, excel_filename)

        # Serve the file and clean up in a separate thread
        response = send_file(excel_filename, as_attachment=True)

        def remove_file_after_send():
            time.sleep(2)  # Allow time for the file to be sent
            try:
                os.remove(excel_filename)
                logging.info(f"File '{excel_filename}' removed successfully.")
            except OSError as e:
                logging.error(f"Error removing file '{excel_filename}': {e}")

        import threading
        threading.Thread(target=remove_file_after_send).start()
        return response

    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({'error': str(e)}), 500
