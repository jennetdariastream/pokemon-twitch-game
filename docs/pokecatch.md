# !pokecatch Command Documentation

## StreamElements Setup
```
!command add !pokecatch $(urlfetch https://pokemon-twitch-game.vercel.app/api/pokecatch?user=$(user)&channel=$(channel)&uptime=$(uptime)&user_level=$(userlevel))
```

## Command Overview
Allows viewers to catch a team of 5 random Pokemon during stream with one re-roll opportunity.

## Usage Restrictions

| User Type | Stream Status | Access | Limit |
|-----------|--------------|--------|-------|
| Viewer | Online | ✅ | 2 per stream |
| Viewer | Offline | ❌ | N/A |
| Moderator | Online | ✅ | 2 per stream |
| Moderator | Offline | ✅ | 2 per day |
| Owner | Online | ✅ | 2 per stream |
| Owner | Offline | ✅ | 2 per day |

## All Command Messages

### Online Mode (Stream Live)

**First Catch:**
```
@{user} caught: {Pokemon1} (Lv.X), {Pokemon2} (Lv.X), {Pokemon3} (Lv.X), {Pokemon4} (Lv.X), {Pokemon5} (Lv.X)! (1/2 catches - you can use !pokecatch once more to re-roll if unhappy)
```

**Second Catch (Re-roll):**
```
@{user} RE-ROLLED and caught: {Pokemon1} (Lv.X), {Pokemon2} (Lv.X), {Pokemon3} (Lv.X), {Pokemon4} (Lv.X), {Pokemon5} (Lv.X)! (2/2 catches used - no more re-rolls this stream)
```

**Already Used Both:**
```
@{user}, you've already used both catches this stream! Your final team: {Pokemon1} (Lv.X), {Pokemon2} (Lv.X), {Pokemon3} (Lv.X), {Pokemon4} (Lv.X), {Pokemon5} (Lv.X)
```

### Offline Mode - Regular Users

**Any Attempt:**
```
@{user}, you cannot catch pokemon while Jennet is offline. Please make sure to follow Jennet and come back when Jennet is live to catch and battle pokemon!
```

### Offline Mode - Moderators Only

**First Catch:**
```
@{user} caught: {Pokemon1} (Lv.X), {Pokemon2} (Lv.X), {Pokemon3} (Lv.X), {Pokemon4} (Lv.X), {Pokemon5} (Lv.X)! (1/2 catches - you can re-roll once if unhappy with your team) | GAME RESETS IN X HRS, Y MINS, Z SECS
```

**Second Catch (Re-roll):**
```
@{user} RE-ROLLED and caught: {Pokemon1} (Lv.X), {Pokemon2} (Lv.X), {Pokemon3} (Lv.X), {Pokemon4} (Lv.X), {Pokemon5} (Lv.X)! (2/2 catches used - no more re-rolls today) | GAME RESETS IN X HRS, Y MINS, Z SECS
```

**Already Used Both:**
```
@{user}, you've already used both catches today! Your team: {Pokemon1} (Lv.X), {Pokemon2} (Lv.X), {Pokemon3} (Lv.X), {Pokemon4} (Lv.X), {Pokemon5} (Lv.X) | GAME RESETS IN X HRS, Y MINS, Z SECS
```

### Error Messages

- `Unauthorized: This channel is not permitted to use this command.` - Wrong channel
- `Error: Could not load Pokemon data from database.` - Database connection issue
- `Error catching Pokemon!` - General error

## Game Mechanics

- **Catch Chance**: 97% regular Pokemon, 3% legendary Pokemon
- **Levels**: Based on Pokemon's catch_level_min and catch_level_max from database
- **Re-roll**: Users get ONE chance to re-roll their entire team if unhappy
- **Stream Tracking**: Uses stream uptime to track unique streams
- **Mod Reset**: Resets daily at 12am UTC for offline mode

## Database Collections Used

- `pokemon_data/` - Pokemon information
- `game_config/legendaries` - List of legendary Pokemon
- `catches/{stream_id}/users/{username}` - Stream catches
- `mod_daily/{date}/users/{username}` - Moderator offline catches
