#!/usr/bin/python3
import argparse
import signal
import sys
import melee
import math
import random
import configparser
import keyboard
from keyboard._keyboard_event import KEY_DOWN, KEY_UP, KeyboardEvent

from melee.enums import Action, Button, Character, ProjectileType
import melee.gamestate

# This example program demonstrates how to use the Melee API to run a console,
#   setup controllers, and send button presses over to a console

def check_port(value):
    ivalue = int(value)
    if ivalue < 1 or ivalue > 4:
        raise argparse.ArgumentTypeError("%s is an invalid controller port. \
                                         Must be 1, 2, 3, or 4." % value)
    return ivalue

parser = argparse.ArgumentParser(description='Example of libmelee in action')
parser.add_argument('--port', '-p', type=check_port,
                    help='The controller port (1-4) your AI will play on',
                    default=1)
parser.add_argument('--opponent', '-o', type=check_port,
                    help='The controller port (1-4) the opponent will play on',
                    default=2)
parser.add_argument('--debug', '-d', action='store_true',
                    help='Debug mode. Creates a CSV of all game states')
parser.add_argument('--address', '-a', default="127.0.0.1",
                    help='IP address of Slippi/Wii')
parser.add_argument('--dolphin_path', '-e', default=None,
                    help='The directory where dolphin is')
parser.add_argument('--connect_code', '-t', default="",
                    help='Direct connect code to connect to in Slippi Online')
parser.add_argument('--iso', default=None, type=str,
                    help='Path to melee iso.')
parser.add_argument("--standard_human", '-s', default=False, action='store_true',
                    help='Is the opponent a human? True = use keyboard inputs based on config set by -i.')
parser.add_argument('--config', '-i', type=str,
                    help='The path to a configuration file used for human keyboard input. Requires --standard_human to be True.',
                    default="Hotkeys.ini")

