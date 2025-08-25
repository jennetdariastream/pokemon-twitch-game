# pokecatch.py
from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import random
import hashlib
import os
from datetime import datetime, timezone, timedelta

import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_CREDS')))
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Cache for Pokemon data
POKEMON_CACHE = {}
LEGENDARIES_CACHE = []
CACHE_LOADED = False

def load_pokemon_data():
    """Load Pokemon data from Firestore into cache"""
    global POKEMON_CACHE, LEGENDARIES_CACHE, CACHE_LOADED
    
    if CACHE_LOADED:
        return True
    
    try:
        # Load legendary list
        legends_doc = db.collection('game_config').document('legendaries').get()
        if legends_doc.exists:
            LEGENDARIES_CACHE = legends_doc.to_dict().get('list', [])
        
        # Load all Pokemon data
        pokemon_docs = db.collection('pokemon_data').stream()
        for doc in pokemon_docs:
            POKEMON_CACHE[doc.id] = doc.to_dict()
        
        CACHE_LOADED = True
        return True
    except:
        return False

def get_time_until_reset():
    """Calculate time until 12am UTC"""
    utc_now = datetime.now(timezone.utc)
    tomorrow = utc_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    time_until = tomorrow - utc_now
    hours = int(time_until.total_seconds() // 3600)
    minutes = int((time_until.total_seconds() % 3600) // 60)
    seconds = int(time_until.total_seconds() % 60)
    return f"GAME RESETS IN {hours} HRS, {minutes} MINS, {seconds} SECS"

def catch_pokemon():
    """Generate 5 random Pokemon with levels"""
    caught = []
    levels = []
    
    all_pokemon = list(POKEMON_CACHE.keys())
    non_legendaries = [p for p in all_pokemon if p not in LEGENDARIES_CACHE]
    
    for _ in range(5):
        if LEGENDARIES_CACHE and random.random() < 0.03:  # 3% legendary chance
            pokemon = random.choice(LEGENDARIES_CACHE)
            level = random.randint(40, 50)
        else:
            pokemon = random.choice(non_legendaries if non_legendaries else all_pokemon)
            poke_info = POKEMON_CACHE.get(pokemon, {})
            min_level = poke_info.get('catch_level_min', 5)
            max_level = poke_info.get('catch_level_max', 45)
            level = random.randint(min_level, max_level)
        
        caught.append(pokemon)
        levels.append(level)
    
    return caught, levels

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
        
        # Load Pokemon data from Firestore
        if not load_pokemon_data():
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b"Error: Could not load Pokemon data from database.")
            return
        
        user = params.get('user', ['someone'])[0].lower()
        uptime = params.get('uptime', [None])[0]
        user_level = params.get('user_level', [''])[0].lower()
        
        # Check if stream is online
        if not uptime or uptime == 'offline':
            # Check if user is a moderator
            if user_level in ['owner', 'moderator']:
                # Moderator offline play - daily limit
                utc_now = datetime.now(timezone.utc)
                daily_id = f"mod_daily_{utc_now.strftime('%Y%m%d')}"
                
                try:
                    catch_ref = db.collection('mod_daily').document(daily_id).collection('users').document(user)
                    catch_doc = catch_ref.get()
                    
                    if catch_doc.exists:
                        data = catch_doc.to_dict()
                        catch_count = data.get('catch_count', 1)
                        
                        if catch_count == 1:
                            # First catch done, do re-roll
                            caught, levels = catch_pokemon()
                            
                            catch_ref.update({
                                'pokemon': caught,
                                'levels': levels,
                                'catch_count': 2,
                                'caught_at': firestore.SERVER_TIMESTAMP
                            })
                            
                            pokemon_with_levels = [f"{p} (Lv.{l})" for p, l in zip(caught, levels)]
                            response = f"@{user} RE-ROLLED and caught: {', '.join(pokemon_with_levels)}! (2/2 catches used - no more re-rolls today) | {get_time_until_reset()}"
                        else:
                            # Already used both catches
                            pokemon_list = data.get('pokemon', [])
                            levels = data.get('levels', [])
                            pokemon_with_levels = [f"{p} (Lv.{l})" for p, l in zip(pokemon_list, levels)]
                            response = f"@{user}, you've already used both catches today! Your team: {', '.join(pokemon_with_levels)} | {get_time_until_reset()}"
                    else:
                        # First catch of the day
                        caught, levels = catch_pokemon()
                        
                        catch_ref.set({
                            'pokemon': caught,
                            'levels': levels,
                            'catch_count': 1,
                            'training_used': 0,
                            'caught_at': firestore.SERVER_TIMESTAMP
                        })
                        
                        pokemon_with_levels = [f"{p} (Lv.{l})" for p, l in zip(caught, levels)]
                        response = f"@{user} caught: {', '.join(pokemon_with_levels)}! (1/2 catches - you can re-roll once if unhappy with your team) | {get_time_until_reset()}"
                    
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
                    self.wfile.write(f"Error catching Pokemon!".encode())
            else:
                # Regular user offline message
                response = f"@{user}, you cannot catch pokemon while Jennet is offline. Please make sure to follow Jennet and come back when Jennet is live to catch and battle pokemon!"
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response.encode())
            return
        
        # ONLINE PLAY - Regular stream logic
        stream_id = hashlib.md5(f"{channel}_{uptime}".encode()).hexdigest()
        
        try:
            catch_ref = db.collection('catches').document(stream_id).collection('users').document(user)
            catch_doc = catch_ref.get()
            
            if catch_doc.exists:
                data = catch_doc.to_dict()
                catch_count = data.get('catch_count', 1)
                
                if catch_count == 1:
                    # First catch done, do re-roll
                    caught, levels = catch_pokemon()
                    
                    catch_ref.update({
                        'pokemon': caught,
                        'levels': levels,
                        'catch_count': 2,
                        'caught_at': firestore.SERVER_TIMESTAMP
                    })
                    
                    pokemon_with_levels = [f"{p} (Lv.{l})" for p, l in zip(caught, levels)]
                    response = f"@{user} RE-ROLLED and caught: {', '.join(pokemon_with_levels)}! (2/2 catches used - no more re-rolls this stream)"
                else:
                    # Already used both catches
                    pokemon_list = data.get('pokemon', [])
                    levels = data.get('levels', [])
                    pokemon_with_levels = [f"{p} (Lv.{l})" for p, l in zip(pokemon_list, levels)]
                    response = f"@{user}, you've already used both catches this stream! Your final team: {', '.join(pokemon_with_levels)}"
            else:
                # First catch this stream
                caught, levels = catch_pokemon()
                
                catch_ref.set({
                    'pokemon': caught,
                    'levels': levels,
                    'catch_count': 1,
                    'training_used': 0,
                    'caught_at': firestore.SERVER_TIMESTAMP
                })
                
                pokemon_with_levels = [f"{p} (Lv.{l})" for p, l in zip(caught, levels)]
                response = f"@{user} caught: {', '.join(pokemon_with_levels)}! (1/2 catches - you can use !pokecatch once more to re-roll if unhappy)"
            
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
            self.wfile.write(f"Error catching Pokemon!".encode())
