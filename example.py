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

from melee.enums import Action, Analog, Button, Character, ProjectileType
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
    config = configparser.ConfigParser()
    section = "Settings"
    # Whether the keyboard is currently reserved for automated inputs
    inputs_reserved = False
    turbo = False
    # The frame hotkeys were last released while turbo button was pressed
    turbo_frames = (0, 0)
    gamestate = None
    buttons_queue = []
    # List of hotkey numbers banned from being pressed
    banned_hotkeys = []
    l_cancel = False
    l_cancel_frame = 0
    
    def __init__(self, input_config_path):
        self.cfg_path = input_config_path
        self.config.read(input_config_path)
        # Add a standard smashbox config to the file of the given path
        if not self.config.has_section(self.section):
            print(args.config + " does not contain Settings section!")
            self.create_smashbox_config()

        self.toggle_hotkeys()
        self.hotkeys_state = {}
        
        i = 1
        for input, key in self.config.items(self.section):
            print(key)
            
            # Skip multi-key hotkeys
            if '+' in key:
                scan_codes = None
            else:
                scan_codes = keyboard.key_to_scan_codes(key)
            
            full_key = (key, scan_codes)

            self.hotkeys[full_key] = i
            self.hotkeys[i] = full_key
            self.hotkeys_state[i] = False
            i += 1
            
    def set_gamestate(self, gs):
        self.gamestate = gs
    
    def create_smashbox_config(self):
        print("Creating standard smashbox Settings.")
        self.config.add_section(self.section)
        # Stick inputs (1-8)
        self.config.set(self.section, 'Analog Up', 'i')
        self.config.set(self.section, 'Analog Left', 'w')
        self.config.set(self.section, 'Analog Down', '3')
        self.config.set(self.section, 'Analog Right', 'r')
        self.config.set(self.section, 'C-Stick Up', '.')
        self.config.set(self.section, 'C-Stick Left', ',')
        self.config.set(self.section, 'C-Stick Down', 'right alt')
        self.config.set(self.section, 'C-Stick Right', '/')
        # Buttons (9-21)
        self.config.set(self.section, 'Lightshield', 'p')
        self.config.set(self.section, 'L', 'o')
        self.config.set(self.section, 'Y', '[')
        self.config.set(self.section, 'R', 'a')
        self.config.set(self.section, 'B', ';')
        self.config.set(self.section, 'A', 'l')
        self.config.set(self.section, 'X', 'k')
        self.config.set(self.section, 'Z', ']')
        self.config.set(self.section, 'Start', '7')
        self.config.set(self.section, 'D-Pad Up', '8')
        self.config.set(self.section, 'D-Pad Down', '2')
        self.config.set(self.section, 'D-Pad Left', '4')
        self.config.set(self.section, 'D-Pad Right', '6')
        # Analog Modifiers (22-25)
        self.config.set(self.section, 'Analog Mod X1', 'c')
        self.config.set(self.section, 'Analog Mod X2', 'v')
        self.config.set(self.section, 'Analog Mod Y1', 'b')
        self.config.set(self.section, 'Analog Mod Y2', 'space')
        # Misc Buttons (26+)
        self.config.set(self.section, 'Toggle Hotkeys', 'shift+alt+s')
        self.config.set(self.section, 'Turbo Modifier', 'shift')
        self.config.set(self.section, 'Jump Z', '\'')
        with open(self.cfg_path, 'w') as configfile:
            self.config.write(configfile)

    def toggle_hotkeys(self, init=True):
        print("Toggled hotkeys.")
        self.hotkeys_enabled = not self.hotkeys_enabled
        if self.hotkeys_enabled:
            i = 1
            for input, key in self.config.items(self.section):
                # Multi-key hotkeys need to be hooked differently
                if init and i == 26:
                    keyboard.add_hotkey(key, self.toggle_hotkeys, [False])
                elif i != 26:
                    keyboard.hook_key(key, self.kb_callback)
                i += 1
        else:
            keyboard.unhook(self.kb_callback)

    def kb_callback(self, event):
        # We convert to lower to ensure case-insensitivity
        if isinstance(event, str):
            key = event.lower()
            event_type = KEY_DOWN
        else:
            key = event.name.lower()
            event_type = event.event_type
        
        scan_codes = keyboard.key_to_scan_codes(key)
        full_key = None
        # For cases where a modifier key is pressed (i.e. shift),
        # the name may change, so we check by scan code instead
        for value in self.hotkeys.values():
            if isinstance(value, tuple) and isinstance(value[1], tuple):
                for v in value[1]:
                    for code in scan_codes:
                        if v == code:
                            true_scan_codes = scan_codes = keyboard.key_to_scan_codes(value[0])
                            full_key = (value[0], true_scan_codes)
                            break
                    if full_key:
                        break
        
        if full_key:
            num = self.hotkeys[full_key]
            self.hotkeys_state[num] = (event_type == KEY_DOWN)
            # Skip all inputs when reserved (except Start)
            if self.inputs_reserved and num != 17:
                return
            # Turbo will handle our presses and releases
            elif self.turbo and num != 27:
                return
            # Skip banned buttons
            elif num in self.banned_hotkeys:
                return
            else:
                # Always update analog inputs when modifier keys are pressed/released
                if num >= 22 and num <= 25:
                    for i in range(1, 9):
                        if self.hotkeys_state[i]:
                            self.human_tilt_analog(i)
                    return
                # Handle regular button presses
                if (event_type == KEY_DOWN):
                    self.hotkey_pressed(num)
                else:
                    self.hotkey_released(num)

    def release_hotkey(self, num, set_state=True):
        if set_state:
            self.hotkeys_state[num] = False
        self.hotkey_released(num)

    def release_hotkeys(self, set_state=True):
        for i in range(1, len(self.hotkeys_state)):
            if set_state:
                self.hotkeys_state[i] = False
            # Skip start and turbo keys, and analog modifiers
            if i != 26 and (i > 25 or i < 22):
                if not self.turbo or i != 27:
                    self.hotkey_released(i)

    def redo_hotkey(self, num):
        if self.hotkeys_state[num]:
            self.hotkey_pressed(num)

    # In cases where we reserve hotkeys, we need to do keypresses again using the hotkey states
    def redo_hotkeys(self):
        for i in range(1, len(self.hotkeys_state)):
            if i == 27:
                continue
            self.redo_hotkey(i)

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

    # Get the button associated with a hotkey number
    def get_hotkey_button(self, num):
        if num == 9 or num == 10:
            return [melee.Button.BUTTON_L]
        if num == 11:
            return [melee.Button.BUTTON_Y]
        if num == 12:
            return [melee.Button.BUTTON_R]
        if num == 13:
            return [melee.Button.BUTTON_B]
        if num == 14:
            return [melee.Button.BUTTON_A]
        if num == 15:
            return [melee.Button.BUTTON_X]
        if num == 16:
            return [melee.Button.BUTTON_Z]
        if num == 17:
            return [melee.Button.BUTTON_START]
        if num == 18:
            return [melee.Button.BUTTON_D_UP]
        if num == 19:
            return [melee.Button.BUTTON_D_DOWN]
        if num == 20:
            return [melee.Button.BUTTON_D_LEFT]
        if num == 21:
            return [melee.Button.BUTTON_D_RIGHT]
        if num == 28:
            return [melee.Button.BUTTON_X, melee.Button.BUTTON_Z]
        
        return None
        
    # Get the hotkey number associated with a button
    def get_button_hotkey(self, button):
        if isinstance(button, list):
            if len(button) > 1:
                if button[0] == melee.Button.BUTTON_X and button[1] == melee.Button.BUTTON_Z:
                    return 28
                else:
                    return None
                
        if button == melee.Button.BUTTON_L:
            return 10
        if button == melee.Button.BUTTON_Y:
            return 11
        if button == melee.Button.BUTTON_R:
            return 12
        if button == melee.Button.BUTTON_B:
            return 13
        if button == melee.Button.BUTTON_A:
            return 14
        if button == melee.Button.BUTTON_X:
            return 15
        if button == melee.Button.BUTTON_Z:
            return 16
        if button == melee.Button.BUTTON_START:
            return 17
        if button == melee.Button.BUTTON_D_UP:
            return 18
        if button == melee.Button.BUTTON_D_DOWN:
            return 19
        if button == melee.Button.BUTTON_D_LEFT:
            return 20
        if button == melee.Button.BUTTON_D_RIGHT:
            return 21
        
    def get_analog_hotkey(self, button, analog):
        if button == Button.BUTTON_MAIN:
            if analog == Analog.UP:
                return 1
            if analog == Analog.LEFT:
                return 2
            if analog == Analog.DOWN:
                return 3
            if analog == Analog.RIGHT:
                return 4
        if button == Button.BUTTON_C:
            if analog == Analog.UP:
                return 5
            if analog == Analog.LEFT:
                return 6
            if analog == Analog.DOWN:
                return 7
            if analog == Analog.RIGHT:
                return 8
        return None
        
    def get_hotkey_stick(self, num):
        if num < 1 or num > 8:
            return None
        
        if num < 5:
            button = melee.Button.BUTTON_MAIN
            tilt = controller.current.main_stick
        else:
            button = melee.Button.BUTTON_C
            tilt = controller.current.c_stick
            
        return (button, tilt)

    def hotkey_pressed(self, num):
        if num == 0:
            return
        if self.hotkeys_enabled:
            # Turbo Modifier
            if num == 27:
                self.turbo = True
            # Analog inputs
            elif num < 9:
                self.human_tilt_analog(num)
            elif num == 9:
                self.human_press_shoulder()
            # Buttons
            elif num > 25 or num < 22:
                self.human_button_pressed(num)

    def hotkey_released(self, num):
        if num == 0:
            return
        if self.hotkeys_enabled:
            # Turbo Modifier
            if num == 27:
                self.turbo = False
                self.turbo_frames = (0, 0)
                self.redo_hotkeys()
            # Analog inputs
            elif num < 9:
                self.human_untilt_analog(num)
            elif num == 9:
                self.human_release_shoulder()
            # Buttons
            elif num > 25 or num < 22:
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
        buttons = self.get_hotkey_button(num)
        if len(buttons) > 1:
            # Check for duplicate buttons in queue
            for queued_button in self.buttons_queue:
                if queued_button[1] == buttons:
                    return
            self.buttons_queue.append((self.gamestate.frame, buttons))
            self.buttons_update()
            return
        controller.press_button(buttons[0])

    def human_button_released(self, num):
        buttons = self.get_hotkey_button(num)
        if len(buttons) > 1:
            return
        
        controller.release_button(buttons[0])

    def human_tilt_analog(self, num):
        button, tilt = self.get_hotkey_stick(num)
        opposite_key = self.get_opposite_key(num)

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
        else:
            tilt = self.get_tilt(num)
            
        controller.tilt_analog(button, tilt[0], tilt[1])

    def human_untilt_analog(self, num):
        button, tilt = self.get_hotkey_stick(num)
        opposite_key = self.get_opposite_key(num)
        
        # Do opposite tilt instead of canceling
        if (self.hotkeys_state[opposite_key] and not self.turbo):
            self.human_tilt_analog(opposite_key)
            return
        
        # Reset tilt to neutral, ignoring pressed buttons
        if self.turbo:
            controller.tilt_analog(button, 0.5, 0.5)
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

        controller.tilt_analog(button, tilt[0], tilt[1])
    
    def human_press_shoulder(self):
        controller.press_shoulder(melee.Button.BUTTON_L, 0.3325)
        
    def human_release_shoulder(self):
        controller.press_shoulder(melee.Button.BUTTON_L, 0.0)
    
    def update(self, gamestate):
        self.set_gamestate(gamestate)
        self.buttons_update()
        self.turbo_update()
        self.l_cancel_update()
    
    def buttons_update(self):
        if len(self.buttons_queue) == 0:
            return
        current_frame = self.gamestate.frame
        button_frame, buttons = self.buttons_queue[0]
        if len(buttons) == 0:
            self.buttons_queue = self.buttons_queue[1:]
            return
        
        currrent_button = buttons[0]
        if current_frame >= button_frame + 2:
            controller.release_button(currrent_button)
            if len(buttons) <= 1:
                self.buttons_queue = self.buttons_queue[1:]
            else:
                buttons.pop(0)
                # update frame for next button
                current_frame = self.gamestate.frame
                self.buttons_queue[0] = (current_frame, buttons)
        elif current_frame == button_frame + 1:
            controller.press_button(currrent_button)
    
    # Alternates between pressing and releasing hotkeys each frame
    def turbo_update(self):
        if not self.gamestate or (not self.turbo and not self.l_cancel):
            return
        
        current_frame = self.gamestate.frame
        button_frame = self.turbo_frames[0]
        stick_frame = self.turbo_frames[1]
        
        # Start of turbo loop is releasing
        if button_frame == 0 or current_frame >= button_frame + 2:
            self.turbo_frames = (current_frame, stick_frame)
            self.release_hotkeys(False)
        # End of turbo loop is pressing
        elif button_frame > 0 and current_frame >= button_frame + 1:
            self.redo_hotkeys()
    
    # Updates the L-Cancel button
    def l_cancel_update(self):
        if not self.l_cancel:
            self.l_cancel_frame = 0
            if not self.hotkeys_state[9]:
                self.human_release_shoulder()
            return
        
        current_frame = self.gamestate.frame
        button_frame = self.l_cancel_frame
        
        if button_frame == 0 or current_frame >= button_frame + 7:
            self.l_cancel_frame = current_frame
            self.human_release_shoulder()
        elif button_frame > 0 and current_frame >= button_frame + 1:
            self.human_press_shoulder()
    
    # Sets the buttons the player is banned from pressing
    def set_banned_hotkeys(self, buttons):
        new_bans = []
        for button in buttons:
            hotkey = self.get_button_hotkey(button)
            if hotkey:
                new_bans.append(hotkey)
        self.banned_hotkeys = new_bans

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
                        logger=log,
                        save_replays=False)

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
                xdist = player.position.x - opponent.position.x
                ydist = player.position.y - opponent.position.y
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
    elif player.y > 7:
        return True
    
    return False
    