class KBController():
    hotkeys_enabled = False
    hotkeys = {}
    hotkeys_hook = None
    config = configparser.ConfigParser()
    section = "Settings"
    auto_techchase = False
    
    def __init__(self, input_config_path):
        self.cfg_path = input_config_path
        self.config.read(input_config_path)
        # Add a standard smashbox config to the file of the given path
        if not self.config.has_section(self.section):
            print(args.config + " does not contain Settings section!")
            self.create_smashbox_config()

        self.hotkeys_enabled = True
        self.hotkeys_hook = keyboard.hook(self.kb_callback)
        self.hotkeys_state = {}
        
        i = 1
        for input, key in self.config.items(self.section):
            print(key)

            self.hotkeys[key] = i
            self.hotkeys[i] = key
            self.hotkeys_state[i] = False
            i += 1
    
    def create_smashbox_config(self):
        print("Creating standard smashbox Settings.")
        self.config.add_section(self.section)
        # Analog inputs (1-9)
        self.config.set(self.section, 'Analog Up', 'i')
        self.config.set(self.section, 'Analog Left', 'w')
        self.config.set(self.section, 'Analog Down', '3')
        self.config.set(self.section, 'Analog Right', 'r')
        self.config.set(self.section, 'C-Stick Up', '.')
        self.config.set(self.section, 'C-Stick Left', ',')
        self.config.set(self.section, 'C-Stick Down', 'right alt')
        self.config.set(self.section, 'C-Stick Right', '/')
        self.config.set(self.section, 'Lightshield', 'p')
        # Buttons (10-21)
        self.config.set(self.section, 'L', 'o')
        self.config.set(self.section, 'Y', '[')
        self.config.set(self.section, 'R', 'a')
        self.config.set(self.section, 'B', ';')
        self.config.set(self.section, 'A', 'l')
        self.config.set(self.section, 'X', 'k')
        self.config.set(self.section, 'Z', '\'')
        self.config.set(self.section, 'Start', '7')
        self.config.set(self.section, 'D-Pad Up', '4')
        self.config.set(self.section, 'D-Pad Down', '5')
        self.config.set(self.section, 'D-Pad Left', '8')
        self.config.set(self.section, 'D-Pad Right', '6')
        # Analog Modifiers (22-25)
        self.config.set(self.section, 'Analog Mod X1', 'c')
        self.config.set(self.section, 'Analog Mod X2', 'v')
        self.config.set(self.section, 'Analog Mod Y1', 'b')
        self.config.set(self.section, 'Analog Mod Y2', 'space')
        with open(self.cfg_path, 'w') as configfile:
            self.config.write(configfile)

    def toggle_hotkeys(self):
        print("Toggled hotkeys.")
        self.hotkeys_enabled = not self.hotkeys_enabled
        if self.hotkeys_enabled:
            i = 1
            for input, key in self.config.items(self.section):
                self.hotkeys_hook = keyboard.hook(self.kb_callback)
                keyboard.block_key(key)
                i += 1
        else:
            i = 1
            for input, key in self.config.items(self.section):
                self.hotkeys_hook.remove()
                keyboard.unblock_key(key)
                i += 1

    def release_hotkeys(self):
        i = 1
        for input, key in self.config.items(self.section):
            self.hotkeys_state[i] = False
            i += 1

    # Gets opposite analog input
    def get_opposite_key(self, num):
        if num == 1:
            return 3
        if num == 3:
            return 1
        if num == 2:
            return 4
        if num == 4:
            return 2
        if num == 5:
            return 7
        if num == 7:
            return 5
        if num == 6:
            return 8
        if num == 8:
            return 6

    def get_hotkey_button(self, num):
        if num == 10:
            return melee.Button.BUTTON_L
        if num == 11:
            return melee.Button.BUTTON_Y
        if num == 12:
            return melee.Button.BUTTON_R
        if num == 13:
            return melee.Button.BUTTON_B
        if num == 14:
            return melee.Button.BUTTON_A
        if num == 15:
            return melee.Button.BUTTON_X
        if num == 16:
            return melee.Button.BUTTON_Z
        if num == 17:
            return melee.Button.BUTTON_START
        if num == 18:
            return melee.Button.BUTTON_D_UP
        if num == 19:
            return melee.Button.BUTTON_D_DOWN
        if num == 20:
            return melee.Button.BUTTON_D_LEFT
        if num == 21:
            return melee.Button.BUTTON_D_RIGHT

    def hotkey_pressed(self, num):
        if num == 0:
            return
        if self.hotkeys_enabled:
            # Analog inputs
            if num <= 8:
                self.human_tilt_analog(num)
            elif num == 9:
                self.human_press_shoulder()
            # Buttons
            elif num <= 21:
                self.human_button_pressed(num)

    def hotkey_released(self, num):
        if num == 0:
            return
        if self.hotkeys_enabled:
            # Analog inputs
            if num <= 8:
                self.human_untilt_analog(num)
            elif num == 9:
                self.human_release_shoulder()
            # Buttons
            elif num <= 21:
                self.human_button_released(num)

    def get_tilt(self, num):
        x = 0.5
        y = 0.5
        
        if num == 0:
            return (x, y)
        
        opposite_key = self.get_opposite_key(num)
        
        # print("Current tilt analog values: (" + str(tilt[0]) + ", " + str(tilt[1]) + ")")

        if self.hotkeys_state[num]:
            if self.hotkeys_state[opposite_key]:
                # left/right
                if (num == 2 or num == 6 or
                    num == 4 or num == 8):
                    x = 0.5
                # up/down
                if (num == 1 or num == 5 or
                    num == 3 or num == 7):
                    y = 0.5

        # up
        if (num == 1):
            if (self.hotkeys_state[2] and
                not self.hotkeys_state[self.get_opposite_key(2)]):
                x = -0.0375
            if (self.hotkeys_state[4] and
                not self.hotkeys_state[self.get_opposite_key(4)]):
                x = 1.0425
            if (self.hotkeys_state[num]):
                y = 1.0375
        if (num == 5):
            if (self.hotkeys_state[6] and
                not self.hotkeys_state[self.get_opposite_key(6)]):
                x = -0.0375
            if (self.hotkeys_state[8] and
                not self.hotkeys_state[self.get_opposite_key(8)]):
                x = 1.0425
            if (self.hotkeys_state[num]):
                y = 1.0375
        
        # down
        if (num == 3):
            if (self.hotkeys_state[2] and
                not self.hotkeys_state[self.get_opposite_key(2)]):
                x = -0.0375
            if (self.hotkeys_state[4] and
                not self.hotkeys_state[self.get_opposite_key(4)]):
                x = 1.0425
            if (self.hotkeys_state[num]):
                y = -0.0475
        if (num == 7):
            if (self.hotkeys_state[6] and
                not self.hotkeys_state[self.get_opposite_key(6)]):
                x = -0.0375
            if (self.hotkeys_state[8] and
                not self.hotkeys_state[self.get_opposite_key(8)]):
                x = 1.0425
            if (self.hotkeys_state[num]):
                y = -0.0475
        
        # left
        if (num == 2):
            if (self.hotkeys_state[1] and
                not self.hotkeys_state[self.get_opposite_key(1)]):
                y = 1.0375
            if (self.hotkeys_state[3] and
                not self.hotkeys_state[self.get_opposite_key(3)]):
                y = -0.0475
            if (self.hotkeys_state[num]):
                x = -0.0375
        if (num == 6):
            if (self.hotkeys_state[5] and
                not self.hotkeys_state[self.get_opposite_key(5)]):
                y = 1.0375
            if (self.hotkeys_state[7] and
                not self.hotkeys_state[self.get_opposite_key(7)]):
                y = -0.0475
            if (self.hotkeys_state[num]):
                x = -0.0375
            
        # right
        if (num == 4):
            if (self.hotkeys_state[1] and
                not self.hotkeys_state[self.get_opposite_key(1)]):
                y = 1.0375
            if (self.hotkeys_state[3] and
                not self.hotkeys_state[self.get_opposite_key(3)]):
                y = -0.0475
            if (self.hotkeys_state[num]):
                x = 1.0425
        if (num == 8):
            if (self.hotkeys_state[5] and
                not self.hotkeys_state[self.get_opposite_key(5)]):
                y = 1.0375
            if (self.hotkeys_state[7] and
                not self.hotkeys_state[self.get_opposite_key(7)]):
                y = -0.0475
            if (self.hotkeys_state[num]):
                x = 1.0425

        return self.apply_tilt_mod(x, y)
    
    def apply_tilt_mod(self, x, y):
        mod_x1 = self.hotkeys_state[22]
        mod_x2 = self.hotkeys_state[23]
        mod_y1 = self.hotkeys_state[24]
        mod_y2 = self.hotkeys_state[25]
        
        if not x == 0.5:
            if x > 0.5:
                if mod_x1 and mod_x2:
                    x -= 0.085
                elif mod_x1:
                    x -= 0.375
                elif mod_x2:
                    x -= 0.2
            if x < 0.5:
                if mod_x1 and mod_x2:
                    x += 0.08
                elif mod_x1:
                    x += 0.37
                elif mod_x2:
                    x += 0.195

        if not y == 0.5:
            if y > 0.5:
                if mod_y1 and mod_y2:
                    y -= 0.085
                elif mod_y1:
                    y -= 0.375
                elif mod_y2:
                    y -= 0.21
            if y < 0.5:
                if mod_y1 and mod_y2:
                    y += 0.08
                elif mod_y1:
                    y += 0.37
                elif mod_y2:
                    y += 0.21

        return (x, y)

    def human_button_pressed(self, num):
        controller.press_button(self.get_hotkey_button(num))

    def human_button_released(self, num):
        controller.release_button(self.get_hotkey_button(num))

    def human_tilt_analog(self, num):
        button, tilt = self.get_stick(num)
        opposite_key = self.get_opposite_key(num)

        # print("Current tilt analog values: (" + str(tilt[0]) + ", " + str(tilt[1]) + ")")

        newtilt = self.get_tilt(num)
        # print("New tilt analog values: (" + str(newtilt[0]) + ", " + str(newtilt[1]) + ")")

        # Cancel opposites
        if (self.hotkeys_state[opposite_key]):
            # up/down
            if (num == 1 or num == 5 or
                num == 3 or num == 7):
                tilt = (tilt[0], 0.5)
            # left/right
            if (num == 2 or num == 6 or
                num == 4 or num == 8):
                tilt = (0.5, tilt[1])
            
            controller.tilt_analog(button, tilt[0], tilt[1])
            return

        tilt = newtilt

        # print("Attempted to tilt analog using these values: (" + str(tilt[0]) + ", " + str(tilt[1]) + ")")
        controller.tilt_analog(button, tilt[0], tilt[1])

    def human_untilt_analog(self, num):
        button, tilt = self.get_stick(num)
        opposite_key = self.get_opposite_key(num)
        
        #print("Current tilt analog values: (" + str(tilt[0]) + ", " + str(tilt[1]) + ")")
        
        if (self.hotkeys_state[opposite_key]):
            self.human_tilt_analog(opposite_key)
            return
        
        tilt = self.get_tilt(num)
        # up/down
        if (num == 1 or num == 5 or
            num == 3 or num == 7):
            tilt = (tilt[0], 0.5)
        # left/right
        elif (num == 2 or num == 6 or
              num == 4 or num == 8):
            tilt = (0.5, tilt[1])
         
        #print("New tilt analog values: (" + str(tilt[0]) + ", " + str(tilt[1]) + ")")

        controller.tilt_analog(button, tilt[0], tilt[1])
    
    def get_stick(self, num):
        button = melee.Button.BUTTON_MAIN
        tilt = controller.current.main_stick
        if num >= 5 and num <= 8:
            button = melee.Button.BUTTON_C
            tilt = controller.current.c_stick
        return (button, tilt)
    
    def human_press_shoulder(self):
        controller.press_shoulder(melee.Button.BUTTON_L, 0.3325)
        
    def human_release_shoulder(self):
        controller.press_shoulder(melee.Button.BUTTON_L, 0.0)
    
    def kb_callback(self, event):
        key = event.name
        if key in self.hotkeys:
            num = self.hotkeys[key]
            self.hotkeys_state[num] = (event.event_type == KEY_DOWN)
            if (event.event_type == KEY_DOWN):
                self.hotkey_pressed(num)
            else:
                self.hotkey_released(num)
                
            # Always update analog inputs when modifier keys are pressed/released
            if num >= 22 and num <= 25:
                for i in range(1, 9):
                    if self.hotkeys_state[i]:
                        self.human_tilt_analog(i)

