# pokedex.py
from http.server import BaseHTTPRequestHandler
import urllib.parse
import random
import json
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

def get_pokemon_info(pokemon_name):
    """Get Pokemon info from Firestore"""
    try:
        doc = db.collection('pokemon_data').document(pokemon_name).get()
        if doc.exists:
            return doc.to_dict()
    except:
        pass
    return None

def get_random_pokemon():
    """Get a random Pokemon from Firestore"""
    try:
        # Get all Pokemon documents
        docs = db.collection('pokemon_data').limit(1000).get()
        if docs:
            # Pick a random one
            random_doc = random.choice(docs)
            return random_doc.id, random_doc.to_dict()
    except:
        pass
    return None, None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        
        # SECURITY: Check channel authorization
        channel = params.get('channel', [''])[0].lower()
        if channel != 'jennetdaria':
            self.send_response(403)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b"Unauthorized: This channel is not permitted to use this command.")
            return
        
        user = params.get('user', ['someone'])[0]
        pokemon_param = params.get('pokemon', [None])[0]
        uptime = params.get('uptime', [None])[0]
        user_level = params.get('user_level', [''])[0].lower()
        
        # Check if stream is offline
        is_offline = not uptime or uptime.lower() == 'offline'
        is_mod = user_level in ['owner', 'moderator']
        
        if is_offline:
            if is_mod:
                # Moderator can use pokedex offline
                try:
                    if pokemon_param:
                        # Specific Pokemon lookup
                        pokemon_name = pokemon_param.strip().title()
                        info = get_pokemon_info(pokemon_name)
                        
                        if info:
                            ptype = info.get('type', 'Unknown')
                            species = info.get('species', 'Unknown Pokemon')
                            entry = info.get('entry', 'No data available.')
                            
                            # Truncate entry for chat
                            if len(entry) > 200:
                                entry = entry[:197] + "..."
                            
                            # Get evolution info
                            evolution_chain = info.get('evolution', 'No evolution')
                            
                            response = f"📖 {pokemon_name} ({ptype}) - {species} | Evolution: {evolution_chain} | {entry} | {get_time_until_reset()}"
                        else:
                            response = f"@{user}, {pokemon_name} not found in the Pokedex! | {get_time_until_reset()}"
                    else:
                        # Random Pokemon fact
                        pokemon_name, info = get_random_pokemon()
                        
                        if info:
                            ptype = info.get('type', 'Unknown')
                            entry = info.get('entry', 'No data available.')
                            
                            # Truncate for random facts
                            if len(entry) > 150:
                                entry = entry[:147] + "..."
                            
                            response = f"📖 Random Pokemon: {pokemon_name} ({ptype}) - {entry} | {get_time_until_reset()}"
                        else:
                            response = f"Pokedex database error! | {get_time_until_reset()}"
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain; charset=utf-8')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(response.encode('utf-8'))
                    
                except Exception as e:
                    self.send_response(500)
                    self.send_header('Content-type', 'text/plain; charset=utf-8')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(f"Pokedex error!".encode('utf-8'))
            else:
                # Regular user offline message
                if pokemon_param:
                    response = f"@{user}, pokedex is currently offline. Please make sure to follow Jennet and come back when Jennet is live to learn about {pokemon_param}!"
                else:
                    response = f"@{user}, pokedex is currently offline. Please make sure to follow Jennet and come back when Jennet is live to learn about pokemon!"
                
                self.send_response(200)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response.encode('utf-8'))
        else:
            # ONLINE PLAY - Regular logic
            try:
                if pokemon_param:
                    # Specific Pokemon lookup
                    pokemon_name = pokemon_param.strip().title()
                    info = get_pokemon_info(pokemon_name)
                    
                    if info:
                        ptype = info.get('type', 'Unknown')
                        species = info.get('species', 'Unknown Pokemon')
                        entry = info.get('entry', 'No data available.')
                        
                        # Truncate entry for chat
                        if len(entry) > 200:
                            entry = entry[:197] + "..."
                        
                        # Get evolution info
                        evolution_chain = info.get('evolution', 'No evolution')
                        
                        response = f"📖 {pokemon_name} ({ptype}) - {species} | Evolution: {evolution_chain} | {entry}"
                    else:
                        response = f"@{user}, {pokemon_name} not found in the Pokedex!"
                else:
                    # Random Pokemon fact
                    pokemon_name, info = get_random_pokemon()
                    
                    if info:
                        ptype = info.get('type', 'Unknown')
                        entry = info.get('entry', 'No data available.')
                        
                        # Truncate for random facts
                        if len(entry) > 150:
                            entry = entry[:147] + "..."
                        
                        response = f"📖 Random Pokemon: {pokemon_name} ({ptype}) - {entry}"
                    else:
                        response = "Pokedex database error!"
                
                self.send_response(200)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response.encode('utf-8'))
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(f"Pokedex error!".encode('utf-8'))
