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
    # hotkeys_hook = None
    config = configparser.ConfigParser()
    section = "Settings"
    inputs_reserved = False
    
    def __init__(self, input_config_path):
        self.cfg_path = input_config_path
        self.config.read(input_config_path)
        # Add a standard smashbox config to the file of the given path
        if not self.config.has_section(self.section):
            print(args.config + " does not contain Settings section!")
            self.create_smashbox_config()

        self.toggle_hotkeys()
        # self.hotkeys_hook = keyboard.hook(self.kb_callback)
        self.hotkeys_state = {}
        
        i = 1
        for input, key in self.config.items(self.section):
            print(key)

            parsed_key = keyboard.parse_hotkey(key)
            self.hotkeys[parsed_key] = i
            self.hotkeys[i] = parsed_key
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
        # Misc Buttons (26+)
        self.config.set(self.section, 'Toggle Hotkeys', 'shift+alt+s')
        self.config.set(self.section, 'Turbo Modifier', 'shift')
        with open(self.cfg_path, 'w') as configfile:
            self.config.write(configfile)

    def toggle_hotkeys(self):
        print("Toggled hotkeys.")
        self.hotkeys_enabled = not self.hotkeys_enabled
        if self.hotkeys_enabled:
            # self.hotkeys_hook = keyboard.hook(self.kb_callback)
            i = 1
            for input, key in self.config.items(self.section):
                keyboard.add_hotkey(key, self.kb_press_callback, key, True)
                keyboard.add_hotkey(key, self.kb_release_callback, key, suppress=True, trigger_on_release=True)
                # keyboard.hook_key(key, self.kb_callback, True)
                i += 1
        else:
            # self.hotkeys_hook = keyboard.unhook(self.hotkeys_hook)
            # self.hotkeys_hook = None
            i = 1
            for input, key in self.config.items(self.section):
                # Skip the toggle hotkey
                if i == 26:
                    continue
                keyboard.remove_hotkey(key)
                # keyboard.unhook_key(key)
                # keyboard.unblock_key(key)
                i += 1

    def release_hotkeys(self):
        i = 1
        for input, key in self.config.items(self.section):
            self.hotkeys_state[i] = False
            self.hotkey_released(i)
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
            elif num == 26:
                self.toggle_hotkeys()
            elif num == 27:
                self.release_hotkeys()

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
    
    def kb_press_callback(self, key):
        if self.inputs_reserved:
            self.release_hotkeys()
            return
        
        parsed_key = keyboard.parse_hotkey(key)
        for i in range(1, len(self.hotkeys_state)):
            first_code = self.hotkeys[i][0][0][0]
            pressed_code = parsed_key[0][0][0]
            if parsed_key == self.hotkeys[i] or first_code == pressed_code:
                num = self.hotkeys[self.hotkeys[i]]
                self.hotkeys_state[num] = True
                self.hotkey_pressed(num)
                
                # Always update analog inputs when modifier keys are pressed/released
                if num >= 22 and num <= 25:
                    for i in range(1, 9):
                        self.human_tilt_analog(i)
    
    def kb_release_callback(self, key):
        if self.inputs_reserved:
            self.release_hotkeys()
            return
        
        parsed_key = keyboard.parse_hotkey(key)
        for i in range(1, len(self.hotkeys_state)):
            first_code = self.hotkeys[i][0][0][0]
            pressed_code = parsed_key[0][0][0]
            if parsed_key == self.hotkeys[i] or first_code == pressed_code:
                num = self.hotkeys[self.hotkeys[i]]
                self.hotkeys_state[num] = False
                self.hotkey_released(num)

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
    
def in_safezone(player, stage_boundary):
    if not player:
        return False
    
    left_bound = stage_boundary[0][0]
    right_bound = stage_boundary[1][0]
    # We are safe if we are far enough above stage where attacks are safe to do
    # Or, we are within the bounds of the stage
    in_bounds = player.x > left_bound and player.x < right_bound
    safe_height = player.y > 6
    if (in_bounds or safe_height):
        return True
    
    return False
    
def get_counter_inputs(player):
    character = player.character
    if character == Character.ROY or character == Character.MARTH:
        return [Button.BUTTON_B], (0.5, -0.0475)
    # Character.PEACH
    return [Button.BUTTON_B], (0.5, 0.5)

def get_tilt(type):
    tilt = (0, 0)
    if type == melee.Button.BUTTON_MAIN:
        tilt = controller.current.main_stick
    else:
        tilt = controller.current.c_stick
    return tilt

