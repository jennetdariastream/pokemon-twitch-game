# pokebattle.py
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

# Cache for Pokemon data
POKEMON_CACHE = {}
TYPE_ADVANTAGES_CACHE = {}
LEGENDARIES_CACHE = []
CACHE_LOADED = False

def load_battle_data():
    """Load Pokemon data and type advantages from Firestore"""
    global POKEMON_CACHE, TYPE_ADVANTAGES_CACHE, LEGENDARIES_CACHE, CACHE_LOADED
    
    if CACHE_LOADED:
        return True
    
    try:
        # Load type advantages
        type_doc = db.collection('game_config').document('type_advantages').get()
        if type_doc.exists:
            TYPE_ADVANTAGES_CACHE = type_doc.to_dict().get('data', {})
        
        # Load legendaries
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

def calculate_power(pokemon_name, level):
    """Calculate battle power with balanced scoring"""
    power = 0
    
    # Base power from level (capped at 5 points max)
    power += min(level * 0.1, 5)
    
    # Legendary bonus (reduced from 10 to 5 for balance)
    if pokemon_name in LEGENDARIES_CACHE:
        power += 5
    
    # Evolution stage (2-6 points)
    stage = POKEMON_CACHE.get(pokemon_name, {}).get('stage', 1)
    power += stage * 2
    
    return power

def battle_pokemon(poke1, level1, poke2, level2):
    """Determine winner with balanced type advantages and power scores"""
    power1 = calculate_power(poke1, level1)
    power2 = calculate_power(poke2, level2)
    
    # Type advantages (increased to 2.0 from 1.5)
    types1 = POKEMON_CACHE.get(poke1, {}).get('type', 'Normal').split('/')
    types2 = POKEMON_CACHE.get(poke2, {}).get('type', 'Normal').split('/')
    
    for type1 in types1:
        for type2 in types2:
            if type2 in TYPE_ADVANTAGES_CACHE.get(type1, []):
                power1 += 2.0
            if type1 in TYPE_ADVANTAGES_CACHE.get(type2, []):
                power2 += 2.0
    
    # Random factor (increased to 0-3 from 0-2)
    power1 += random.random() * 3
    power2 += random.random() * 3
    
    return 1 if power1 > power2 else 2

def sort_by_power(pokemon_list, levels_list):
    """Sort Pokemon by power score from weakest to strongest"""
    pokemon_with_power = []
    for i in range(len(pokemon_list)):
        power = calculate_power(pokemon_list[i], levels_list[i])
        pokemon_with_power.append((pokemon_list[i], levels_list[i], power))
    
    # Sort by power (weakest first)
    pokemon_with_power.sort(key=lambda x: x[2])
    return pokemon_with_power

