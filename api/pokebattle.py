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

from pokemon_data import POKEMON_DATA, TYPE_ADVANTAGES

# Extract legendaries dynamically
LEGENDARIES = [name for name, data in POKEMON_DATA.items() if data.get('legendary', False)]

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
    if pokemon_name in LEGENDARIES:
        power += 5
    
    # Evolution stage (2-6 points) - FIXED: using 'stage' instead of 'evolution_stage'
    stage = POKEMON_DATA.get(pokemon_name, {}).get('stage', 1)
    power += stage * 2
    
    return power

def battle_pokemon(poke1, level1, poke2, level2):
    """Determine winner with balanced type advantages and power scores"""
    power1 = calculate_power(poke1, level1)
    power2 = calculate_power(poke2, level2)
    
    # Type advantages (increased to 2.0 from 1.5)
    types1 = POKEMON_DATA.get(poke1, {}).get('type', 'Normal').split('/')
    types2 = POKEMON_DATA.get(poke2, {}).get('type', 'Normal').split('/')
    
    for type1 in types1:
        for type2 in types2:
            if type2 in TYPE_ADVANTAGES.get(type1, []):
                power1 += 2.0
            if type1 in TYPE_ADVANTAGES.get(type2, []):
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
            self.send_header('Content-type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b"Unauthorized: This channel is not permitted to use this command.")
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
                        self.send_header('Content-type', 'text/plain')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(response.encode())
                        return
                    
                    user_data = user_catch.to_dict()
                    user_pokemon = user_data.get('pokemon', [])
                    user_levels = user_data.get('levels', [])
                    
                    # Check daily battle limit
                    battle_ref = db.collection('mod_daily_battles').document(daily_id).collection('users').document(user)
                    battle_doc = battle_ref.get()
                    
                    if battle_doc.exists:
                        battle_data = battle_doc.to_dict()
                        battles_done = battle_data.get('battles', 0)
                        
                        if battles_done >= 2:
                            wins = battle_data.get('wins', 0)
                            losses = battle_data.get('losses', 0)
                            response = f"@{user}, you've battled twice today ({wins}W-{losses}L)! Wait for the daily reset! | {get_time_until_reset()}"
                            self.send_response(200)
                            self.send_header('Content-type', 'text/plain')
                            self.send_header('Access-Control-Allow-Origin', '*')
                            self.end_headers()
                            self.wfile.write(response.encode())
                            return
                    else:
                        battles_done = 0
                        battle_data = {'battles': 0, 'wins': 0, 'losses': 0}
                    
                    # Find opponent
                    if target:
                        target = target.lower().replace('@', '')
                        if target == user:
                            response = f"@{user}, you can't battle yourself! | {get_time_until_reset()}"
                            self.send_response(200)
                            self.send_header('Content-type', 'text/plain')
                            self.send_header('Access-Control-Allow-Origin', '*')
                            self.end_headers()
                            self.wfile.write(response.encode())
                            return
                        
                        opp_catch = db.collection('mod_daily').document(daily_id).collection('users').document(target).get()
                        
                        if not opp_catch.exists:
                            response = f"@{user}, {target} hasn't caught any Pokemon today! | {get_time_until_reset()}"
                            self.send_response(200)
                            self.send_header('Content-type', 'text/plain')
                            self.send_header('Access-Control-Allow-Origin', '*')
                            self.end_headers()
                            self.wfile.write(response.encode())
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
                            self.send_header('Content-type', 'text/plain')
                            self.send_header('Access-Control-Allow-Origin', '*')
                            self.end_headers()
                            self.wfile.write(response.encode())
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
                    
                    # Update battle records for BOTH users (mod_daily_battles)
                    battle_data['battles'] += 1
                    
                    if winner == 1:
                        battle_data['wins'] += 1
                        emoji = "🏆"
                        result = f"won {user_score}-{opp_score}"
                    else:
                        battle_data['losses'] += 1
                        emoji = "💔"
                        result = f"lost {user_score}-{opp_score}"
                    
                    battle_ref.set(battle_data)
                    
                    # CRITICAL: ALWAYS update opponent's battle count (targeted or random)
                    opp_battle_ref = db.collection('mod_daily_battles').document(daily_id).collection('users').document(opponent)
                    opp_battle_data_existing = opp_battle_ref.get()
                    
                    if opp_battle_data_existing.exists:
                        opp_battle_data = opp_battle_data_existing.to_dict()
                    else:
                        opp_battle_data = {'battles': 0, 'wins': 0, 'losses': 0}
                    
                    opp_battle_data['battles'] += 1
                    # Opponent gets opposite result
                    if winner == 2:  # Opponent won
                        opp_battle_data['wins'] += 1
                    else:  # Opponent lost
                        opp_battle_data['losses'] += 1
                    
                    opp_battle_ref.set(opp_battle_data)
                    
                    # NO LEADERBOARD UPDATE FOR MOD OFFLINE PLAY
                    
                    # Format response with countdown
                    battles_left = 2 - battle_data['battles']
                    battle_text = " | ".join(battle_results)
                    response = f"⚔️ BATTLE: {battle_text} | {emoji} {user} {result} to {opponent}! ({battles_left} battles left) | {get_time_until_reset()}"
                    
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
                    self.wfile.write(f"Error in battle!".encode())
            else:
                # Regular user offline message
                response = f"@{user}, you cannot battle pokemon while Jennet is offline. Please make sure to follow Jennet and come back when Jennet is live to catch and battle pokemon!"
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response.encode())
            return
        
        # ONLINE PLAY - Regular stream logic continues...
        # [Rest of the online play code remains the same]
        stream_id = hashlib.md5(f"{channel}_{uptime}".encode()).hexdigest()
        
        try:
            # Get user's Pokemon
            user_catch = db.collection('catches').document(stream_id).collection('users').document(user).get()
            
            if not user_catch.exists:
                response = f"@{user}, you haven't caught any Pokemon yet! Use !pokecatch first!"
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response.encode())
                return
            
            user_data = user_catch.to_dict()
            user_pokemon = user_data.get('pokemon', [])
            user_levels = user_data.get('levels', [])
            
            # Check battle limit (2 per stream)
            battle_ref = db.collection('stream_battles').document(stream_id).collection('users').document(user)
            battle_doc = battle_ref.get()
            
            if battle_doc.exists:
                battle_data = battle_doc.to_dict()
                battles_done = battle_data.get('battles', 0)
                
                if battles_done >= 2:
                    wins = battle_data.get('wins', 0)
                    losses = battle_data.get('losses', 0)
                    response = f"@{user}, you've battled twice this stream ({wins}W-{losses}L)! Wait for the next stream!"
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(response.encode())
                    return
            else:
                battles_done = 0
                battle_data = {'battles': 0, 'wins': 0, 'losses': 0}
            
            # Find opponent
            if target:
                target = target.lower().replace('@', '')
                if target == user:
                    response = f"@{user}, you can't battle yourself! Use !pokebattle without a target for a random opponent!"
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(response.encode())
                    return
                
                opp_catch = db.collection('catches').document(stream_id).collection('users').document(target).get()
                
                if not opp_catch.exists:
                    response = f"@{user}, {target} hasn't caught any Pokemon yet! Tell them to use !pokecatch!"
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(response.encode())
                    return
                
                # Check if target has battles left
                opp_battle_doc = db.collection('stream_battles').document(stream_id).collection('users').document(target).get()
                if opp_battle_doc.exists:
                    opp_battles = opp_battle_doc.to_dict().get('battles', 0)
                    if opp_battles >= 2:
                        response = f"@{user}, {target} is too tired to battle (already battled twice)! Try someone else!"
                        self.send_response(200)
                        self.send_header('Content-type', 'text/plain')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(response.encode())
                        return
                
                opponent = target
                opp_data = opp_catch.to_dict()
            else:
                # Find random opponent
                all_catches = db.collection('catches').document(stream_id).collection('users').stream()
                potential_opponents = []
                
                for doc in all_catches:
                    if doc.id != user:
                        opp_battle = db.collection('stream_battles').document(stream_id).collection('users').document(doc.id).get()
                        if not opp_battle.exists or opp_battle.to_dict().get('battles', 0) < 2:
                            potential_opponents.append((doc.id, doc.to_dict()))
                
                if not potential_opponents:
                    response = f"@{user}, no opponents available! Encourage others to !pokecatch!"
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(response.encode())
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
            
            # Update battle records for BOTH users
            battle_data['battles'] += 1
            
            if winner == 1:
                battle_data['wins'] += 1
                emoji = "🏆"
                result = f"won {user_score}-{opp_score}"
            else:
                battle_data['losses'] += 1
                emoji = "💔"
                result = f"lost {user_score}-{opp_score}"
            
            battle_ref.set(battle_data)
            
            # CRITICAL: ALWAYS update opponent's battle count (targeted or random)
            opp_battle_ref = db.collection('stream_battles').document(stream_id).collection('users').document(opponent)
            opp_battle_data_existing = opp_battle_ref.get()
            
            if opp_battle_data_existing.exists:
                opp_battle_data = opp_battle_data_existing.to_dict()
            else:
                opp_battle_data = {'battles': 0, 'wins': 0, 'losses': 0}
            
            opp_battle_data['battles'] += 1
            # Opponent gets opposite result
            if winner == 2:  # Opponent won
                opp_battle_data['wins'] += 1
            else:  # Opponent lost
                opp_battle_data['losses'] += 1
            
            opp_battle_ref.set(opp_battle_data)
            
            # Update leaderboard for BOTH users (online play only) - ALWAYS, not just targeted
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
            
            # ALWAYS update opponent's leaderboard (targeted or random)
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
            
            # Also update legends collection for BOTH users
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
            
            # ALWAYS update opponent's legends (targeted or random)
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
            battles_left = 2 - battle_data['battles']
            battle_text = " | ".join(battle_results)
            response = f"⚔️ BATTLE: {battle_text} | {emoji} {user} {result} to {opponent}! ({battles_left} battles left)"
            
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
            self.wfile.write(f"Error in battle!".encode())