def get_counter_inputs(player):
    character = player.character
    if character == Character.ROY or character == Character.MARTH:
        return [Button.BUTTON_B], (0.5, -0.0475)
    # Character.PEACH
    return [Button.BUTTON_B], (0.5, 0.5)

# Returns -1, 0, or 1 depending on if the player is on the left, in the middle, or right of the stage
def get_relative_stage_position(player, stage_bounds):
    if player.position.x < stage_bounds[0]:
        return -1
    if player.position.x > stage_bounds[1]:
        return 1
    return 0

def get_dodge_inputs(player, framedata):
    if framedata.is_shielding(player):
        return [], (0.5, -0.0475)
    if player.action == Action.EDGE_HANGING and player.percent < 100:
        # Facing right
        if player.facing:
            return [], (1.0425, 0.5)
        # Facing left
        else:
            return [], (-0.0375, 0.5)
    return [Button.BUTTON_L], (0.5, -0.0475)

def get_controller_tilt(type):
    tilt = (0, 0)
    if type == melee.Button.BUTTON_MAIN:
        tilt = controller.current.main_stick
    else:
        tilt = controller.current.c_stick
    return tilt

def can_ledgefall(kb_controller):
    last_frame = (controller.prev.raw_main_stick[1] <= -45 and
                   controller.prev.raw_main_stick[0] == 0)
    down_hotkey = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.DOWN)
    left_hotkey = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.LEFT)
    right_hotkey = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.RIGHT)
    return (kb_controller.hotkeys_state[down_hotkey] and
                               not kb_controller.hotkeys_state[left_hotkey] and
                               not kb_controller.hotkeys_state[right_hotkey])

