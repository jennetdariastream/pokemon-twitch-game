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

def check_evolution(pokemon_name, old_level, new_level, level_gain):
    """Check if Pokemon can evolve and return evolution if applicable"""
    # Evolution only happens with 9-10 level gains
    if level_gain < 9:
        return None
        
    try:
        doc = db.collection('pokemon_data').document(pokemon_name).get()
        if doc.exists:
            poke_data = doc.to_dict()
            # Check all evolution requirements
            if (poke_data.get('can_evolve', False) and 
                poke_data.get('can_train_evolve', False) and
                poke_data.get('evolution_method') == 'level-up'):
                
                evolves_to = poke_data.get('evolves_to')
                evo_level = poke_data.get('min_level_to_evolve')
                
                if evolves_to and evo_level and old_level < evo_level <= new_level:
                    # Check if this is a branched evolution (pipe-separated)
                    if '|' in str(evolves_to):
                        # Split and randomly choose from the branches
                        evolution_options = evolves_to.split('|')
                        evolution = random.choice(evolution_options)
                    else:
                        # Single evolution path
                        evolution = evolves_to
                    return evolution
    except:
        pass
    return None

def get_weighted_level_gain():
    """Get level gain with weighted probabilities"""
    levels = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    weights = [1, 5, 8, 11, 14, 16, 14, 11, 8, 6, 6]  # Total: 100
    return random.choices(levels, weights=weights, k=1)[0]

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
        uptime = params.get('uptime', [''])[0]
        user_level = params.get('user_level', ['regular'])[0].lower()
        
        is_offline = uptime.lower() == 'offline'
        is_mod = user_level in ['moderator', 'owner']
        
        try:
            if is_offline:
                if not is_mod:
                    # Regular users cannot train offline
                    response = f"@{user}, you cannot train pokemon while Jennet is offline. Please make sure to follow Jennet and come back when Jennet is live to catch, train, and battle pokemon!"
                else:
                    # Mod offline training (daily)
                    utc_now = datetime.now(timezone.utc)
                    daily_id = f"mod_daily_{utc_now.strftime('%Y%m%d')}"  # FIXED: Added mod_daily_ prefix
                    catch_ref = db.collection('mod_daily').document(daily_id).collection('users').document(user)
                    data = catch_ref.get().to_dict()
                    
                    if not data or 'pokemon' not in data:
                        response = f"@{user}, you need to !pokecatch before training!"
                    else:
                        training_used = data.get('training_used', 0)
                        
                        if training_used >= 2:
                            pokemon_list = data.get('pokemon', [])
                            levels = data.get('levels', [])
                            pokemon_with_levels = [f"{p} (Lv.{l})" for p, l in zip(pokemon_list, levels)]
                            response = f"@{user}, you've already trained twice today! Your team: {', '.join(pokemon_with_levels)} | {get_time_until_reset()}"
                        else:
                            # Train the Pokemon
                            pokemon_list = data.get('pokemon', [])
                            old_levels = data.get('levels', [])
                            new_levels = []
                            
                            # Build individual results for each Pokemon
                            training_results = []
                            for i, (pokemon, old_level) in enumerate(zip(pokemon_list, old_levels)):
                                level_gain = get_weighted_level_gain()
                                new_level = old_level + level_gain
                                new_levels.append(new_level)
                                
                                # Check for evolution
                                evolution = check_evolution(pokemon, old_level, new_level, level_gain)
                                if evolution:
                                    training_results.append(f"{pokemon} gained +{level_gain} levels and evolved into {evolution}")
                                    pokemon_list[i] = evolution  # FIXED: Use index instead of .index()
                                else:
                                    training_results.append(f"{pokemon} gained +{level_gain} levels")
                            
                            # Update database
                            catch_ref.update({
                                'pokemon': pokemon_list,
                                'levels': new_levels,
                                'training_used': training_used + 1
                            })
                            
                            trainings_left = 2 - (training_used + 1)
                            response = f"@{user} trained! {'! '.join(training_results)}! ({trainings_left} training sessions left) | {get_time_until_reset()}"
            else:
                # Online training
                stream_id = hashlib.md5(f"{channel}_{uptime}".encode()).hexdigest()
                catch_ref = db.collection('catches').document(stream_id).collection('users').document(user)
                data = catch_ref.get().to_dict()
                
                if not data or 'pokemon' not in data:
                    response = f"@{user}, you need to !pokecatch before training!"
                else:
                    training_used = data.get('training_used', 0)
                    
                    if training_used >= 2:
                        pokemon_list = data.get('pokemon', [])
                        levels = data.get('levels', [])
                        pokemon_with_levels = [f"{p} (Lv.{l})" for p, l in zip(pokemon_list, levels)]
                        response = f"@{user}, you've already trained twice this stream! Your team: {', '.join(pokemon_with_levels)}"
                    else:
                        # Train the Pokemon
                        pokemon_list = data.get('pokemon', [])
                        old_levels = data.get('levels', [])
                        new_levels = []
                        
                        # Build individual results for each Pokemon
                        training_results = []
                        for i, (pokemon, old_level) in enumerate(zip(pokemon_list, old_levels)):
                            level_gain = get_weighted_level_gain()
                            new_level = old_level + level_gain
                            new_levels.append(new_level)
                            
                            # Check for evolution
                            evolution = check_evolution(pokemon, old_level, new_level, level_gain)
                            if evolution:
                                training_results.append(f"{pokemon} gained +{level_gain} levels and evolved into {evolution}")
                                pokemon_list[i] = evolution  # FIXED: Use index instead of .index()
                            else:
                                training_results.append(f"{pokemon} gained +{level_gain} levels")
                        
                        # Update database
                        catch_ref.update({
                            'pokemon': pokemon_list,
                            'levels': new_levels,
                            'training_used': training_used + 1
                        })
                        
                        trainings_left = 2 - (training_used + 1)
                        response = f"@{user} trained! {'! '.join(training_results)}! ({trainings_left} training sessions left)"
            
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
