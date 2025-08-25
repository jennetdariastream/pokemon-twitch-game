# pokelegends.py
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
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        
        # SECURITY: Check channel authorization
        channel = params.get('channel', [''])[0].lower()
        if channel != 'jennetdaria':
            self.send_response(403)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b"Unauthorized: This channel is not permitted to use this command.")
            return
        
        try:
            # Get all entries from the permanent legends collection
            legends_docs = db.collection('legends').stream()
            
            all_legends = []
            for doc in legends_docs:
                data = doc.to_dict()
                total_battles = data.get('total_battles', 0)
                total_wins = data.get('total_wins', 0)
                total_losses = data.get('total_losses', 0)
                
                if total_battles >= 10:  # Higher threshold for legends (10 battles minimum)
                    win_rate = total_wins / total_battles if total_battles > 0 else 0
                    all_legends.append({
                        'name': doc.id,
                        'wins': total_wins,
                        'losses': total_losses,
                        'battles': total_battles,
                        'win_rate': win_rate
                    })
            
            if not all_legends:
                response = "⭐ LEGENDS HALL OF FAME: No legendary trainers yet! Battle more to become a legend!"
            else:
                # Sort by total wins first, then by win rate as tiebreaker
                all_legends.sort(key=lambda x: (x['wins'], x['win_rate']), reverse=True)
                
                # Format top 5 with proper ranking (accounting for ties)
                legends = []
                current_rank = 1
                prev_wins = None
                prev_rate = None
                
                for i, trainer in enumerate(all_legends[:10]):  # Get more to ensure we have 5 displayed
                    # Determine actual rank (accounting for ties)
                    if prev_wins != trainer['wins'] or prev_rate != trainer['win_rate']:
                        current_rank = i + 1
                    
                    # Only show top 5 ranks
                    if current_rank <= 5:
                        win_pct = int(trainer['win_rate'] * 100)
                        
                        # Add special emojis for top 3 actual ranks
                        if current_rank == 1:
                            emoji = "👑"
                        elif current_rank == 2:
                            emoji = "🥈"
                        elif current_rank == 3:
                            emoji = "🥉"
                        else:
                            emoji = f"{current_rank}."
                        
                        legends.append(f"{emoji} {trainer['name']} ({trainer['wins']}W-{trainer['losses']}L, {win_pct}%)")
                    
                    prev_wins = trainer['wins']
                    prev_rate = trainer['win_rate']
                    
                    # Stop after we have 5 entries
                    if len(legends) >= 5:
                        break
                
                response = "⭐ LEGENDS HALL OF FAME: " + " | ".join(legends)
            
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
            self.wfile.write(f"Error loading legends!".encode())
