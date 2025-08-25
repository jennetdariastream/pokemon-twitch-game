# poketrain.py
from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import random
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

def check_evolution(pokemon_name, old_level, new_level):
    """Check if Pokemon can evolve and return evolution if applicable"""
    try:
        doc = db.collection('pokemon_data').document(pokemon_name).get()
        if doc.exists:
            poke_data = doc.to_dict()
            if poke_data.get('can_evolve', False):
                evolution = poke_data.get('evolves_to')
                evo_level = poke_data.get('min_level_to_evolve')
                if evolution and evo_level and old_level < evo_level <= new_level:
                    return evolution
    except:
        pass
    return None

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
                # Moderator offline play - daily training
                utc_now = datetime.now(timezone.utc)
                daily_id = f"mod_daily_{utc_now.strftime('%Y%m%d')}"
                
                try:
                    # Get user's Pokemon from mod_daily
                    catch_ref = db.collection('mod_daily').document(daily_id).collection('users').document(user)
                    catch_doc = catch_ref.get()
                    
                    if not catch_doc.exists:
                        response = f"@{user}, you need to !pokecatch before training! | {get_time_until_reset()}"
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
                    
                    # Check daily training limit
                    if training_used >= 2:
                        response = f"@{user}, you've already trained twice today! Your team: {', '.join([f'{p} (Lv.{l})' for p, l in zip(pokemon_list, levels)])} | {get_time_until_reset()}"
                        self.send_response(200)
                        self.send_header('Content-type', 'text/plain')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(response.encode())
                        return
                    
                    # Train all Pokemon
                    evolutions = []
                    level_gains_display = []
                    
                    for i in range(len(pokemon_list)):
                        old_level = levels[i]
                        level_gain = random.randint(3, 8)
                        new_level = min(old_level + level_gain, 100)
                        levels[i] = new_level
                        level_gains_display.append(f"+{level_gain}")
                        
                        # Check for evolution using Firestore
                        pokemon_name = pokemon_list[i]
                        evolution = check_evolution(pokemon_name, old_level, new_level)
                        if evolution:
                            pokemon_list[i] = evolution
                            evolutions.append(f"{pokemon_name} evolved into {evolution}!")
                    
                    # Update database (mod_daily)
                    data['pokemon'] = pokemon_list
                    data['levels'] = levels
                    data['training_used'] = training_used + 1
                    catch_ref.set(data)
                    
                    # Format response with countdown
                    trainings_left = 2 - (training_used + 1)
                    
                    if evolutions:
                        response = f"@{user} trained! {' '.join(evolutions)} ({trainings_left} training sessions left) | {get_time_until_reset()}"
                    else:
                        response = f"@{user}'s Pokemon gained levels: {', '.join(level_gains_display)}! ({trainings_left} training sessions left) | {get_time_until_reset()}"
                    
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
                    self.wfile.write(f"Error training Pokemon!".encode())
            else:
                # Regular user offline message
                response = f"@{user}, you cannot train pokemon while Jennet is offline. Please make sure to follow Jennet and come back when Jennet is live to catch, train, and battle pokemon!"
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response.encode())
            return
        
        # ONLINE PLAY - Regular stream logic
        stream_id = hashlib.md5(f"{channel}_{uptime}".encode()).hexdigest()
        
        try:
            # Get user's Pokemon
            catch_ref = db.collection('catches').document(stream_id).collection('users').document(user)
            catch_doc = catch_ref.get()
            
            if not catch_doc.exists:
                response = f"@{user}, you need to !pokecatch before training!"
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
            
            # Check training limit (2 per stream)
            if training_used >= 2:
                response = f"@{user}, you've already trained twice this stream! Your team: {', '.join([f'{p} (Lv.{l})' for p, l in zip(pokemon_list, levels)])}"
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response.encode())
                return
            
            # Train all Pokemon
            evolutions = []
            level_gains_display = []
            
            for i in range(len(pokemon_list)):
                old_level = levels[i]
                level_gain = random.randint(3, 8)
                new_level = min(old_level + level_gain, 100)
                levels[i] = new_level
                level_gains_display.append(f"+{level_gain}")
                
                # Check for evolution using Firestore
                pokemon_name = pokemon_list[i]
                evolution = check_evolution(pokemon_name, old_level, new_level)
                if evolution:
                    pokemon_list[i] = evolution
                    evolutions.append(f"{pokemon_name} evolved into {evolution}!")
            
            # Update database
            data['pokemon'] = pokemon_list
            data['levels'] = levels
            data['training_used'] = training_used + 1
            catch_ref.set(data)
            
            # Format response
            trainings_left = 2 - (training_used + 1)
            
            if evolutions:
                response = f"@{user} trained! {' '.join(evolutions)} ({trainings_left} training sessions left)"
            else:
                response = f"@{user}'s Pokemon gained levels: {', '.join(level_gains_display)}! ({trainings_left} training sessions left)"
            
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
            self.wfile.write(f"Error training Pokemon!".encode())