def full_team_battle(user_pokemon, user_levels, opp_pokemon, opp_levels, user, opponent):
    """Conduct full 5v5 team battle"""
    # Sort both teams by power (weakest to strongest)
    user_sorted = sort_by_power(user_pokemon, user_levels)
    opp_sorted = sort_by_power(opp_pokemon, opp_levels)
    
    # Battle all 5 matchups
    results = []
    user_wins = 0
    opp_wins = 0
    
    for i in range(5):
        round_winner = battle_pokemon(
            user_sorted[i][0], user_sorted[i][1],
            opp_sorted[i][0], opp_sorted[i][1]
        )
        
        if round_winner == 1:
            user_wins += 1
            results.append(f"R{i+1}: {user}'s {user_sorted[i][0]} (Lv.{user_sorted[i][1]}) ✅ vs {opponent}'s {opp_sorted[i][0]} (Lv.{opp_sorted[i][1]}) ❌")
        else:
            opp_wins += 1
            results.append(f"R{i+1}: {user}'s {user_sorted[i][0]} (Lv.{user_sorted[i][1]}) ❌ vs {opponent}'s {opp_sorted[i][0]} (Lv.{opp_sorted[i][1]}) ✅")
        
        # Early exit if someone reaches 3 wins
        if user_wins == 3 or opp_wins == 3:
            break
    
    # Determine overall winner
    overall_winner = 1 if user_wins >= 3 else 2
    
    return overall_winner, results, user_wins, opp_wins

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
        
        # Load battle data from Firestore
        if not load_battle_data():
            self.send_response(500)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b"Error: Could not load battle data from database.")
            return
        
        user = params.get('user', ['someone'])[0].lower()
        target = params.get('target', [None])[0]
        uptime = params.get('uptime', [None])[0]
        user_level = params.get('user_level', [''])[0].lower()
        
        # Check if stream is online
        if not uptime or uptime == 'offline':
            # Check if user is a moderator
            if user_level in ['owner', 'moderator']:
                # Moderator offline play - daily battles
                utc_now = datetime.now(timezone.utc)
                daily_id = f"mod_daily_{utc_now.strftime('%Y%m%d')}"
                
                try:
                    # Get user's Pokemon from mod_daily
                    user_catch = db.collection('mod_daily').document(daily_id).collection('users').document(user).get()
                    
                    if not user_catch.exists:
                        response = f"@{user}, you haven't caught any Pokemon today! Use !pokecatch first! | {get_time_until_reset()}"
                        self.send_response(200)
                        self.send_header('Content-type', 'text/plain; charset=utf-8')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(response.encode('utf-8'))
                        return
                    
                    user_data = user_catch.to_dict()
                    user_pokemon = user_data.get('pokemon', [])
                    user_levels = user_data.get('levels', [])
                    
                    # Check daily battle limit (using separate counter)
                    battles_used = user_data.get('battles_used', 0)
                    
                    if battles_used >= 2:
                        response = f"@{user}, you've battled twice today! Wait for the daily reset! | {get_time_until_reset()}"
                        self.send_response(200)
                        self.send_header('Content-type', 'text/plain; charset=utf-8')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(response.encode('utf-8'))
                        return
                    
                    # Find opponent
                    if target:
                        target = target.lower().replace('@', '')
                        if target == user:
                            response = f"@{user}, you can't battle yourself! | {get_time_until_reset()}"
                            self.send_response(200)
                            self.send_header('Content-type', 'text/plain; charset=utf-8')
                            self.send_header('Access-Control-Allow-Origin', '*')
                            self.end_headers()
                            self.wfile.write(response.encode('utf-8'))
                            return
                        
                        opp_catch = db.collection('mod_daily').document(daily_id).collection('users').document(target).get()
                        
                        if not opp_catch.exists:
                            response = f"@{user}, {target} hasn't caught any Pokemon today! | {get_time_until_reset()}"
                            self.send_response(200)
                            self.send_header('Content-type', 'text/plain; charset=utf-8')
                            self.send_header('Access-Control-Allow-Origin', '*')
                            self.end_headers()
                            self.wfile.write(response.encode('utf-8'))
                            return
                        
                        opponent = target
                        opp_data = opp_catch.to_dict()
                    else:
                        # Find random opponent from mod_daily
                        all_catches = db.collection('mod_daily').document(daily_id).collection('users').stream()
                        potential_opponents = []
                        
                        for doc in all_catches:
                            if doc.id != user:
                                potential_opponents.append((doc.id, doc.to_dict()))
                        
                        if not potential_opponents:
                            response = f"@{user}, no opponents available in offline mode! | {get_time_until_reset()}"
                            self.send_response(200)
                            self.send_header('Content-type', 'text/plain; charset=utf-8')
                            self.send_header('Access-Control-Allow-Origin', '*')
                            self.end_headers()
                            self.wfile.write(response.encode('utf-8'))
                            return
                        
                        opponent, opp_data = random.choice(potential_opponents)
                    
                    opp_pokemon = opp_data.get('pokemon', [])
                    opp_levels = opp_data.get('levels', [])
                    
                    # Full team battle
                    winner, battle_results, user_score, opp_score = full_team_battle(
                        user_pokemon, user_levels, 
                        opp_pokemon, opp_levels,
                        user, opponent
                    )
                    
                    # Update battle count for user
                    user_catch_ref = db.collection('mod_daily').document(daily_id).collection('users').document(user)
                    user_catch_ref.update({
                        'battles_used': battles_used + 1
                    })
                    
                    # Update battle count for opponent (ALWAYS - targeted or random)
                    opp_catch_ref = db.collection('mod_daily').document(daily_id).collection('users').document(opponent)
                    opp_catch_ref.update({
                        'battles_used': opp_data.get('battles_used', 0) + 1
                    })
                    
                    # Format response with countdown
                    if winner == 1:
                        emoji = "🏆"
                        result = f"won {user_score}-{opp_score}"
                    else:
                        emoji = "💔"
                        result = f"lost {user_score}-{opp_score}"
                    
                    battles_left = 1 - battles_used
                    battle_text = " | ".join(battle_results)
                    response = f"⚔️ BATTLE: {battle_text} | {emoji} {user} {result} to {opponent}! ({battles_left} battle{'s' if battles_left != 1 else ''} left) | {get_time_until_reset()}"
                    
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
                    self.wfile.write(f"Error in battle!".encode('utf-8'))
            else:
                # Regular user offline message
                response = f"@{user}, you cannot battle pokemon while Jennet is offline. Please make sure to follow Jennet and come back when Jennet is live to catch and battle pokemon!"
                self.send_response(200)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response.encode('utf-8'))
            return
        
        # ONLINE PLAY - Regular stream logic
        stream_id = hashlib.md5(f"{channel}_{uptime}".encode()).hexdigest()
        
        try:
            # Get user's Pokemon
            user_catch = db.collection('catches').document(stream_id).collection('users').document(user).get()
            
            if not user_catch.exists:
                response = f"@{user}, you haven't caught any Pokemon yet! Use !pokecatch first!"
                self.send_response(200)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response.encode('utf-8'))
                return
            
            user_data = user_catch.to_dict()
            user_pokemon = user_data.get('pokemon', [])
            user_levels = user_data.get('levels', [])
            
            # Check battle limit (using separate counter)
            battles_used = user_data.get('battles_used', 0)
            
            if battles_used >= 2:
                response = f"@{user}, you've battled twice this stream! Wait for the next stream!"
                self.send_response(200)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response.encode('utf-8'))
                return
            
            # Find opponent
            if target:
                target = target.lower().replace('@', '')
                if target == user:
                    response = f"@{user}, you can't battle yourself! Use !pokebattle without a target for a random opponent!"
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain; charset=utf-8')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(response.encode('utf-8'))
                    return
                
                opp_catch = db.collection('catches').document(stream_id).collection('users').document(target).get()
                
                if not opp_catch.exists:
                    response = f"@{user}, {target} hasn't caught any Pokemon yet! Tell them to use !pokecatch!"
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain; charset=utf-8')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(response.encode('utf-8'))
                    return
                
                # Check if target has battles left
                opp_data = opp_catch.to_dict()
                opp_battles = opp_data.get('battles_used', 0)
                if opp_battles >= 2:
                    response = f"@{user}, {target} is too tired to battle (already battled twice)! Try someone else!"
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain; charset=utf-8')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(response.encode('utf-8'))
                    return
                
                opponent = target
            else:
                # Find random opponent
                all_catches = db.collection('catches').document(stream_id).collection('users').stream()
                potential_opponents = []
                
                for doc in all_catches:
                    if doc.id != user:
                        doc_data = doc.to_dict()
                        if doc_data.get('battles_used', 0) < 2:
                            potential_opponents.append((doc.id, doc_data))
                
                if not potential_opponents:
                    response = f"@{user}, no opponents available! Encourage others to !pokecatch!"
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain; charset=utf-8')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(response.encode('utf-8'))
                    return
                
                opponent, opp_data = random.choice(potential_opponents)
            
            opp_pokemon = opp_data.get('pokemon', [])
            opp_levels = opp_data.get('levels', [])
            
            # Full team battle
            winner, battle_results, user_score, opp_score = full_team_battle(
                user_pokemon, user_levels,
                opp_pokemon, opp_levels,
                user, opponent
            )
            
            # Update battle count for user
            user_catch_ref = db.collection('catches').document(stream_id).collection('users').document(user)
            user_catch_ref.update({
                'battles_used': battles_used + 1
            })
            
            # Update battle count for opponent (ALWAYS - targeted or random)
            opp_catch_ref = db.collection('catches').document(stream_id).collection('users').document(opponent)
            opp_catch_ref.update({
                'battles_used': opp_data.get('battles_used', 0) + 1
            })
            
            # Update leaderboard for user
            leaderboard_ref = db.collection('leaderboard').document(user)
            leaderboard_doc = leaderboard_ref.get()
            
            if leaderboard_doc.exists:
                lb_data = leaderboard_doc.to_dict()
                lb_data['total_battles'] = lb_data.get('total_battles', 0) + 1
                if winner == 1:
                    lb_data['total_wins'] = lb_data.get('total_wins', 0) + 1
                else:
                    lb_data['total_losses'] = lb_data.get('total_losses', 0) + 1
            else:
                lb_data = {
                    'total_battles': 1,
                    'total_wins': 1 if winner == 1 else 0,
                    'total_losses': 1 if winner == 2 else 0
                }
            
            lb_data['last_battle'] = firestore.SERVER_TIMESTAMP
            leaderboard_ref.set(lb_data)
            
            # Update leaderboard for opponent (ALWAYS - targeted or random)
            opp_leaderboard_ref = db.collection('leaderboard').document(opponent)
            opp_leaderboard_doc = opp_leaderboard_ref.get()
            
            if opp_leaderboard_doc.exists:
                opp_lb_data = opp_leaderboard_doc.to_dict()
                opp_lb_data['total_battles'] = opp_lb_data.get('total_battles', 0) + 1
                if winner == 2:
                    opp_lb_data['total_wins'] = opp_lb_data.get('total_wins', 0) + 1
                else:
                    opp_lb_data['total_losses'] = opp_lb_data.get('total_losses', 0) + 1
            else:
                opp_lb_data = {
                    'total_battles': 1,
                    'total_wins': 1 if winner == 2 else 0,
                    'total_losses': 1 if winner == 1 else 0
                }
            
            opp_lb_data['last_battle'] = firestore.SERVER_TIMESTAMP
            opp_leaderboard_ref.set(opp_lb_data)
            
            # Also update legends collection for user
            legends_ref = db.collection('legends').document(user)
            legends_doc = legends_ref.get()
            
            if legends_doc.exists:
                legend_data = legends_doc.to_dict()
                legend_data['total_battles'] = legend_data.get('total_battles', 0) + 1
                if winner == 1:
                    legend_data['total_wins'] = legend_data.get('total_wins', 0) + 1
                else:
                    legend_data['total_losses'] = legend_data.get('total_losses', 0) + 1
            else:
                legend_data = {
                    'total_battles': 1,
                    'total_wins': 1 if winner == 1 else 0,
                    'total_losses': 1 if winner == 2 else 0
                }
            
            legend_data['last_battle'] = firestore.SERVER_TIMESTAMP
            legends_ref.set(legend_data)
            
            # Update legends for opponent (ALWAYS - targeted or random)
            opp_legends_ref = db.collection('legends').document(opponent)
            opp_legends_doc = opp_legends_ref.get()
            
            if opp_legends_doc.exists:
                opp_legend_data = opp_legends_doc.to_dict()
                opp_legend_data['total_battles'] = opp_legend_data.get('total_battles', 0) + 1
                if winner == 2:
                    opp_legend_data['total_wins'] = opp_legend_data.get('total_wins', 0) + 1
                else:
                    opp_legend_data['total_losses'] = opp_legend_data.get('total_losses', 0) + 1
            else:
                opp_legend_data = {
                    'total_battles': 1,
                    'total_wins': 1 if winner == 2 else 0,
                    'total_losses': 1 if winner == 1 else 0
                }
            
            opp_legend_data['last_battle'] = firestore.SERVER_TIMESTAMP
            opp_legends_ref.set(opp_legend_data)
            
            # Format response
            if winner == 1:
                emoji = "🏆"
                result = f"won {user_score}-{opp_score}"
            else:
                emoji = "💔"
                result = f"lost {user_score}-{opp_score}"
            
            battles_left = 1 - battles_used
            battle_text = " | ".join(battle_results)
            response = f"⚔️ BATTLE: {battle_text} | {emoji} {user} {result} to {opponent}! ({battles_left} battle{'s' if battles_left != 1 else ''} left)"
            
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
            self.wfile.write(f"Error in battle!".encode('utf-8'))
