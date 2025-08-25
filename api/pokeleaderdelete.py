# pokeleaderdelete.py
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
        target = params.get('target', [None])[0]
        
        # Check if user is authorized
        if user not in ALLOWED_USERS:
            response = f"@{user}, you are not authorized to use this command!"
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(response.encode())
            return
        
        if not target:
            response = "Please specify a user to remove: !pokeleaderdelete @username"
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(response.encode())
            return
        
        target = target.lower().replace('@', '')
        
        try:
            # Get the user's record before deleting
            doc_ref = db.collection('leaderboard').document(target)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                wins = data.get('total_wins', 0)
                losses = data.get('total_losses', 0)
                
                # Delete the document
                doc_ref.delete()
                response = f"✅ @{target} has been removed from the leaderboard (was {wins}W-{losses}L)"
            else:
                response = f"@{target} was not found on the leaderboard"
            
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
            self.wfile.write(f"Error removing user!".encode())
