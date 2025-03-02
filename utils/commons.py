import math

import melee
from melee.enums import Action, Analog, Button, Character


def sq_distance(x1, x2):
    return sum(map(lambda x: (x[0] - x[1])**2, zip(x1, x2)))

"""Returns a point in the list of points that is closest to the given point."""
def get_min_point(point, points):
    dists = list(map(lambda x: sq_distance(x, point), points))
    return points[dists.index(min(dists))]

def append_if_valid(arr, check_arr):
    if not check_arr is None:
        arr.append(check_arr)
        
def get_target_player(gamestate, target):
    # Discover our target player
    for key, player in gamestate.players.items():
        if player.connectCode == target:
            print("Found player:", player.connectCode)
            return key
    print("Unable to find player:", target)
    return 0

def get_opponents(gamestate, target_port):
    # Discover opponents of the target player
    opponent_ports = []
    for key, player in gamestate.players.items():
        same_team = gamestate.is_teams and player.team_id == gamestate.players[target_port].team_id
        if key != target_port and not same_team:
            opponent_ports.append(key)
            print("Found opponent in port:", key)
    if len(opponent_ports) == 0:
        print("Unable to find opponents of port:", target_port)
    return opponent_ports

def get_closest_opponent(gamestate, player, opponent_ports):
    opponent_port = 0
    while opponent_port == 0:
        if len(opponent_ports) == 0:
            break
        
        # Figure out who our opponent is
        #   Opponent is the closest player that is a different costume
        if len(opponent_ports) >= 1:
            nearest_dist = 1000
            nearest_port = 0
            # Validate before indexing
            for port in opponent_ports:
                if port not in gamestate.players:
                    opponent_ports.remove(port)
                    
            for port in opponent_ports:
                opponent = gamestate.players[port]
                xdist = player.x - opponent.x
                ydist = player.y - opponent.y
                dist = math.sqrt((xdist**2) + (ydist**2))
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest_port = port
            gamestate.distance = nearest_dist
            opponent_port = nearest_port
        elif len(opponent_ports) == 1:
            opponent_port = opponent_ports[0]
        else:
            print("Failed to find opponent")
            opponent_port = 0
            break
        
        # Verify if valid port
        if opponent_port not in gamestate.players:
            if opponent_port in opponent_ports:
                opponent_ports.remove(opponent_port)
        else:
            break
    return opponent_port

def safe_counter(player):
    if not player:
        return False
    
    if not player.off_stage:
        return True
    elif player.y > 10:
        return True
    
    return False

# Returns -1, 0, or 1 depending on if the player is on the left, in the middle, or right of the stage
def get_relative_stage_position(player, stage_bounds):
    if player.x < stage_bounds[0]:
        return -1
    if player.x > stage_bounds[1]:
        return 1
    return 0

def get_controller_tilt(type, controller):
    tilt = (0, 0)
    if type == Button.BUTTON_MAIN:
        tilt = controller.current.main_stick
    else:
        tilt = controller.current.c_stick
    return tilt

def update_player_info(gamestate, local_port, opponent_ports, alive, costume, character):
    if local_port not in gamestate.players or len(opponent_ports) == 0 and alive:
        local_port = get_target_player(gamestate, 'SOUL#127') or melee.gamestate.port_detector(gamestate, character, costume)
        if local_port not in gamestate.players:
            print("Failed to find player.")
            alive = False
        else:
            print("Found player:", local_port)
            opponent_ports = get_opponents(gamestate, local_port)
    
    if alive and opponent_ports:
        opponent_port = get_closest_opponent(gamestate, gamestate.players[local_port], opponent_ports)
    else:
        opponent_port = 0

    return local_port, opponent_ports, opponent_port, alive

def get_slide_pos(player, framedata, time=1):
    # Calculate location after sliding
    move_location = [player.x, player.y]
    speed_x = player.speed_x_attack + player.speed_ground_x_self
    if speed_x > 0:
        slide_dist = framedata.slide_distance(player, speed_x, time)
        move_location = [player.x + slide_dist, player.y]
        
    return move_location

def get_fly_pos(player, gamestate, framedata, time=1, y_margin=0.0, collide_below_platforms=False):
    # Calculate location during flight
    if framedata.is_hit(player) or not player.on_ground:
        target_pos_x, target_pos_y, _ = framedata.project_hit_location(gamestate, player, time, y_margin, collide_below_platforms)
        return [target_pos_x, target_pos_y]
    else:
        return [player.x, player.y]

def calculate_wavedash_x(start_x, target_x, facing, optimal_distance=10):
    dx = abs(start_x - target_x)
    percentage_wavedash = (dx / optimal_distance)
    wavedash_x = 1.3 if facing else -0.3
    offset_x = -0.625 if facing else 0.625
    wavedash_x += (offset_x * (1 - percentage_wavedash))
    return wavedash_x

