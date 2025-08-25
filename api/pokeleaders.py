# pokeleaders.py
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

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # pokeleaders works for everyone but only in jennetdaria channel
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        
        channel = params.get('channel', [''])[0].lower()
        if channel != 'jennetdaria':
            self.send_response(403)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b"Unauthorized: This channel is not permitted to use this command.")
            return
        
        try:
            # Get all leaderboard entries
            leaderboard_docs = db.collection('leaderboard').stream()
            
            all_trainers = []
            for doc in leaderboard_docs:
                data = doc.to_dict()
                total_battles = data.get('total_battles', 0)
                total_wins = data.get('total_wins', 0)
                total_losses = data.get('total_losses', 0)
                
                if total_battles >= 5:  # Minimum 5 battles to qualify
                    win_rate = total_wins / total_battles if total_battles > 0 else 0
                    all_trainers.append({
                        'name': doc.id,
                        'wins': total_wins,
                        'losses': total_losses,
                        'battles': total_battles,
                        'win_rate': win_rate
                    })
            
            if not all_trainers:
                response = "🏆 No trainers on the leaderboard yet! Get battling!"
            else:
                # Sort by total wins first, then by win rate as tiebreaker
                all_trainers.sort(key=lambda x: (x['wins'], x['win_rate']), reverse=True)
                
                # Format top 5 with proper ranking (accounting for ties)
                leaders = []
                current_rank = 1
                prev_wins = None
                prev_rate = None
                
                for i, trainer in enumerate(all_trainers[:10]):  # Get more to ensure we have 5 displayed
                    # Determine actual rank (accounting for ties)
                    if prev_wins != trainer['wins'] or prev_rate != trainer['win_rate']:
                        current_rank = i + 1
                    
                    # Only show top 5 ranks
                    if current_rank <= 5:
                        win_pct = int(trainer['win_rate'] * 100)
                        leaders.append(f"{current_rank}. {trainer['name']} ({trainer['wins']}W-{trainer['losses']}L, {win_pct}%)")
                    
                    prev_wins = trainer['wins']
                    prev_rate = trainer['win_rate']
                    
                    # Stop after we have 5 entries
                    if len(leaders) >= 5:
                        break
                
                response = "🏆 TOP TRAINERS: " + " | ".join(leaders)
            
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
            self.wfile.write(f"Error loading leaderboard!".encode())
