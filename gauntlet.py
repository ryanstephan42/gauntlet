import pygame
import json
import os
import socket
import subprocess
import time

# --- CONSTANTS ---
DATA_FOLDER = "gauntlet_data"
RETROARCH_IP = '127.0.0.1'
RETROARCH_PORT = 55355

# --- 1. CONFIG LOADER ---
def load_games():
    """Scans the data folder and loads all JSON game configs"""
    games = []
    if not os.path.exists(DATA_FOLDER):
        os.makedirs(DATA_FOLDER)
        print(f"Created {DATA_FOLDER}. Please add JSON files!")
        return []

    for filename in os.listdir(DATA_FOLDER):
        if filename.endswith(".json"):
            path = os.path.join(DATA_FOLDER, filename)
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    games.append(data)
            except Exception as e:
                print(f"Failed to load {filename}: {e}")
    return games

# --- 2. MEMORY TOOLS (UDP) ---
def udp_send(command):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.5)
    try:
        sock.sendto(command.encode(), (RETROARCH_IP, RETROARCH_PORT))
        return sock.recvfrom(1024)[0].decode().strip()
    except:
        return None

def write_memory(address_hex_str, value):
    """Effect: Writes a value to RAM (e.g., Giving Health)"""
    # Convert hex string "0x00A5" to integer for formatting
    addr = int(address_hex_str, 16)
    # Command: WRITE_CORE_MEMORY <addr> <byte_value>
    cmd = f"WRITE_CORE_MEMORY {addr:x} {value}" 
    udp_send(cmd)
    print(f"Injecting Memory: {cmd}")

# --- 3. DYNAMIC SHOP UI ---
def run_shop(screen, current_game, player_points):
    """Builds the shop menu based on the CURRENT GAME'S JSON"""
    font = pygame.font.Font(None, 36)
    clock = pygame.time.Clock()
    
    # Extract items for this specific game
    items = current_game.get('shop', [])
    purchased_items = []
    
    running = True
    while running:
        screen.fill((30, 30, 40))
        
        # Header
        title = font.render(f"SHOP: {current_game['meta']['name']}", True, (255, 215, 0))
        pts = font.render(f"Your Points: {player_points}", True, (255, 255, 255))
        screen.blit(title, (50, 50))
        screen.blit(pts, (50, 90))
        
        # Render Dynamic Items
        y = 150
        for index, item in enumerate(items):
            color = (200, 200, 200)
            status = ""
            
            # Check if affordable
            if player_points >= item['cost']:
                color = (255, 255, 255)
            
            # Check if already bought
            if item in purchased_items:
                color = (0, 255, 0)
                status = "[BOUGHT]"
            
            text = f"{index + 1}. {item['name']} ({item['cost']} pts) - {item['description']} {status}"
            label = font.render(text, True, color)
            screen.blit(label, (50, y))
            y += 50
            
        footer = font.render("Press Number to Buy, SPACE to Start", True, (100, 100, 255))
        screen.blit(footer, (50, 600))
        
        pygame.display.flip()
        
        # Input Handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return [], player_points
            
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    running = False
                
                # Check number keys (1-9)
                if event.key >= pygame.K_1 and event.key <= pygame.K_9:
                    idx = event.key - pygame.K_1
                    if idx < len(items):
                        item = items[idx]
                        if player_points >= item['cost'] and item not in purchased_items:
                            player_points -= item['cost']
                            purchased_items.append(item)

    return purchased_items, player_points

# --- 4. GAME LAUNCHER & INJECTOR ---
def play_match(game_config, active_items):
    # A. Setup Launch Arguments
    # Check if any item requires a specific RetroArch config file
    ra_config = "standard.cfg"
    for item in active_items:
        if item['action_type'] == 'retroarch_config':
            ra_config = item['config_file']
            
    # B. Launch RetroArch
    cmd = [
        r"/bin/retroarch",
        "-L", game_config['meta']['core'],
        game_config['meta']['rom'],
        "-c", f"config/{ra_config}"
    ]
    process = subprocess.Popen(cmd)
    
    # C. Wait for Game to Initialize
    print("Waiting for RetroArch core...")
    time.sleep(5) # Give it time to boot
    
    # D. Apply Memory Injections (Buffs)
    for item in active_items:
        if item['action_type'] == 'memory_write':
            # We try to inject a few times to ensure the game RAM is ready
            for _ in range(3): 
                write_memory(item['address'], item['value'])
                time.sleep(0.5)
                
    # E. Referee Loop (simplified)
    # ... Insert Referee Logic Here ...
    
    process.wait()

# --- MAIN BLOCK ---
if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((1024, 768))
    
    all_games = load_games()
    if not all_games:
        print("No games found!")
    else:
        # Example flow: Pick first game, run shop, play
        game = all_games[0] 
        purchases, remaining_points = run_shop(screen, game, 10)
        play_match(game, purchases)