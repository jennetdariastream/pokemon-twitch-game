# pokeleaderclear.py
from http.server import BaseHTTPRequestHandler
import urllib.parse
import firebase_admin
from firebase_admin import credentials, firestore
import json
import os

if not firebase_admin._apps:
    cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_CREDS')))
    firebase_admin.initialize_app(cred)

db = firestore.client()

ALLOWED_USERS = ['jennetdaria', 'itssjonn']

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        
        # SECURITY: Check channel authorization first
        channel = params.get('channel', [''])[0].lower()
        if channel != 'jennetdaria':
            self.send_response(403)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b"Unauthorized: This channel is not permitted to use this command.")
            return
        
        user = params.get('user', [''])[0].lower()
        
        # Check if user is authorized
        if user not in ALLOWED_USERS:
            response = f"@{user}, you are not authorized to use this command!"
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(response.encode())
            return
        
        try:
            # Delete all leaderboard entries
            batch = db.batch()
            docs = db.collection('leaderboard').stream()
            count = 0
            for doc in docs:
                batch.delete(doc.reference)
                count += 1
            
            if count > 0:
                batch.commit()
                response = f"🔄 Pokemon leaderboard cleared and reset! {count} trainers removed."
            else:
                response = "Leaderboard was already empty!"
            
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(response.encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(f"Error clearing leaderboard!".encode())