def check_projectile_collision(player, opponent, projectile, online_delay=2):
    if projectile.type == melee.ProjectileType.SAMUS_GRAPPLE_BEAM and opponent.on_ground:
        return False
    if projectile.type in [melee.ProjectileType.SHEIK_SMOKE, melee.ProjectileType.SHEIK_CHAIN ]:
        return False
    # Missles and needles that aren't moving are actually already exploded. Ignore them
    if projectile.type in [melee.ProjectileType.SAMUS_MISSLE, melee.ProjectileType.NEEDLE_THROWN] and (-0.01 < projectile.speed.x < 0.01):
        return False

    if projectile.type == melee.ProjectileType.SAMUS_BOMB and (-0.01 < projectile.speed.y < 0.01):
        return False

    size = 10
    if projectile.type in [melee.ProjectileType.PIKACHU_THUNDERJOLT_1, melee.ProjectileType.PICHU_THUNDERJOLT_1]:
        size = 18
    if projectile.type == melee.ProjectileType.NEEDLE_THROWN:
        size = 12
    if projectile.type in [melee.ProjectileType.PIKACHU_THUNDER, melee.ProjectileType.PICHU_THUNDER]:
        size = 30
    if projectile.type == melee.ProjectileType.TURNIP:
        size = 12
    # Your hitbox is super distorted when edge hanging. Give ourselves more leeway here
    if player.action == Action.EDGE_HANGING:
        size *= 2

    # If the projectile is above us, then increase its effective size.
    #   Since our hurtbox extends upwards more that way
    if abs(player.position.x - projectile.position.x) < 15 and abs(projectile.speed.x) < 1:
        size += 15

    # Is this about to hit us in the next frame?
    proj_x, proj_y = projectile.position.x, projectile.position.y
    check_frames = online_delay + 2
    if opponent.character == Character.SAMUS:
        check_frames += 2
    for i in range(0, online_delay + 2):
        proj_x += projectile.speed.x
        proj_y += projectile.speed.y
        player_y = player.position.y
        player_x = player.position.x + player.speed_ground_x_self
        # This is a bit hacky, but it's easiest to move our "center" up a little for the math
        if player.on_ground:
            player_y += 8
        distance = math.sqrt((proj_x - player_x)**2 + (proj_y - player_y)**2)
        if distance < size:
            return True
    
    return False

def can_waveland(player, framedata):
    return (
        not framedata.is_attacking(player) and
        (framedata.is_falling(player) or framedata.is_jumping(player)) and
        player.y > -2.5
    )
    
def can_airdash(player):
    """Whether the player can perform an aerial dash.
    This requires a character with a teleport special move.
    """
    return (player.character == Character.PICHU or
            player.character == Character.PIKACHU or
            player.character == Character.MEWTWO or
            player.character == Character.ZELDA)

def can_airturn(player):
    """Whether the player can perform an aerial turnaround.
    This requires a character with a chargeable special attack.
    """
    return (player.character == Character.DK or
            player.character == Character.MEWTWO or
            player.character == Character.SHEIK)
    
def initialize_game_state(gamestate):
    stage = gamestate.stage
    if stage == melee.Stage.NO_STAGE:
        return None, None, None, None, None
    
    ground_left = (-melee.stages.EDGE_GROUND_POSITION[stage], 0)
    ground_right = (melee.stages.EDGE_GROUND_POSITION[stage], 0)
    stage_bounds_ground = (ground_left, ground_right)
    offstage_left = (-melee.stages.EDGE_POSITION[stage], 0)
    offstage_right = (melee.stages.EDGE_POSITION[stage], 0)
    stage_bounds_air = (offstage_left, offstage_right)
    
    left_plat = melee.stages.left_platform_position(gamestate)
    right_plat = melee.stages.right_platform_position(gamestate)
    top_plat = melee.stages.top_platform_position(gamestate)
    if not left_plat is None:
        left_plat_left = (left_plat[1], left_plat[0])
        left_plat_right = (left_plat[2], left_plat[0])
    if not right_plat is None:
        right_plat_left = (right_plat[1], right_plat[0])
        right_plat_right = (right_plat[2], right_plat[0])
    if not top_plat is None:
        top_plat_left = (top_plat[1], top_plat[0])
        top_plat_right = (top_plat[2], top_plat[0])
    
    left_plat_bounds = (left_plat_left, left_plat_right)
    right_plat_bounds = (right_plat_left, right_plat_right)
    top_plat_bounds = (top_plat_left, top_plat_right)
    
    return stage_bounds_ground, stage_bounds_air, left_plat_bounds, right_plat_bounds, top_plat_bounds