def player_damaged(playerstate):
    if (playerstate.hitstun_frames_left or
        playerstate.hitlag_left and
        (playerstate.action == melee.Action.DAMAGE_HIGH_1 or
        playerstate.action == melee.Action.DAMAGE_HIGH_2 or
        playerstate.action == melee.Action.DAMAGE_HIGH_3 or
        playerstate.action == melee.Action.DAMAGE_NEUTRAL_1 or
        playerstate.action == melee.Action.DAMAGE_NEUTRAL_2 or
        playerstate.action == melee.Action.DAMAGE_NEUTRAL_3 or
        playerstate.action == melee.Action.DAMAGE_LOW_1 or
        playerstate.action == melee.Action.DAMAGE_LOW_2 or
        playerstate.action == melee.Action.DAMAGE_LOW_3 or
        playerstate.action == melee.Action.DAMAGE_AIR_1 or
        playerstate.action == melee.Action.DAMAGE_AIR_2 or
        playerstate.action == melee.Action.DAMAGE_AIR_3 or
        playerstate.action == melee.Action.DAMAGE_SCREW or
        playerstate.action == melee.Action.DAMAGE_SCREW_AIR or
        playerstate.action == melee.Action.DAMAGE_FLY_HIGH or
        playerstate.action == melee.Action.DAMAGE_FLY_NEUTRAL or
        playerstate.action == melee.Action.DAMAGE_FLY_LOW or
        playerstate.action == melee.Action.DAMAGE_FLY_TOP or
        playerstate.action == melee.Action.DAMAGE_FLY_ROLL or
        playerstate.action == melee.Action.SHIELD_STUN or
        playerstate.action == melee.Action.LYING_GROUND_UP_HIT or
        playerstate.action == melee.Action.DAMAGE_GROUND or
        playerstate.action == melee.Action.DAMAGE_BIND)):
        return True

    return False

