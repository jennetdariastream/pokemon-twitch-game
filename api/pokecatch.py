# pokecatch.py
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

from pokemon_data import POKEMON_DATA, LEGENDARIES

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
                            pokemon_with_levels = [f"{p} (Lv.{l})" for p, l in zip(pokemon_list, levels)]
                            response = f"@{user}, you already caught: {', '.join(pokemon_with_levels)}! (Daily re-roll used) | {get_time_until_reset()}"
                        else:
                            response = f"@{user}, you can re-roll your team once by using !pokecatch again. Current team: {', '.join(pokemon_list)} | {get_time_until_reset()}"
                    else:
                        # Catch 5 Pokemon with levels
                        caught = []
                        levels = []
                        
                        for _ in range(5):
                            if random.random() < 0.03:  # 3% legendary chance
                                pokemon = random.choice(LEGENDARIES)
                                level = random.randint(40, 50)
                            else:
                                pokemon = random.choice([p for p in POKEMON_DATA.keys() if p not in LEGENDARIES])
                                poke_info = POKEMON_DATA[pokemon]
                                if poke_info.get('evolution_stage') == 1:
                                    level = random.randint(5, 20)
                                elif poke_info.get('evolution_stage') == 2:
                                    level = random.randint(15, 35)
                                else:
                                    level = random.randint(20, 45)
                            
                            caught.append(pokemon)
                            levels.append(level)
                        
                        # Save to mod_daily database (not regular catches)
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
                    pokemon_with_levels = [f"{p} (Lv.{l})" for p, l in zip(pokemon_list, levels)]
                    response = f"@{user}, you already caught: {', '.join(pokemon_with_levels)}! (Re-roll used)"
                else:
                    response = f"@{user}, you can re-roll your team once by using !pokecatch again. Current team: {', '.join(pokemon_list)}"
            else:
                # Catch 5 Pokemon with levels
                caught = []
                levels = []
                
                for _ in range(5):
                    if random.random() < 0.03:  # 3% legendary chance
                        pokemon = random.choice(LEGENDARIES)
                        level = random.randint(40, 50)
                    else:
                        pokemon = random.choice([p for p in POKEMON_DATA.keys() if p not in LEGENDARIES])
                        poke_info = POKEMON_DATA[pokemon]
                        if poke_info.get('evolution_stage') == 1:
                            level = random.randint(5, 20)
                        elif poke_info.get('evolution_stage') == 2:
                            level = random.randint(15, 35)
                        else:
                            level = random.randint(20, 45)
                    
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