# Whether the player should wavedash out of shield
def should_wd_oos(player, framedata, kb_controller):
    if framedata.is_shielding(player):
        left = kb_controller.hotkeys_state[controller.current.get_analog_hotkey(Button.BUTTON_MAIN, Analog.LEFT)]
        right = kb_controller.hotkeys_state[controller.current.get_analog_hotkey(Button.BUTTON_MAIN, Analog.RIGHT)]
        if left and not right:
            return -1
        elif right and not left:
            return 1
    return 0

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
    alive = False
    
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
        # Read in dolphin's controller config file
        kb_controller = KBController(args.config)
    
    # Main loop
    while True:

        # "step" to the next frame
        gamestate = console.step()
        if gamestate is None:
            initialized = False
            continue
        
        # Do keyboard updates
        kb_controller.update(gamestate)

        # The console object keeps track of how long your bot is taking to process frames
        #   And can warn you if it's taking too long
        if console.processingtime * 1000 > 12:
            print("WARNING: Last frame took " + str(console.processingtime*1000) + "ms to process.")

        in_game = gamestate.menu_state in [melee.Menu.IN_GAME, melee.Menu.SUDDEN_DEATH]

        # What menu are we in?
        if in_game:
            if not initialized:
                alive = True
                ground_left = (-melee.stages.EDGE_GROUND_POSITION[gamestate.stage], 0)
                ground_right = (melee.stages.EDGE_GROUND_POSITION[gamestate.stage], 0)
                stage_bounds_ground = (ground_left, ground_right)
                offstage_left = (-melee.stages.EDGE_POSITION[gamestate.stage], 0)
                offstage_right = (melee.stages.EDGE_POSITION[gamestate.stage], 0)
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
                initialized = True
            
            # Discover our target player
            local_player_invalid = local_port not in gamestate.players
            if local_player_invalid or len(opponent_ports) == 0 and alive:
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
                            alive = False
                if len(opponent_ports) == 0:
                    opponent_ports = get_opponents(gamestate, local_port)
            else:
                local_player = gamestate.players[local_port]
                opponent_port = get_closest_opponent(gamestate, local_player, opponent_ports)
                if opponent_port != 0:
                    opponent_player = gamestate.players[opponent_port]
                else:
                    continue
                
                # Pick the right climber to be the opponent
                if opponent_player.nana is not None:
                    xdist = opponent_player.nana.position.x - local_player.position.x
                    ydist = opponent_player.nana.position.y - local_player.position.y
                    dist = math.sqrt((xdist**2) + (ydist**2))
                    if dist < gamestate.distance:
                        gamestate.distance = dist
                        popo = opponent_player
                        opponent_player = opponent_player.nana
                        opponent_player.nana = popo

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
                if opponent_player.character == Character.YOSHI:
                    if opponent_player.action in [melee.Action.NEUTRAL_B_CHARGING, melee.Action.NEUTRAL_B_FULL_CHARGE, melee.Action.LASER_GUN_PULL]:
                        opponent_player.action = melee.Action.SHIELD

                # Tech lockout
                if local_player.controller_state.button[Button.BUTTON_L]:
                    tech_lockout = 40
                else:
                    tech_lockout -= 1
                    tech_lockout = max(0, tech_lockout)

                # Jump meteor cancel lockout
                if local_player.controller_state.button[Button.BUTTON_Y] or \
                    local_player.controller_state.main_stick[1] > 0.8:
                    meteor_jump_lockout = 40
                else:
                    meteor_jump_lockout -= 1
                    meteor_jump_lockout = max(0, meteor_jump_lockout)

                # Firefox meteor cancel lockout
                if local_player.controller_state.button[Button.BUTTON_B] and \
                    local_player.controller_state.main_stick[1] > 0.8:
                    meteor_ff_lockout = 40
                else:
                    meteor_ff_lockout -= 1
                    meteor_ff_lockout = max(0, meteor_ff_lockout)

                # Keep a ledge grab count
                if opponent_player.action == Action.EDGE_CATCHING and opponent_player.action_frame == 1:
                    ledge_grab_count += 1
                if opponent_player.on_ground:
                    ledge_grab_count = 0
                if gamestate.frame == -123:
                    ledge_grab_count = 0
                gamestate.custom["ledge_grab_count"] = ledge_grab_count
                gamestate.custom["tech_lockout"] = tech_lockout
                gamestate.custom["meteor_jump_lockout"] = meteor_jump_lockout
                gamestate.custom["meteor_ff_lockout"] = meteor_ff_lockout

                if local_player.action in [Action.SHIELD_REFLECT, Action.SHIELD_STUN]:
                    if local_player.is_powershield:
                        powershielded_last = True
                    elif local_player.hitlag_left > 0:
                        powershielded_last = False

                gamestate.custom["powershielded_last"] = powershielded_last

                # Let's treat Counter-Moves as invulnerable. So we'll know to not attack during that time
                countering = False
                if opponent_player.character in [Character.ROY, Character.MARTH]:
                    if opponent_player.action in [Action.MARTH_COUNTER, Action.MARTH_COUNTER_FALLING]:
                        # We consider Counter to start a frame early and a frame late
                        if 4 <= opponent_player.action_frame <= 30:
                            countering = True
                if opponent_player.character == Character.PEACH:
                    if opponent_player.action in [Action.UP_B_GROUND, Action.DOWN_B_STUN]:
                        if 4 <= opponent_player.action_frame <= 30:
                            countering = True
                if countering:
                    opponent_player.invulnerable = True
                    opponent_player.invulnerability_left = max(29 - opponent_player.action_frame, opponent_player.invulnerability_left)

                # Platform drop is fully actionable. Don't be fooled
                if opponent_player.action == Action.PLATFORM_DROP:
                    opponent_player.hitstun_frames_left = 0
                
                # L-Cancels
                if (not local_player.on_ground and
                    local_player.speed_y_self < 0 and
                    not local_player.off_stage and
                    framedata.is_normal_attacking(local_player)):
                    kb_controller.l_cancel = True
                else:
                    kb_controller.l_cancel = False
                
                # Skip non-actionable frames
                if not framedata.is_actionable(local_player):
                    continue
                
                if move_queued == 0:
                    wavedash_out = should_wd_oos(local_player, framedata, kb_controller)
                    
                    
                    
                    # We only counter when it is safe to do so
                    can_attack = safe_counter(local_player)
                    # Determine if opponent will hit us
                    opponent_character = opponent_player.character
                    opponent_action = opponent_player.action
                    attack_imminent = framedata.check_attack(gamestate, opponent_player)
                    is_grabbing = framedata.is_grab(opponent_character, opponent_action)
                    
                    if attack_imminent:
                        hit_frame = framedata.in_range(opponent_player, local_player, gamestate.stage)
                        if hit_frame != 0:
                            current_frame = opponent_player.action_frame
                            frames_till_hit = hit_frame - current_frame
                            counter_start, counter_end = framedata.counter_window(local_player)
                            dodge_start, dodge_end = framedata.intangible_window(local_player, Action.SPOTDODGE)
                            can_counter = ((counter_end != 0) and 
                                           frames_till_hit >= counter_start and
                                           frames_till_hit <= counter_end)
                            should_counter = not is_grabbing and can_attack and can_counter
                            can_dodge = (frames_till_hit >= dodge_start and frames_till_hit <= dodge_end and 
                                        (local_player.on_ground or local_player.action == Action.EDGE_HANGING or
                                         framedata.is_shielding(local_player)))
                            should_dodge = can_dodge and frames_till_hit <= counter_start
                            
                            if not move_queued and should_counter:
                                kb_controller.inputs_reserved = True
                                counter_inputs = get_counter_inputs(local_player)
                                new_inputs[0].extend(counter_inputs[0])
                                new_inputs[1] = counter_inputs[1]
                                move_queued = gamestate.frame + 1
                                controller.release_all()
                            # If we cannot counter, we try dodging
                            if not move_queued and should_dodge:
                                kb_controller.inputs_reserved = True
                                dodge_inputs = get_dodge_inputs(local_player, framedata)
                                new_inputs[0].extend(dodge_inputs[0])
                                new_inputs[1] = dodge_inputs[1]
                                if (framedata.is_shielding(local_player) and 
                                   local_player.controller_state.raw_main_stick[1] <= -45):
                                    move_queued = gamestate.frame + 1
                                    controller.release_all()
                                else:
                                    move_queued = gamestate.frame
                if move_queued != 0:
                    # Attack/reservation frame
                    if gamestate.frame == move_queued:
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
                    # Release frame
                    elif gamestate.frame == move_queued + 1:
                        controller.release_all()
                        new_inputs = [[], None, None]
                    # Finish attack/reservation frame
                    elif gamestate.frame >= move_queued + 2:
                        move_queued = 0
                        kb_controller.redo_hotkeys()
                        kb_controller.inputs_reserved = False
            if log:
                log.logframe(gamestate)
                log.writeframe()
        else:
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
            alive = False
            kb_controller.inputs_reserved = False
            
            # If we're not in game, don't log the frame
            if log:
                log.skipframe()

if __name__ == '__main__':
    main()