def sq_distance(x1, x2):
    return sum(map(lambda x: (x[0] - x[1])**2, zip(x1, x2)))

"""Returns a point in the list of points that is closest to the given point."""
def get_min_point(point, points):
    dists = list(map(lambda x: sq_distance(x, point), points))
    return points[dists.index(min(dists))]

def append_if_valid(arr, check_arr):
    if not check_arr is None:
        arr.append(check_arr)

args = parser.parse_args()

# This logger object is useful for retroactively debugging issues in your bot
#   You can write things to it each frame, and it will create a CSV file describing the match
log = None
if args.debug:
    log = melee.Logger()

opponent_type = melee.ControllerType.GCN_ADAPTER
if args.standard_human:
    opponent_type = melee.ControllerType.STANDARD

# Create our Console object.
#   This will be one of the primary objects that we will interface with.
#   The Console represents the virtual or hardware system Melee is playing on.
#   Through this object, we can get "GameState" objects per-frame so that your
#       bot can actually "see" what's happening in the game
console = melee.Console(path=args.dolphin_path,
                        slippi_address=args.address,
                        logger=log)

# Create our Controller object
#   The controller is the second primary object your bot will interact with
#   Your controller is your way of sending button presses to the game, whether
#   virtual or physical.
controller = melee.Controller(console=console,
                              port=args.port,
                              type=melee.ControllerType.STANDARD)

