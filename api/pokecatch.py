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

# Cache for Pokemon data to reduce Firestore reads
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
    except Exception as e:
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
                    # Check if mod already caught today
                    catch_ref = db.collection('mod_daily').document(daily_id).collection('users').document(user)
                    catch_doc = catch_ref.get()
                    
                    if catch_doc.exists:
                        data = catch_doc.to_dict()
                        pokemon_list = data.get('pokemon', [])
                        levels = data.get('levels', [])
                        catch_count = data.get('catch_count', 1)
                        
                        # Check for re-roll
                        if catch_count >= 2:
                            # Already used re-roll
                            pokemon_with_levels = [f"{p} (Lv.{l})" for p, l in zip(pokemon_list, levels)]
                            response = f"@{user}, you already caught: {', '.join(pokemon_with_levels)}! (Daily re-roll used) | {get_time_until_reset()}"
                        else:
                            # Re-roll - generate NEW Pokemon
                            caught = []
                            levels = []
                            
                            # Get all Pokemon names
                            all_pokemon = list(POKEMON_CACHE.keys())
                            non_legendaries = [p for p in all_pokemon if p not in LEGENDARIES_CACHE]
                            
                            for _ in range(5):
                                if LEGENDARIES_CACHE and random.random() < 0.03:  # 3% legendary chance
                                    pokemon = random.choice(LEGENDARIES_CACHE)
                                    level = random.randint(40, 50)
                                else:
                                    # Get non-legendary Pokemon
                                    pokemon = random.choice(non_legendaries if non_legendaries else all_pokemon)
                                    poke_info = POKEMON_CACHE.get(pokemon, {})
                                    
                                    # Use catch_level_min and catch_level_max from data
                                    min_level = poke_info.get('catch_level_min', 5)
                                    max_level = poke_info.get('catch_level_max', 45)
                                    level = random.randint(min_level, max_level)
                                
                                caught.append(pokemon)
                                levels.append(level)
                            
                            # Update with re-roll
                            catch_ref.update({
                                'pokemon': caught,
                                'levels': levels,
                                'catch_count': 2,
                                'caught_at': firestore.SERVER_TIMESTAMP
                            })
                            
                            pokemon_with_levels = [f"{p} (Lv.{l})" for p, l in zip(caught, levels)]
                            response = f"@{user} caught: {', '.join(pokemon_with_levels)}! (Daily re-roll used) | {get_time_until_reset()}"
                    else:
                        # First catch of the day for mod
                        caught = []
                        levels = []
                        
                        # Get all Pokemon names
                        all_pokemon = list(POKEMON_CACHE.keys())
                        non_legendaries = [p for p in all_pokemon if p not in LEGENDARIES_CACHE]
                        
                        for _ in range(5):
                            if LEGENDARIES_CACHE and random.random() < 0.03:  # 3% legendary chance
                                pokemon = random.choice(LEGENDARIES_CACHE)
                                level = random.randint(40, 50)
                            else:
                                # Get non-legendary Pokemon
                                pokemon = random.choice(non_legendaries if non_legendaries else all_pokemon)
                                poke_info = POKEMON_CACHE.get(pokemon, {})
                                
                                # Use catch_level_min and catch_level_max from data
                                min_level = poke_info.get('catch_level_min', 5)
                                max_level = poke_info.get('catch_level_max', 45)
                                level = random.randint(min_level, max_level)
                            
                            caught.append(pokemon)
                            levels.append(level)
                        
                        # Save to mod_daily database
                        catch_ref.set({
                            'pokemon': caught,
                            'levels': levels,
                            'catch_count': 1,
                            'training_used': 0,
                            'caught_at': firestore.SERVER_TIMESTAMP
                        })
                        
                        pokemon_with_levels = [f"{p} (Lv.{l})" for p, l in zip(caught, levels)]
                        response = f"@{user} caught: {', '.join(pokemon_with_levels)}! | {get_time_until_reset()}"
                    
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
                # Regular user offline message - EXACT format from requirements
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
            # Check if user already caught this stream
            catch_ref = db.collection('catches').document(stream_id).collection('users').document(user)
            catch_doc = catch_ref.get()
            
            if catch_doc.exists:
                data = catch_doc.to_dict()
                pokemon_list = data.get('pokemon', [])
                levels = data.get('levels', [])
                catch_count = data.get('catch_count', 1)
                
                # Check for re-roll
                if catch_count >= 2:
                    # Already used re-roll - EXACT format from requirements
                    pokemon_with_levels = [f"{p} (Lv.{l})" for p, l in zip(pokemon_list, levels)]
                    response = f"@{user}, you already caught: {', '.join(pokemon_with_levels)}! (Re-roll used)"
                else:
                    # Re-roll - generate NEW Pokemon
                    caught = []
                    levels = []
                    
                    # Get all Pokemon names
                    all_pokemon = list(POKEMON_CACHE.keys())
                    non_legendaries = [p for p in all_pokemon if p not in LEGENDARIES_CACHE]
                    
                    for _ in range(5):
                        if LEGENDARIES_CACHE and random.random() < 0.03:  # 3% legendary chance
                            pokemon = random.choice(LEGENDARIES_CACHE)
                            level = random.randint(40, 50)
                        else:
                            # Get non-legendary Pokemon
                            pokemon = random.choice(non_legendaries if non_legendaries else all_pokemon)
                            poke_info = POKEMON_CACHE.get(pokemon, {})
                            
                            # Use catch_level_min and catch_level_max from data
                            min_level = poke_info.get('catch_level_min', 5)
                            max_level = poke_info.get('catch_level_max', 45)
                            level = random.randint(min_level, max_level)
                        
                        caught.append(pokemon)
                        levels.append(level)
                    
                    # Update with re-roll
                    catch_ref.update({
                        'pokemon': caught,
                        'levels': levels,
                        'catch_count': 2,
                        'caught_at': firestore.SERVER_TIMESTAMP
                    })
                    
                    pokemon_with_levels = [f"{p} (Lv.{l})" for p, l in zip(caught, levels)]
                    response = f"@{user} caught: {', '.join(pokemon_with_levels)}! (Re-roll used)"
            else:
                # First catch this stream
                caught = []
                levels = []
                
                # Get all Pokemon names
                all_pokemon = list(POKEMON_CACHE.keys())
                non_legendaries = [p for p in all_pokemon if p not in LEGENDARIES_CACHE]
                
                for _ in range(5):
                    if LEGENDARIES_CACHE and random.random() < 0.03:  # 3% legendary chance
                        pokemon = random.choice(LEGENDARIES_CACHE)
                        level = random.randint(40, 50)
                    else:
                        # Get non-legendary Pokemon
                        pokemon = random.choice(non_legendaries if non_legendaries else all_pokemon)
                        poke_info = POKEMON_CACHE.get(pokemon, {})
                        
                        # Use catch_level_min and catch_level_max from data
                        min_level = poke_info.get('catch_level_min', 5)
                        max_level = poke_info.get('catch_level_max', 45)
                        level = random.randint(min_level, max_level)
                    
                    caught.append(pokemon)
                    levels.append(level)
                
                # Save to database
                catch_ref.set({
                    'pokemon': caught,
                    'levels': levels,
                    'catch_count': 1,
                    'training_used': 0,
                    'caught_at': firestore.SERVER_TIMESTAMP
                })
                
                # First catch message - EXACT format from requirements
                pokemon_with_levels = [f"{p} (Lv.{l})" for p, l in zip(caught, levels)]
                response = f"@{user} caught: {', '.join(pokemon_with_levels)}! Use !pokebattle to battle trainers or !poketrain to level up!"
            
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