def main():
    initialized = False
    move_queued = 0
    # First array for buttons, two tuples for main and c sticks
    new_inputs = [[], None, None]
    target_frame = 0
    last_sdi_input = (0.5, 0.5)
    local_port = 0
    tech_lockout = 0
    meteor_jump_lockout = 0
    ledge_grab_count = 0
    meteor_ff_lockout = 0
    powershielded_last = False
    opponent_ports = []
    opponent_port = 0
    
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
            local_player_invalid = local_port not in gamestate.players
            if local_player_invalid or len(opponent_ports) == 0:
                if local_player_invalid:
                    local_port = get_target_player(gamestate, 'SOUL#127')
                    local_player_invalid = local_port not in gamestate.players
                    if local_player_invalid:
                        print("Searching by character...")
                        local_port = melee.gamestate.port_detector(gamestate, Character.MARTH, costume)
                        local_player_invalid = local_port not in gamestate.players
                        if not local_player_invalid:
                            print("Found player:", local_port)
                        else:
                            print("Failed to find player.")
                            # If the discovered port was unsure, reroll our costume for next time
                            costume = random.randint(0, 4)
                if len(opponent_ports) == 0:
                    opponent_ports = get_opponents(gamestate, local_port)
            else:
                # Figure out who our opponent is
                #   Opponent is the closest player that is a different costume
                if len(opponent_ports) > 1:
                    nearest_dist = 1000
                    nearest_port = 0
                    # Validate first
                    for port in opponent_ports:
                        if port not in gamestate.players:
                            opponent_ports.remove(port)
                            
                    for port in opponent_ports:
                        opponent = gamestate.players[port]
                        xdist = gamestate.players[local_port].position.x - opponent.position.x
                        ydist = gamestate.players[local_port].position.y - opponent.position.y
                        dist = math.sqrt((xdist**2) + (ydist**2))
                        if dist < nearest_dist:
                            nearest_dist = dist
                            nearest_port = port
                    opponent_port = nearest_port
                    gamestate.distance = nearest_dist
                elif len(opponent_ports) == 1:
                    opponent_port = opponent_ports[0]
                else:
                    print("Failed to find opponent")
                    continue

                # Pick the right climber to be the opponent
                if gamestate.players[opponent_port].nana is not None:
                    xdist = gamestate.players[opponent_port].nana.position.x - gamestate.players[local_port].position.x
                    ydist = gamestate.players[opponent_port].nana.position.y - gamestate.players[local_port].position.y
                    dist = math.sqrt((xdist**2) + (ydist**2))
                    if dist < gamestate.distance:
                        gamestate.distance = dist
                        popo = gamestate.players[opponent_port]
                        gamestate.players[opponent_port] = gamestate.players[opponent_port].nana
                        gamestate.players[opponent_port].nana = popo

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
                    if projectile.owner == local_port:
                        continue
                    if projectile.type not in [ProjectileType.UNKNOWN_PROJECTILE, ProjectileType.PEACH_PARASOL, \
                        ProjectileType.FOX_LASER, ProjectileType.SHEIK_CHAIN, ProjectileType.SHEIK_SMOKE]:
                        knownprojectiles.append(projectile)
                gamestate.projectiles = knownprojectiles

                # Yoshi shield animations are weird. Change them to normal shield
                if gamestate.players[opponent_port].character == Character.YOSHI:
                    if gamestate.players[opponent_port].action in [melee.Action.NEUTRAL_B_CHARGING, melee.Action.NEUTRAL_B_FULL_CHARGE, melee.Action.LASER_GUN_PULL]:
                        gamestate.players[opponent_port].action = melee.Action.SHIELD

                # Tech lockout
                if gamestate.players[local_port].controller_state.button[Button.BUTTON_L]:
                    tech_lockout = 40
                else:
                    tech_lockout -= 1
                    tech_lockout = max(0, tech_lockout)

                # Jump meteor cancel lockout
                if gamestate.players[local_port].controller_state.button[Button.BUTTON_Y] or \
                    gamestate.players[local_port].controller_state.main_stick[1] > 0.8:
                    meteor_jump_lockout = 40
                else:
                    meteor_jump_lockout -= 1
                    meteor_jump_lockout = max(0, meteor_jump_lockout)

                # Firefox meteor cancel lockout
                if gamestate.players[local_port].controller_state.button[Button.BUTTON_B] and \
                    gamestate.players[local_port].controller_state.main_stick[1] > 0.8:
                    meteor_ff_lockout = 40
                else:
                    meteor_ff_lockout -= 1
                    meteor_ff_lockout = max(0, meteor_ff_lockout)

                # Keep a ledge grab count
                if gamestate.players[opponent_port].action == Action.EDGE_CATCHING and gamestate.players[opponent_port].action_frame == 1:
                    ledge_grab_count += 1
                if gamestate.players[opponent_port].on_ground:
                    ledge_grab_count = 0
                if gamestate.frame == -123:
                    ledge_grab_count = 0
                gamestate.custom["ledge_grab_count"] = ledge_grab_count
                gamestate.custom["tech_lockout"] = tech_lockout
                gamestate.custom["meteor_jump_lockout"] = meteor_jump_lockout
                gamestate.custom["meteor_ff_lockout"] = meteor_ff_lockout

                if gamestate.players[local_port].action in [Action.SHIELD_REFLECT, Action.SHIELD_STUN]:
                    if gamestate.players[local_port].is_powershield:
                        powershielded_last = True
                    elif gamestate.players[local_port].hitlag_left > 0:
                        powershielded_last = False

                gamestate.custom["powershielded_last"] = powershielded_last

                # Let's treat Counter-Moves as invulnerable. So we'll know to not attack during that time
                countering = False
                if gamestate.players[opponent_port].character in [Character.ROY, Character.MARTH]:
                    if gamestate.players[opponent_port].action in [Action.MARTH_COUNTER, Action.MARTH_COUNTER_FALLING]:
                        # We consider Counter to start a frame early and a frame late
                        if 4 <= gamestate.players[opponent_port].action_frame <= 30:
                            countering = True
                if gamestate.players[opponent_port].character == Character.PEACH:
                    if gamestate.players[opponent_port].action in [Action.UP_B_GROUND, Action.DOWN_B_STUN]:
                        if 4 <= gamestate.players[opponent_port].action_frame <= 30:
                            countering = True
                if countering:
                    gamestate.players[opponent_port].invulnerable = True
                    gamestate.players[opponent_port].invulnerability_left = max(29 - gamestate.players[opponent_port].action_frame, gamestate.players[opponent_port].invulnerability_left)

                # Platform drop is fully actionable. Don't be fooled
                if gamestate.players[opponent_port].action == Action.PLATFORM_DROP:
                    gamestate.players[opponent_port].hitstun_frames_left = 0
                
                # Skip non-actionable frames
                if framedata.is_hit(gamestate.players[local_port]) or framedata.is_damaged(gamestate.players[local_port]):
                    continue
                
                if move_queued == 0 and framedata.can_special_attack(gamestate.players[local_port]):
                    # We only attack when it is safe to do so
                    safe_attack = in_safezone(gamestate.players[local_port], all_edges)
                    player_velocity_total_y = gamestate.players[local_port].speed_y_self + gamestate.players[local_port].speed_y_attack
                    # Determine if opponent will hit us
                    opponent_character = gamestate.players[opponent_port].character
                    opponent_action = gamestate.players[opponent_port].action
                    is_attacking = framedata.is_attacking(gamestate.players[opponent_port])
                    is_grabbing = framedata.is_grab(opponent_character, opponent_action)
                    if is_attacking and not is_grabbing:
                        hit_frame = framedata.in_range(gamestate.players[opponent_port], gamestate.players[local_port], gamestate.stage)
                        if hit_frame != 0:
                            current_frame = gamestate.players[opponent_port].action_frame
                            frames_till_hit = hit_frame - current_frame
                            frame_window = framedata.counter_window(gamestate.players[local_port])
                            if frames_till_hit >= frame_window[0] and frames_till_hit <= frame_window[1]:
                                if safe_attack:
                                    kb_controller.inputs_reserved = True
                                    controller.release_all()
                                    counter_inputs = get_counter_inputs(gamestate.players[local_port])
                                    new_inputs[0].extend(counter_inputs[0])
                                    new_inputs[1] = counter_inputs[1]
                                    move_queued = gamestate.frame
                if move_queued != 0:
                    if move_queued <= gamestate.frame - 1:
                        controller.release_all()
                        new_inputs = [[], None, None]
                        if move_queued <= gamestate.frame - 2:
                            kb_controller.inputs_reserved = False
                            move_queued = 0
                
                if new_inputs[1]:
                    # new main stick inputs
                    if new_inputs[1]:
                        controller.tilt_analog(Button.BUTTON_MAIN, new_inputs[1][0], new_inputs[1][1])
                if new_inputs[2]:
                    # new c stick inputs
                    if new_inputs[2]:
                        controller.tilt_analog(Button.BUTTON_C, new_inputs[2][0], new_inputs[2][1])
                if len(new_inputs[0]) != 0:
                    # do new button inputs
                    for new_button in new_inputs[0]:
                        controller.press_button(new_button)
            if log:
                log.logframe(gamestate)
                log.writeframe()
        else:
            initialized = False
            local_port = 0
            opponent_port = 0
            opponent_ports = []
            
            # If we're not in game, don't log the frame
            if log:
                log.skipframe()

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
        if key != target_port:
            opponent_ports.append(key)
            print("Found opponent in port:", key)
    if len(opponent_ports) == 0:
        print("Unable to find opponents of port:", target_port)
    return opponent_ports

if __name__ == '__main__':
    main()