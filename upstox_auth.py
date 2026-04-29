"""
Upstox Auto Token Manager
Handles token generation, refresh, and persistence
"""

import requests
import json
import time
import logging
from datetime import datetime, timedelta
from threading import Thread

log = logging.getLogger("waveedge")

class UpstoxAuth:
    def __init__(self, api_key, api_secret, redirect_uri, token_file="upstox_token.json"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.redirect_uri = redirect_uri
        self.token_file = token_file
        self.access_token = None
        self.token_expiry = None
        self._load_token()

    def _load_token(self):
        """Load token from file"""
        try:
            with open(self.token_file, 'r') as f:
                data = json.load(f)
                self.access_token = data.get('access_token')
                if data.get('expires_at'):
                    self.token_expiry = datetime.fromisoformat(data['expires_at'])
                log.info(f"Token loaded, expires: {self.token_expiry}")
        except:
            log.info("No existing token found")

    def _save_token(self):
        """Save token to file"""
        data = {
            'access_token': self.access_token,
            'expires_at': self.token_expiry.isoformat() if self.token_expiry else None
        }
        with open(self.token_file, 'w') as f:
            json.dump(data, f)

    def is_valid(self):
        """Check if token is valid and not expired"""
        if not self.access_token or not self.token_expiry:
            return False
        # Refresh 1 hour before expiry
        return datetime.now() < (self.token_expiry - timedelta(hours=1))

    def generate_token(self, authorization_code):
        """Generate token using authorization code"""
        url = "https://api.upstox.com/v2/login/authorization/token"
        payload = {
            "code": authorization_code,
            "client_id": self.api_key,
            "client_secret": self.api_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code"
        }
        response = requests.post(url, data=payload, timeout=15)
        if response.status_code == 200:
            data = response.json()
            self.access_token = data['access_token']
            self.token_expiry = datetime.now() + timedelta(days=1)
            self._save_token()
            log.info("✅ Token generated and saved")
            return True, None
        return False, f"HTTP {response.status_code}: {response.text}"

    def refresh_token(self):
        """Refresh expired token"""
        if not self.is_valid():
            log.warning("Token expired or invalid. Please re-authenticate.")
            return False
        return True

    def get_token(self):
        """Return current token if valid"""
        if self.is_valid():
            return self.access_token
        return None
