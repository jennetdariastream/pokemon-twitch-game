# mypokemon.py
from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import hashlib
import firebase_admin
from firebase_admin import credentials, firestore
import os
from datetime import datetime, timezone, timedelta

if not firebase_admin._apps:
    cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_CREDS')))
    firebase_admin.initialize_app(cred)

db = firestore.client()

def get_time_until_reset():
    """Calculate time until 12am UTC"""
    utc_now = datetime.now(timezone.utc)
    tomorrow = utc_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    time_until = tomorrow - utc_now
    hours = int(time_until.total_seconds() // 3600)
    minutes = int((time_until.total_seconds() % 3600) // 60)
    seconds = int(time_until.total_seconds() % 60)
    return f"GAME RESETS IN {hours} HRS, {minutes} MINS, {seconds} SECS"

def get_pokemon_type(pokemon_name):
    """Get Pokemon type from Firestore"""
    try:
        doc = db.collection('pokemon_data').document(pokemon_name).get()
        if doc.exists:
            return doc.to_dict().get('type', 'Unknown')
        return 'Unknown'
    except:
        return 'Unknown'

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
        
        user = params.get('user', ['someone'])[0].lower()
        uptime = params.get('uptime', [None])[0]
        user_level = params.get('user_level', [''])[0].lower()
        
        # Check if stream is online
        if not uptime or uptime == 'offline':
            # Check if user is a moderator
            if user_level in ['owner', 'moderator']:
                # Moderator offline play - show daily team
                utc_now = datetime.now(timezone.utc)
                daily_id = f"mod_daily_{utc_now.strftime('%Y%m%d')}"
                
                try:
                    # Get mod's daily Pokemon
                    catch_doc = db.collection('mod_daily').document(daily_id).collection('users').document(user).get()
                    
                    if not catch_doc.exists:
                        response = f"@{user}, you haven't caught any Pokemon today! Use !pokecatch to get started! | {get_time_until_reset()}"
                        self.send_response(200)
                        self.send_header('Content-type', 'text/plain')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(response.encode())
                        return
                    
                    data = catch_doc.to_dict()
                    pokemon_list = data.get('pokemon', [])
                    levels = data.get('levels', [])
                    training_used = data.get('training_used', 0)
                    
                    # Get daily battle record
                    battle_doc = db.collection('mod_daily_battles').document(daily_id).collection('users').document(user).get()
                    
                    if battle_doc.exists:
                        battle_data = battle_doc.to_dict()
                        wins = battle_data.get('wins', 0)
                        losses = battle_data.get('losses', 0)
                        battles_done = battle_data.get('battles', 0)
                    else:
                        wins = losses = battles_done = 0
                    
                    # Calculate remaining
                    battles_left = 2 - battles_done
                    training_left = 2 - training_used
                    
                    # Format Pokemon with types and levels - get types from Firestore
                    pokemon_with_info = []
                    for p, l in zip(pokemon_list, levels):
                        ptype = get_pokemon_type(p)
                        pokemon_with_info.append(f"{p} ({ptype}, Lv.{l})")
                    
                    response = f"@{user}'s team: {', '.join(pokemon_with_info)} | Record: {wins}W-{losses}L | Battles left: {battles_left} | Training left: {training_left} | {get_time_until_reset()}"
                    
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
                    self.wfile.write(f"Error retrieving Pokemon!".encode())
            else:
                # Regular user offline - always show same message
                response = f"@{user}, you cannot view Pokemon while Jennet is offline. Please make sure to follow Jennet and come back when Jennet is live to view your Pokemon!"
                
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response.encode())
            return
        
        # ONLINE PLAY - Regular stream logic
        stream_id = hashlib.md5(f"{channel}_{uptime}".encode()).hexdigest()
        
        try:
            # Get user's Pokemon for current stream
            catch_doc = db.collection('catches').document(stream_id).collection('users').document(user).get()
            
            if not catch_doc.exists:
                response = f"@{user}, you haven't caught any Pokemon this stream! Use !pokecatch to get started!"
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response.encode())
                return
            
            data = catch_doc.to_dict()
            pokemon_list = data.get('pokemon', [])
            levels = data.get('levels', [])
            training_used = data.get('training_used', 0)
            
            # Get battle record for this stream
            battle_doc = db.collection('stream_battles').document(stream_id).collection('users').document(user).get()
            
            if battle_doc.exists:
                battle_data = battle_doc.to_dict()
                wins = battle_data.get('wins', 0)
                losses = battle_data.get('losses', 0)
                battles_done = battle_data.get('battles', 0)
            else:
                wins = losses = battles_done = 0
            
            # Calculate remaining
            battles_left = 2 - battles_done
            training_left = 2 - training_used
            
            # Format Pokemon with types and levels - get types from Firestore
            pokemon_with_info = []
            for p, l in zip(pokemon_list, levels):
                ptype = get_pokemon_type(p)
                pokemon_with_info.append(f"{p} ({ptype}, Lv.{l})")
            
            response = f"@{user}'s team: {', '.join(pokemon_with_info)} | Record: {wins}W-{losses}L | Battles left: {battles_left} | Training left: {training_left}"
            
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
            self.wfile.write(f"Error retrieving Pokemon!".encode())