# This isn't necessary, but makes it so that Dolphin will get killed when you ^C
def signal_handler(sig, frame):
    console.stop()
    if args.debug:
        log.writelog()
        print("") #because the ^C will be on the terminal
        print("Log file created: " + log.filename)
    print("Shutting down cleanly...")
    sys.exit(0)

def main():
    initialized = False
        
    last_frame = 0
    last_input_frame = 0
    hit_frame = 0
    last_sdi_input = (0.5, 0.5)
    local_player = (0, None)
    tech_lockout = 0
    meteor_jump_lockout = 0
    ledge_grab_count = 0
    meteor_ff_lockout = 0
    powershielded_last = False
    opponents = []
    current_opponent = (0, None)
    
    signal.signal(signal.SIGINT, signal_handler)

    # Run the console
    console.run(iso_path=args.iso)

    # Connect to the console
    print("Connecting to console...")
    if not console.connect():
        print("ERROR: Failed to connect to the console.")
        sys.exit(-1)
    print("Console connected")

    # Plug our controller in
    #   Due to how named pipes work, this has to come AFTER running dolphin
    #   NOTE: If you're loading a movie file, don't connect the controller,
    #   dolphin will hang waiting for input and never receive it
    print("Connecting controller to console...")
    if not controller.connect():
        print("ERROR: Failed to connect the controller.")
        sys.exit(-1)
    print("Controller connected")

    costume = 0
    framedata = melee.framedata.FrameData()
    print("Initial costume: " + str(costume))
    
    if args.standard_human:
        #Read in dolphin's controller config file
        kb_controller = KBController(args.config)
    
    # Main loop
    while True:

        # "step" to the next frame
        gamestate = console.step()
        if gamestate is None:
            initialized = False
            continue

        # The console object keeps track of how long your bot is taking to process frames
        #   And can warn you if it's taking too long
        if console.processingtime * 1000 > 12:
            print("WARNING: Last frame took " + str(console.processingtime*1000) + "ms to process.")

        # What menu are we in?
        if gamestate.menu_state in [melee.Menu.IN_GAME, melee.Menu.SUDDEN_DEATH]:
            if not initialized:
                # print("Initializing stage parameters.")
                stage_leftplatform_positions = melee.stages.left_platform_position(gamestate)
                stage_rightplatform_positions = melee.stages.right_platform_position(gamestate)
                stage_topplatform_positions = melee.stages.top_platform_position(gamestate)

                """Edge order: main, left, right, top"""
                stage_offstage_leftedge = [melee.stages.EDGE_POSITION[gamestate.stage], 0]
                stage_offstage_rightedge = [melee.stages.EDGE_POSITION[gamestate.stage], 0]
                stage_ground_leftedge = [-melee.stages.EDGE_GROUND_POSITION[gamestate.stage], 0]
                stage_ground_rightedge = [melee.stages.EDGE_GROUND_POSITION[gamestate.stage], 0]
                all_edges = [stage_ground_leftedge, stage_ground_rightedge, stage_offstage_leftedge, stage_offstage_rightedge]
                if not stage_leftplatform_positions is None:
                    stage_leftplatform_leftedge = [stage_leftplatform_positions[1], stage_leftplatform_positions[0]]
                    stage_leftplatform_rightedge = [stage_leftplatform_positions[2], stage_leftplatform_positions[0]]
                    append_if_valid(all_edges, stage_leftplatform_leftedge)
                    append_if_valid(all_edges, stage_leftplatform_rightedge)
                if not stage_rightplatform_positions is None:
                    stage_rightplatform_leftedge = [stage_rightplatform_positions[1], stage_rightplatform_positions[0]]
                    stage_rightplatform_rightedge = [stage_rightplatform_positions[2], stage_rightplatform_positions[0]]
                    append_if_valid(all_edges, stage_rightplatform_leftedge)
                    append_if_valid(all_edges, stage_rightplatform_rightedge)
                if not stage_topplatform_positions is None:
                    stage_topplatform_leftedge = [stage_topplatform_positions[1], stage_topplatform_positions[0]]
                    stage_topplatform_rightedge = [stage_topplatform_positions[2], stage_topplatform_positions[0]]
                    append_if_valid(all_edges, stage_topplatform_leftedge)
                    append_if_valid(all_edges, stage_topplatform_rightedge)
                initialized = True
            
            # Discover our target player
            if not local_player[1] or len(opponents) == 0:
                if not local_player[1]:
                    local_player = get_target_player(gamestate, 'LIZA#594')
                    if not local_player[1]:
                        print("Searching by character...")
                        local_port = melee.gamestate.port_detector(gamestate, Character.ROY, 0)
                        local_player = (local_port, gamestate.players[local_port])
                        if local_player[1]:
                            print("Found player:", local_player[0])
                if len(opponents) == 0:
                    opponents = get_opponents(gamestate, local_player[0])
            else:
                # Figure out who our opponent is
                #   Opponent is the closest player that is a different costume
                if len(opponents) > 1:
                    nearest_dist = 1000
                    nearest_player = None
                    for opponent in opponents:
                        xdist = local_player[1].position.x - opponent[1].position.x
                        ydist = local_player[1].position.y - opponent[1].position.y
                        dist = math.sqrt((xdist**2) + (ydist**2))
                        if dist < nearest_dist:
                            nearest_dist = dist
                            nearest_player = opponent
                    current_opponent = nearest_player
                    gamestate.distance = nearest_dist
                else:
                    current_opponent = opponents[0]

                # Pick the right climber to be the opponent
                if current_opponent[1].nana is not None:
                    xdist = current_opponent[1].nana.position.x - local_player[1].position.x
                    ydist = current_opponent[1].nana.position.y - local_player[1].position.y
                    dist = math.sqrt((xdist**2) + (ydist**2))
                    if dist < gamestate.distance:
                        gamestate.distance = dist
                        popo = current_opponent[1]
                        current_opponent = (current_opponent[0], current_opponent[1].nana)
                        current_opponent[1].nana = popo

                knownprojectiles = []
                for projectile in gamestate.projectiles:
                    # Held turnips and link bombs
                    if projectile.type in [ProjectileType.TURNIP, ProjectileType.LINK_BOMB, ProjectileType.YLINK_BOMB]:
                        if projectile.subtype in [0, 4, 5]:
                            continue
                    # Charging arrows
                    if projectile.type in [ProjectileType.YLINK_ARROW, ProjectileType.FIRE_ARROW, \
                        ProjectileType.LINK_ARROW, ProjectileType.ARROW]:
                        if projectile.speed.x == 0 and projectile.speed.y == 0:
                            continue
                    # Pesticide
                    if projectile.type == ProjectileType.PESTICIDE:
                        continue
                    # Ignore projectiles owned by us
                    if projectile.owner == local_player[0]:
                        continue
                    if projectile.type not in [ProjectileType.UNKNOWN_PROJECTILE, ProjectileType.PEACH_PARASOL, \
                        ProjectileType.FOX_LASER, ProjectileType.SHEIK_CHAIN, ProjectileType.SHEIK_SMOKE]:
                        knownprojectiles.append(projectile)
                gamestate.projectiles = knownprojectiles

                # Yoshi shield animations are weird. Change them to normal shield
                if current_opponent[1].character == Character.YOSHI:
                    if current_opponent[1].action in [melee.Action.NEUTRAL_B_CHARGING, melee.Action.NEUTRAL_B_FULL_CHARGE, melee.Action.LASER_GUN_PULL]:
                        current_opponent[1].action = melee.Action.SHIELD

                # Tech lockout
                if local_player[1].controller_state.button[Button.BUTTON_L]:
                    tech_lockout = 40
                else:
                    tech_lockout -= 1
                    tech_lockout = max(0, tech_lockout)

                # Jump meteor cancel lockout
                if local_player[1].controller_state.button[Button.BUTTON_Y] or \
                    local_player[1].controller_state.main_stick[1] > 0.8:
                    meteor_jump_lockout = 40
                else:
                    meteor_jump_lockout -= 1
                    meteor_jump_lockout = max(0, meteor_jump_lockout)

                # Firefox meteor cancel lockout
                if local_player[1].controller_state.button[Button.BUTTON_B] and \
                    local_player[1].controller_state.main_stick[1] > 0.8:
                    meteor_ff_lockout = 40
                else:
                    meteor_ff_lockout -= 1
                    meteor_ff_lockout = max(0, meteor_ff_lockout)

                # Keep a ledge grab count
                if current_opponent[1].action == Action.EDGE_CATCHING and current_opponent[1].action_frame == 1:
                    ledge_grab_count += 1
                if current_opponent[1].on_ground:
                    ledge_grab_count = 0
                if gamestate.frame == -123:
                    ledge_grab_count = 0
                gamestate.custom["ledge_grab_count"] = ledge_grab_count
                gamestate.custom["tech_lockout"] = tech_lockout
                gamestate.custom["meteor_jump_lockout"] = meteor_jump_lockout
                gamestate.custom["meteor_ff_lockout"] = meteor_ff_lockout

                if local_player[1].action in [Action.SHIELD_REFLECT, Action.SHIELD_STUN]:
                    if local_player[1].is_powershield:
                        powershielded_last = True
                    elif local_player[1].hitlag_left > 0:
                        powershielded_last = False

                gamestate.custom["powershielded_last"] = powershielded_last

                # Let's treat Counter-Moves as invulnerable. So we'll know to not attack during that time
                countering = False
                if current_opponent[1].character in [Character.ROY, Character.MARTH]:
                    if current_opponent[1].action in [Action.MARTH_COUNTER, Action.MARTH_COUNTER_FALLING]:
                        # We consider Counter to start a frame early and a frame late
                        if 4 <= current_opponent[1].action_frame <= 30:
                            countering = True
                if current_opponent[1].character == Character.PEACH:
                    if current_opponent[1].action in [Action.UP_B_GROUND, Action.DOWN_B_STUN]:
                        if 4 <= current_opponent[1].action_frame <= 30:
                            countering = True
                if countering:
                    current_opponent[1].invulnerable = True
                    current_opponent[1].invulnerability_left = max(29 - current_opponent[1].action_frame, current_opponent[1].invulnerability_left)

                # Platform drop is fully actionable. Don't be fooled
                if current_opponent[1].action == Action.PLATFORM_DROP:
                    current_opponent[1].hitstun_frames_left = 0
                    
                player_velocity_total_y = local_player[1].speed_y_self + local_player[1].speed_y_attack
                # Determine if opponent will hit us
                if framedata.in_range(current_opponent[1], local_player[1], gamestate.stage) != 0:
                    controller.simple_press(0.5, -0.0475, Button.BUTTON_B)
        
                last_frame = gamestate.frame

            if log:
                log.logframe(gamestate)
                log.writeframe()
        else:
            initialized = False
            local_player = (0, None)
            current_opponent = (0, None)
            opponents = []
            
            # If we're not in game, don't log the frame
            if log:
                log.skipframe()

def get_target_player(gamestate, target):
    # Discover our target player
    for key, player in gamestate.players.items():
        if player.connectCode == target:
            print("Found player:", player.connectCode)
            return (key, player)
    print("Unable to find player:", target)
    return (0, None)

def get_opponents(gamestate, target_port):
    # Discover opponents of the target player
    opponents = []
    for key, player in gamestate.players.items():
        if key != target_port:
            opponents.append((key, player))
            print("Found opponent in port:", key)
    if len(opponents) == 0:
        print("Unable to find opponents of port:", target_port)
    return opponents

if __name__ == '__main__':
    main()