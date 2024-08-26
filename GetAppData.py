from flask import Blueprint, jsonify, redirect, current_app
from urllib.parse import urlencode

GetAppData = Blueprint('GetAppData', __name__)

def get_oauth_settings():
    """Retrieve OAuth settings from app config."""
    base_url = current_app.config.get('baseUrl')
    client_id = current_app.config.get('clientId')
    scope = current_app.config.get('scope', [])  # Default to empty list if scope is not set
    
    return base_url, client_id, scope

@GetAppData.route("/")
def get_app_data():
    """Redirects the user to the OAuth provider's authorization endpoint."""
    try:
        # Get OAuth settings from helper function
        base_url, client_id, scope = get_oauth_settings()
        redirect_uri = "http://127.0.0.1:8000/GetAccessToken/"  # Replace with your actual redirect URI

        # Check if required settings are missing
        if not base_url:
            return jsonify({"error": "BASE_URL is not configured in the application settings."}), 500

        if not client_id:
            return jsonify({"error": "CLIENT_ID is not configured in the application settings."}), 500

        if not scope:
            return jsonify({"error": "Scope is not configured in the application settings."}), 500
        
        # Construct OAuth redirect URL manually
        print(scope)
        scope_string = ' '.join(scope)  # Join scope list into a space-separated string
        print(scope_string)
        # Properly encode query parameters
        query_params = {
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "scope": scope_string
        }
        query_string = urlencode(query_params)
        
        redirect_url = f"{base_url}/oauth/chooselocation?{query_string}"

        # Redirect user to the constructed URL
        return redirect(redirect_url)

    except Exception as e:
        # Handle unexpected exceptions
        return jsonify({"error": "An unexpected error occurred. Please try again later."}), 500
