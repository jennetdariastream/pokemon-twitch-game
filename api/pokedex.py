# pokedex.py
from http.server import BaseHTTPRequestHandler
import urllib.parse
import random
from datetime import datetime, timezone, timedelta
from pokemon_data import POKEMON_DATA

def get_time_until_reset():
    """Calculate time until 12am UTC"""
    utc_now = datetime.now(timezone.utc)
    tomorrow = utc_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    time_until = tomorrow - utc_now
    hours = int(time_until.total_seconds() // 3600)
    minutes = int((time_until.total_seconds() % 3600) // 60)
    seconds = int(time_until.total_seconds() % 60)
    return f"GAME RESETS IN {hours} HRS, {minutes} MINS, {seconds} SECS"

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
        
        user = params.get('user', ['someone'])[0]
        pokemon_param = params.get('pokemon', [None])[0]
        uptime = params.get('uptime', [None])[0]
        user_level = params.get('user_level', [''])[0].lower()
        
        # Check if stream is offline
        if not uptime or uptime == 'offline':
            # Check if user is a moderator
            if user_level in ['owner', 'moderator']:
                # Moderator can use pokedex offline
                try:
                    if pokemon_param:
                        # Specific Pokemon lookup
                        pokemon_name = pokemon_param.lower().capitalize()
                        
                        if pokemon_name in POKEMON_DATA:
                            info = POKEMON_DATA[pokemon_name]
                            ptype = info.get('type', 'Unknown')
                            species = info.get('species', 'Unknown Pokemon')
                            entry = info.get('entry', 'No data available.')  # FIXED: using 'entry' instead of 'pokedex_entry'
                            
                            # Truncate entry for chat
                            if len(entry) > 200:
                                entry = entry[:197] + "..."
                            
                            # Get evolution info - FIXED: using 'evolution' field
                            evolution_chain = info.get('evolution', 'No evolution')
                            
                            response = f"📖 {pokemon_name} ({ptype}) - {species} | Evolution: {evolution_chain} | {entry} | {get_time_until_reset()}"
                        else:
                            response = f"@{user}, {pokemon_name} not found in the Pokedex! | {get_time_until_reset()}"
                    else:
                        # Random Pokemon fact
                        pokemon_name = random.choice(list(POKEMON_DATA.keys()))
                        info = POKEMON_DATA[pokemon_name]
                        ptype = info.get('type', 'Unknown')
                        entry = info.get('entry', 'No data available.')  # FIXED: using 'entry'
                        
                        # Truncate for random facts
                        if len(entry) > 150:
                            entry = entry[:147] + "..."
                        
                        response = f"📖 Random Pokemon: {pokemon_name} ({ptype}) - {entry} | {get_time_until_reset()}"
                    
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
                    self.wfile.write(f"Pokedex error!".encode())
            else:
                # Regular user offline message
                if pokemon_param:
                    response = f"@{user}, pokedex is currently offline. Please make sure to follow Jennet and come back when Jennet is live to learn about {pokemon_param}!"
                else:
                    response = f"@{user}, pokedex is currently offline. Please make sure to follow Jennet and come back when Jennet is live to learn about pokemon!"
                
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response.encode())
            return
        
        # ONLINE PLAY - Regular logic
        try:
            if pokemon_param:
                # Specific Pokemon lookup
                pokemon_name = pokemon_param.lower().capitalize()
                
                if pokemon_name in POKEMON_DATA:
                    info = POKEMON_DATA[pokemon_name]
                    ptype = info.get('type', 'Unknown')
                    species = info.get('species', 'Unknown Pokemon')
                    entry = info.get('entry', 'No data available.')  # FIXED: using 'entry'
                    
                    # Truncate entry for chat
                    if len(entry) > 200:
                        entry = entry[:197] + "..."
                    
                    # Get evolution info - FIXED: using 'evolution' field
                    evolution_chain = info.get('evolution', 'No evolution')
                    
                    response = f"📖 {pokemon_name} ({ptype}) - {species} | Evolution: {evolution_chain} | {entry}"
                else:
                    response = f"@{user}, {pokemon_name} not found in the Pokedex!"
            else:
                # Random Pokemon fact
                pokemon_name = random.choice(list(POKEMON_DATA.keys()))
                info = POKEMON_DATA[pokemon_name]
                ptype = info.get('type', 'Unknown')
                entry = info.get('entry', 'No data available.')  # FIXED: using 'entry'
                
                # Truncate for random facts
                if len(entry) > 150:
                    entry = entry[:147] + "..."
                
                response = f"📖 Random Pokemon: {pokemon_name} ({ptype}) - {entry}"
            
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
            self.wfile.write(f"Pokedex error!".encode())
