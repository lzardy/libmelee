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
    inputs_reserved = 0
    input_queue = []
    current_stick_state = {
        melee.Button.BUTTON_MAIN: {'x': 0.5, 'y': 0.5},
        melee.Button.BUTTON_C: {'x': 0.5, 'y': 0.5}
    }
    current_shoulder_state = {
        melee.Button.BUTTON_L: 0.0,
        melee.Button.BUTTON_R: 0.0
    }
    
    gamestate = None
    l_cancel = False
    force_tilt = False
    force_tilt_platform = False
    edge_cancels = False
    character_int = 0
    
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
            
        self.reserved_inputs = set()
        
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
        self.config.set(self.section, 'R', 'f')
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
        self.config.set(self.section, 'Ledge Dash', 'm')
        self.config.set(self.section, 'Character Specific Attack', 'a')
        self.config.set(self.section, 'Auto Edgecancel', 'e')
        self.config.set(self.section, '')
        # self.config.set(self.section, 'Increment Character', '0')
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
            
            # Toggles
            if num == 31 and not self.hotkeys_state[num] and (event_type == KEY_DOWN):
                self.edge_cancels = not self.edge_cancels
                
            self.hotkeys_state[num] = (event_type == KEY_DOWN)
            self.hotkey_update(num)

    def release_hotkey(self, num, set_state=True):
        if set_state:
            self.hotkeys_state[num] = False
        self.hotkey_released(num)

    def release_hotkeys(self, set_state=True):
        for i in range(1, len(self.hotkeys_state)):
            if set_state:
                self.hotkeys_state[i] = False
            # Skip start and turbo keys, and analog modifiers
            if i < 22:
                if not self.hotkeys_state[27] or i != 27:
                    self.hotkey_released(i)

    def redo_hotkey(self, num):
        if isinstance(num, list):
            for n in num:
                if self.hotkeys_state[n]:
                    self.redo_hotkey(n)
        elif self.hotkeys_state[num]:
            self.hotkey_pressed(num)

    # In cases where we reserve hotkeys, we need to do keypresses again using the hotkey states
    def redo_hotkeys(self):
        for i in range(1, len(self.hotkeys_state)):
            if i > 25:
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
        if num <= 4:
            return [melee.Button.BUTTON_MAIN]
        if num <= 8:
            return [melee.Button.BUTTON_C]
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
            return [9, 10]
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
            # Turbo Modifier, Ledgedash, Gentleman
            if num == 27 or num == 29 or num == 30 or num == 31:
                return
            # Analog inputs
            if num < 9:
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
            # Ledgedash, Gentleman
            if num == 29 or num == 30 or num == 31:
                return
            # Turbo Modifier
            if num == 27:
                self.redo_hotkeys()
                return
            # Analog inputs
            if num < 9:
                self.human_untilt_analog(num)
            elif num == 9:
                self.human_release_shoulder()
            # Buttons
            elif num > 25 or num < 22:
                self.human_button_released(num)

    def get_tilt(self, num, check_state=True, skip_mod=False):
        init_state = self.hotkeys_state[num]
        force_state = init_state
        if not check_state:
            force_state = True
        
        x = 0.5
        y = 0.5
        
        if num == 0:
            return (x, y)
        
        opposite_key = self.get_opposite_key(num)
        
        # print("Current tilt analog values: (" + str(tilt[0]) + ", " + str(tilt[1]) + ")")

        if force_state:
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
            if (force_state):
                y = 1.0375
        if (num == 5):
            if (self.hotkeys_state[6] and
                not self.hotkeys_state[self.get_opposite_key(6)]):
                x = -0.0375
            if (self.hotkeys_state[8] and
                not self.hotkeys_state[self.get_opposite_key(8)]):
                x = 1.0425
            if (force_state):
                y = 1.0375
        
        # down
        if (num == 3):
            if (self.hotkeys_state[2] and
                not self.hotkeys_state[self.get_opposite_key(2)]):
                x = -0.0375
            if (self.hotkeys_state[4] and
                not self.hotkeys_state[self.get_opposite_key(4)]):
                x = 1.0425
            if (force_state):
                y = -0.0475
        if (num == 7):
            if (self.hotkeys_state[6] and
                not self.hotkeys_state[self.get_opposite_key(6)]):
                x = -0.0375
            if (self.hotkeys_state[8] and
                not self.hotkeys_state[self.get_opposite_key(8)]):
                x = 1.0425
            if (force_state):
                y = -0.0475
        
        # left
        if (num == 2):
            if (self.hotkeys_state[1] and
                not self.hotkeys_state[self.get_opposite_key(1)]):
                y = 1.0375
            if (self.hotkeys_state[3] and
                not self.hotkeys_state[self.get_opposite_key(3)]):
                y = -0.0475
            if (force_state):
                x = -0.0375
        if (num == 6):
            if (self.hotkeys_state[5] and
                not self.hotkeys_state[self.get_opposite_key(5)]):
                y = 1.0375
            if (self.hotkeys_state[7] and
                not self.hotkeys_state[self.get_opposite_key(7)]):
                y = -0.0475
            if (force_state):
                x = -0.0375
            
        # right
        if (num == 4):
            if (self.hotkeys_state[1] and
                not self.hotkeys_state[self.get_opposite_key(1)]):
                y = 1.0375
            if (self.hotkeys_state[3] and
                not self.hotkeys_state[self.get_opposite_key(3)]):
                y = -0.0475
            if (force_state):
                x = 1.0425
        if (num == 8):
            if (self.hotkeys_state[5] and
                not self.hotkeys_state[self.get_opposite_key(5)]):
                y = 1.0375
            if (self.hotkeys_state[7] and
                not self.hotkeys_state[self.get_opposite_key(7)]):
                y = -0.0475
            if (force_state):
                x = 1.0425

        if skip_mod:
            return (x, y)
            
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
        if len(buttons) >= 2:
            frame_offset = 0
            for button in buttons:
                current_frame = self.gamestate.frame + frame_offset
                self.queue_input('button', button, current_frame + 1, current_frame + 2)
                frame_offset += 2
            return
                
        controller.press_button(buttons[0])

    def human_button_released(self, num):
        buttons = self.get_hotkey_button(num)
        if len(buttons) >= 2:
            # current_frame = self.gamestate.frame
            # for button in buttons:
            #     # Check if there's a press for this button in the current frame
            #     press_in_current_frame = any(
            #         input['type'] == 'button' and
            #         input['value'] == button and
            #         input['start_frame'] == current_frame
            #         for input in self.input_queue
            #     )
                
            #     # If there's a press in the current frame, schedule the release for the next frame
            #     release_frame = current_frame + 1 if press_in_current_frame else current_frame
                
            #     self.queue_input('button', button, release_frame, release_frame)
            
            return
        
        first_button = buttons.pop(0)
        controller.release_button(first_button)

    def calculate_current_tilt(self, stick):
        x, y = 0.5, 0.5
        
        if stick == melee.Button.BUTTON_MAIN:
            # Check main stick directional inputs (1-4)
            if self.hotkeys_state[1] and not self.hotkeys_state[3]: y = max(y, 1.0375)  # Up
            if self.hotkeys_state[3] and not self.hotkeys_state[1]: y = min(y, -0.0475)  # Down
            if self.hotkeys_state[2] and not self.hotkeys_state[4]: x = min(x, -0.0375)  # Left
            if self.hotkeys_state[4] and not self.hotkeys_state[2]: x = max(x, 1.0425)  # Right
        elif stick == melee.Button.BUTTON_C:
            # Check C-stick directional inputs (5-8)
            if self.hotkeys_state[5] and not self.hotkeys_state[7]: y = max(y, 1.0375)  # C-Up
            if self.hotkeys_state[7] and not self.hotkeys_state[5]: y = min(y, -0.0475)  # C-Down
            if self.hotkeys_state[6] and not self.hotkeys_state[8]: x = min(x, -0.0375)  # C-Left
            if self.hotkeys_state[8] and not self.hotkeys_state[6]: x = max(x, 1.0425)  # C-Right
        
        if stick != melee.Button.BUTTON_C:
            x, y = self.apply_tilt_mod(x, y)

            if self.force_tilt or self.force_tilt_platform or self.hotkeys_state[9] or self.hotkeys_state[10] or self.hotkeys_state[12]:
                # Modify stick values to force tilts
                if self.force_tilt_platform:
                    if x < 0.125:
                        x = 0.125
                    elif x > 0.8725:
                        x = 0.8725
                    if y < 0.125:
                        y = 0.125
                    elif y > 0.83:
                        y = 0.83
                else:
                    if x < 0.1575:
                        x = 0.1575
                    elif x > 0.8425:
                        x = 0.8425
                    if y < 0.165:
                        y = 0.165
                    elif x > 0.83:
                        x = 0.83
        
        return (x, y)

    def human_tilt_analog(self, num):
        button, _ = self.get_hotkey_stick(num)
        new_x, new_y = self.calculate_current_tilt(button)
        controller.tilt_analog(button, new_x, new_y)

    def human_untilt_analog(self, num):
        button, _ = self.get_hotkey_stick(num)
        
        new_x, new_y = 0.5, 0.5
        # Recalculate the stick position based on all currently pressed directional inputs
        if not self.hotkeys_state[27]:
            new_x, new_y = self.calculate_current_tilt(button)
        controller.tilt_analog(button, new_x, new_y)
    
    def update_analog_inputs(self):
        # Skip update if reserved
        if melee.Button.BUTTON_MAIN in self.reserved_inputs or melee.Button.BUTTON_C in self.reserved_inputs:
            return
        
        current_y = self.current_stick_state[melee.Button.BUTTON_MAIN]['y']
        main_x, main_y = self.calculate_current_tilt(melee.Button.BUTTON_MAIN)
            
        c_x, c_y = self.calculate_current_tilt(melee.Button.BUTTON_C)

        self.current_stick_state[melee.Button.BUTTON_MAIN] = {'x': main_x, 'y': main_y}
        self.current_stick_state[melee.Button.BUTTON_C] = {'x': c_x, 'y': c_y}
    
    def human_press_shoulder(self, value=0.3325):
        controller.press_shoulder(melee.Button.BUTTON_L, value)
        self.current_shoulder_state[melee.Button.BUTTON_L] = value
        
    def human_release_shoulder(self):
        controller.press_shoulder(melee.Button.BUTTON_L, 0.0)
        self.current_shoulder_state[melee.Button.BUTTON_L] = 0.0
    
    # Schedules a redo of a specific hotkey
    def queue_redo(self, frame, num):
        self.queue_input('redo', num, frame, frame)
    
    def queue_input(self, input_type, value, start_frame, end_frame):
        """Queue an input (button press or stick movement) for a specific frame range."""
        if end_frame > 0:
            self.inputs_reserved = end_frame
        # Add the new input
        self.input_queue.append({
            'type': input_type,
            'value': value,
            'start_frame': start_frame,
            'end_frame': end_frame
        })
        # Add the input to the reserved set
        if input_type == 'button':
            self.reserved_inputs.add((value, start_frame))
        elif input_type == 'stick':
            self.reserved_inputs.add((value['stick'], start_frame))
        elif input_type == 'shoulder':
            self.reserved_inputs.add((melee.Button.BUTTON_L, start_frame))  # Assuming L shoulder for simplicity
        
    def process_and_clean_input_queue(self, current_frame):
        new_queue = []
        for input in self.input_queue:
            if current_frame == input['start_frame']:
                if input['type'] == 'redo':
                    self.redo_hotkey(input['value'])
                    continue
                self.apply_input(input)
            if current_frame >= input['end_frame'] and input['end_frame'] > 0:
                self.release_input(input)
                if input['type'] == 'button':
                    self.reserved_inputs.discard((input['value'], input['start_frame']))
                elif input['type'] == 'stick':
                    self.reserved_inputs.discard((input['value']['stick'], input['start_frame']))
                elif input['type'] == 'shoulder':
                    self.reserved_inputs.discard((melee.Button.BUTTON_L, input['start_frame']))
                continue
                
            if current_frame < input['end_frame']:
                new_queue.append(input)
                
        self.input_queue = new_queue
    
    def hotkey_update(self, num):
        if self.gamestate is None or not self.hotkeys_enabled:
            return
        state = self.hotkeys_state[num]
        # Skip inputs only if they are in the reserved set
        if self.gamestate.frame > 0:
            button = self.get_hotkey_button(num)
            if button:
                for reserved_button, _ in self.reserved_inputs:
                    if reserved_button == button[0]:
                        return
        # Turbo will handle our presses and releases
        if self.hotkeys_state[27] and num != 27:
            return
        else:
            # Always update analog inputs when modifier keys are pressed/released
            if num >= 22 and num <= 25:
                self.update_analog_inputs()
                # for i in range(1, 9):
                #     if self.hotkeys_state[i]:
                #         self.human_tilt_analog(i)
                return
            # Handle regular button presses
            if state:
                self.hotkey_pressed(num)
            else:
                self.hotkey_released(num)
    
    def hotkeys_update(self):
        for num in range(1, len(self.hotkeys_state)):
            self.hotkey_update(num)
    
    def update(self, gamestate):
        self.set_gamestate(gamestate)
        
        if gamestate is None:
            return
        
        current_frame = gamestate.frame
        
        if self.hotkeys_state[27] and not self.l_cancel and self.inputs_reserved == 0:
            self.handle_turbo(current_frame)
            return

        # Process queued inputs and remove completed ones
        self.process_and_clean_input_queue(current_frame)

        if not self.inputs_reserved:
            # Update analog inputs based on current hotkey states
            self.update_analog_inputs()
        
            # Apply current stick state
            for stick, state in self.current_stick_state.items():
                controller.tilt_analog(stick, state['x'], state['y'])
        
        self.handle_l_cancel(current_frame)
        
        # Free inputs after reservation
        if gamestate.frame > self.inputs_reserved:
            self.inputs_reserved = 0
            self.reserved_inputs.clear()
        
    def apply_input(self, input):
        if input['type'] == 'button':
            controller.press_button(input['value'])
        elif input['type'] == 'stick':
            controller.tilt_analog(input['value']['stick'], input['value']['x'], input['value']['y'])
            self.current_stick_state[input['value']['stick']] = {
                'x': input['value']['x'],
                'y': input['value']['y']
            }
        elif input['type'] == 'shoulder':
            self.human_press_shoulder(input['value'])
    
    def release_input(self, input):
        if input['type'] == 'button':
            controller.release_button(input['value'])
        elif input['type'] == 'stick':
            # Reset stick to neutral position
            self.current_stick_state[input['value']['stick']] = {'x': 0.5, 'y': 0.5}
        elif input['type'] == 'shoulder':
            self.human_release_shoulder()
            
    def handle_turbo(self, current_frame):
        if current_frame % 2 == 0:
            self.release_hotkeys(False)
        else:
            self.redo_hotkeys()
                
    def handle_l_cancel(self, current_frame):
        if self.l_cancel:
            if current_frame % 6 == 0:
                self.human_press_shoulder(value=0.43)
            elif current_frame % 6 == 1:
                self.human_release_shoulder()
        elif self.inputs_reserved == 0:
            hotkeys = self.get_button_hotkey(melee.Button.BUTTON_L)
            hotkeys.append(self.get_button_hotkey(melee.Button.BUTTON_R))
            hotkey_pressed = any(map(lambda x: self.hotkeys_state[x], hotkeys))
            if not hotkey_pressed:
                state_pressed = self.current_shoulder_state[melee.Button.BUTTON_L] > 0.0
                if state_pressed:
                    self.human_release_shoulder()

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

def handle_l_cancel(kb_controller, player, framedata):
    # Get attack hotkey states
    is_attacking = (kb_controller.hotkeys_state[kb_controller.get_analog_hotkey(Button.BUTTON_C, Analog.UP)] or
                    kb_controller.hotkeys_state[kb_controller.get_analog_hotkey(Button.BUTTON_C, Analog.DOWN)] or
                    kb_controller.hotkeys_state[kb_controller.get_analog_hotkey(Button.BUTTON_C, Analog.LEFT)] or
                    kb_controller.hotkeys_state[kb_controller.get_analog_hotkey(Button.BUTTON_C, Analog.RIGHT)] or
                    kb_controller.hotkeys_state[kb_controller.get_button_hotkey(Button.BUTTON_Z)] or
                    kb_controller.hotkeys_state[kb_controller.get_button_hotkey(Button.BUTTON_A)])
    kb_controller.l_cancel = (
        not player.on_ground and
        (framedata.is_normal_attacking(player) or
        is_attacking)
    )

def queue_turn(kb_controller, new_facing, run_frames=0, set_x=0.0, set_y=0.0, delay=0, cstick=False):
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
    
    current_frame += delay
    
    stick_button = Button.BUTTON_MAIN
    if cstick:
        stick_button = Button.BUTTON_C
    
    stick_input = kb_controller.get_analog_hotkey(stick_button, Analog.RIGHT)
    if not new_facing:
        stick_input = kb_controller.get_analog_hotkey(stick_button, Analog.LEFT)
        
    new_x, new_y = kb_controller.get_tilt(stick_input, False)[0], 0.5
    if run_frames == 0:
        new_x += -0.25 if new_facing else 0.25
    else:
        if run_frames == 1:
            run_frames = 0
        new_x = 1.3 if new_facing else -1.3
        
    if set_x != 0.0:
        new_x = set_x
    if set_y != 0.0:
        new_y = set_y
    
    kb_controller.queue_input('stick', {'stick': stick_button, 'x': new_x, 'y': new_y}, current_frame + 1, current_frame + 2 + run_frames)
    kb_controller.queue_redo(current_frame + 2 + run_frames, stick_input)

def queue_shorthop(kb_controller, with_facing=0, set_x=0.5, use_current_frame=False, delay=0, frames=1):
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
    
    if use_current_frame and current_frame != kb_controller.gamestate.frame:
        current_frame -= 1
        
    current_frame += delay
    
    if with_facing != 0:
        stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.RIGHT)
        if with_facing == -1:
            stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.LEFT)
            
        new_x, new_y = kb_controller.get_tilt(stick_input, False)[0], 0.5
        if set_x != 0.5:
            new_x = set_x
    
        kb_controller.queue_input('stick', {'stick': Button.BUTTON_MAIN, 'x': new_x, 'y': new_y}, current_frame + 1, current_frame + 2 + frames)
        kb_controller.queue_redo(current_frame + 2 + frames, stick_input)
    
    jump_button = kb_controller.get_button_hotkey(Button.BUTTON_Y)
    # Release pressed buttons before pressing again
    if kb_controller.hotkeys_state[jump_button]:
        kb_controller.queue_input('button', Button.BUTTON_Y, current_frame + 1, current_frame + 2)
        current_frame += 1
        
    kb_controller.queue_input('button', Button.BUTTON_Y, current_frame + 1, current_frame + 2)

def queue_wavedash(kb_controller, player, facing=0, set_x=0, set_y=0, do_jump=True, use_current_frame=False, delay=0):
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
    
    if use_current_frame and current_frame != kb_controller.gamestate.frame:
        current_frame -= 1
    
    current_frame += delay
    
    if do_jump and player.on_ground and not player.action == Action.KNEE_BEND:
        queue_shorthop(kb_controller, delay=delay)
        local_char = player.character
        if local_char == Character.FALCO:
            current_frame += 5
        elif local_char == Character.GANONDORF:
            current_frame += 6
        elif local_char == Character.LINK:
            current_frame += 6
        elif local_char == Character.ROY:
            current_frame += 5
        elif local_char == Character.SAMUS:
            current_frame += 3
        elif local_char == Character.SHEIK:
            current_frame += 3
        else:
            current_frame += 4
    
    shield_button = kb_controller.get_button_hotkey(Button.BUTTON_L)[1]
    if kb_controller.hotkeys_state[shield_button]:
        kb_controller.queue_input('button', Button.BUTTON_L, current_frame + 1, current_frame + 1)
        current_frame += 1
    
    stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.RIGHT)
    new_x, _ = kb_controller.get_tilt(stick_input, False)
    if facing != 0:
        if facing == -1:
            stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.LEFT)
            new_x, _ = kb_controller.get_tilt(stick_input, False)
    else:
        new_x = 0.5
    
    stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.DOWN)
    _, new_y = kb_controller.get_tilt(stick_input, False)
    
    # When mod_y2 is not pressed, we increase length manually
    if facing != 0 and not kb_controller.hotkeys_state[24]:
        new_y = -0.0475 + 0.37
        
    if set_x != 0:
        new_x = set_x
    if set_y != 0:
        new_y = set_y
    
    kb_controller.queue_input('stick', {'stick': Button.BUTTON_MAIN, 'x': new_x, 'y': new_y}, current_frame + 1, current_frame + 2)
    kb_controller.queue_redo(current_frame + 2, stick_input)
    
    kb_controller.queue_input('button', Button.BUTTON_L, current_frame + 1, current_frame + 2)
    kb_controller.queue_redo(current_frame + 2, shield_button)

def queue_counter(kb_controller, player, framedata):
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
    
    if player.character == Character.ROY or player.character == Character.MARTH:
        stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.DOWN)
        _, new_y = kb_controller.get_tilt(stick_input, False)
        kb_controller.queue_input('stick', {'stick': Button.BUTTON_MAIN, 'x': 0.5, 'y': new_y}, current_frame + 1, current_frame + 4)
    
    kb_controller.queue_input('button', Button.BUTTON_B, current_frame + 2, current_frame + 3)

def queue_dodge(kb_controller, player, framedata):
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
    
    stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.DOWN)
    new_x, new_y = kb_controller.get_tilt(stick_input, False, True)
    kb_controller.queue_input('stick', {'stick': Button.BUTTON_MAIN, 'x': new_x, 'y': new_y}, current_frame + 1, current_frame + 2)
    kb_controller.queue_redo(current_frame + 2, stick_input)

    if not framedata.is_shielding(player):
        kb_controller.queue_input('button', Button.BUTTON_L, current_frame + 1, current_frame + 2)
        kb_controller.queue_redo(current_frame + 2, kb_controller.get_button_hotkey(Button.BUTTON_L))

def queue_shield(kb_controller, light=False, frames=0, delay=0, use_current_frame=False, redo=True, zpress=False):
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved

    if use_current_frame:
        current_frame -= 1
        
    current_frame += delay

    shield_button = kb_controller.get_button_hotkey(Button.BUTTON_L)[1]
    if light:
        shield_button = kb_controller.get_button_hotkey(Button.BUTTON_L)[0]
    if kb_controller.hotkeys_state[shield_button]:
        return

    if zpress and controller.prev.button[Button.BUTTON_A]:
        kb_controller.queue_input('button', Button.BUTTON_Z, current_frame + 1, current_frame + 2 + frames)

    if not light:
        kb_controller.queue_input('button', Button.BUTTON_L, current_frame + 1, current_frame + 2 + frames)
    else:
        kb_controller.queue_input('shoulder', 0.3325, current_frame + 1, current_frame + 2 + frames)
    if redo:
        kb_controller.queue_redo(current_frame + 2 + frames, shield_button)

def handle_counter_and_dodge(kb_controller, gamestate, player, opponent, framedata):
    attack_imminent = framedata.check_attack(gamestate, opponent)
    
    if attack_imminent:
        hit_frame = framedata.in_range(opponent, player, gamestate.stage)
        if hit_frame != 0:
            current_frame = opponent.action_frame
            frames_till_hit = hit_frame - current_frame
            
            counter_start, counter_end = framedata.counter_window(player)
            
            dodge_start, dodge_end = framedata.intangible_window(player, Action.SPOTDODGE)
            
            getup_attack = opponent.action == Action.GETUP_ATTACK or opponent.action == Action.GROUND_ATTACK_UP
            can_powershield = (getup_attack and frames_till_hit >= 2 and frames_till_hit <= 3)
            
            can_counter = (counter_end != 0 and 
                           frames_till_hit >= counter_start and 
                           frames_till_hit <= counter_end and 
                           safe_counter(player) and 
                           not framedata.is_grab(opponent.character, opponent.action))
            
            if getup_attack and can_counter:
                can_counter = (
                    frames_till_hit >= counter_start + 12 and
                    frames_till_hit <= counter_end
                )
            
            is_facing = opponent.facing == opponent.x >= player.x
            dx = abs(opponent.x - player.x)
            grab_from_behind = dx < 5
            can_dodge = (frames_till_hit >= dodge_start and 
                         frames_till_hit <= dodge_end and
                         framedata.is_grab(opponent.character, opponent.action) and
                         ((player.on_ground and
                           not player.off_stage and
                           (is_facing or grab_from_behind)) or
                          framedata.is_shielding(player)))

            if can_powershield:
                # kb_controller.release_hotkeys(False)
                # queue_powershield(kb_controller)
                return
            if can_counter:
                # queue_counter(kb_controller, player, framedata)
                return
            if can_dodge:
                queue_dodge(kb_controller, player, framedata)
                return

def queue_jump(kb_controller, player, direction=0, delay=0, use_current_frame=False):
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
    
    if player.action == Action.KNEE_BEND:
        return
    
    if delay != 0:
        current_frame += delay
        
    if use_current_frame and current_frame != kb_controller.gamestate.frame:
        current_frame -= 1
    
    if direction != 0:
        stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.RIGHT)
        if direction == -1:
            stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.LEFT)
        new_x, new_y = kb_controller.get_tilt(stick_input, False, True)[0], 0.5
        kb_controller.queue_input('stick', {'stick': Button.BUTTON_MAIN, 'x': new_x, 'y': new_y}, current_frame + 1, current_frame + 2)
        kb_controller.queue_redo(current_frame + 2, stick_input)
        current_frame += 1
    
    kb_controller.queue_input('button', Button.BUTTON_Y, current_frame + 1, current_frame + 2)

def queue_jcgrab(kb_controller, player, dash=0):
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
    
    dash_offset = 0
    if dash != 0:
        stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.RIGHT)
        if dash == -1:
            stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.LEFT)
        new_x, new_y = kb_controller.get_tilt(stick_input, False, True)[0], 0.5
        kb_controller.queue_input('stick', {'stick': Button.BUTTON_MAIN, 'x': new_x, 'y': new_y}, current_frame + 1, current_frame + 2)
        kb_controller.queue_redo(current_frame + 2, stick_input)
        dash_offset += 1
    
    # Knee bend means we are already jumping
    grab_offset = dash_offset
    if player.action != Action.KNEE_BEND:
        kb_controller.queue_input('button', Button.BUTTON_Y, current_frame + 1 + dash_offset, current_frame + 2 + dash_offset)
        grab_offset += 2
    
    attack_input = kb_controller.get_button_hotkey(Button.BUTTON_A)
    grab_input = kb_controller.get_button_hotkey(Button.BUTTON_Z)
    release_button = Button.BUTTON_A
    if kb_controller.hotkeys_state[grab_input]:
        release_button = Button.BUTTON_Z
    if kb_controller.hotkeys_state[attack_input] or kb_controller.hotkeys_state[grab_input]:
        kb_controller.queue_input('button', release_button, current_frame + 1, current_frame + 1)
        grab_offset += 1
    
    kb_controller.queue_input('button', Button.BUTTON_Z, current_frame + 1 + grab_offset, current_frame + 2 + grab_offset)

def queue_jab(kb_controller, player, jab_count=1, gentleman=False, delay=0, hold_frames=0):
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
    if jab_count == 0:
        return
    
    local_char = player.character
    for i in range(jab_count):
        start = current_frame + (2 * i) + 1
        end = current_frame + (2 * i) + 2
        # Third jab needs more time
        if i == 2:
            start += 5
            end += 5
            if local_char == Character.CPTFALCON:
                start += 5
                end += 5
                if not gentleman:
                    start += 15
                    end += 50
        if i == 0:
            start += delay
            end += delay
        kb_controller.queue_input(
            'button',
            Button.BUTTON_A,
            start,
            end + hold_frames
        )

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

def handle_techchase(kb_controller, gamestate, player, opponent, framedata):
    if (not player.on_ground or kb_controller.inputs_reserved >= gamestate.frame):
        return
    
    last_attack_frame = framedata.last_frame(player.character, player.action)
    check_attack = (framedata.is_attacking(player) and
                    player.action_frame > last_attack_frame - console.online_delay)
    
    if check_attack:
        return
    
    opp_char = opponent.character
    chase_scenario = opponent.action
    is_damaged = framedata.is_damaged(opponent)
    can_chase = (framedata.is_roll(opp_char, chase_scenario) and not
                 check_attack)
    # Skip if no chase necessary
    if not can_chase and (not is_damaged or opponent.off_stage):
        return
    
    # We dont chase throws, as we want the player to chase them
    if framedata.is_thrown(opponent):
        return
    
    current_frame = opponent.action_frame
    local_char = player.character
    first_grab_frame = framedata.first_hitbox_frame(local_char, Action.GRAB) + console.online_delay
    last_grab_frame = framedata.last_hitbox_frame(local_char, Action.GRAB) + console.online_delay
    time_to_chase = framedata.last_roll_frame(opp_char, chase_scenario) - current_frame
    is_attack = framedata.is_attack(opp_char, chase_scenario)
    if chase_scenario == Action.NEUTRAL_GETUP:
        time_to_chase = 30 - current_frame
    elif is_attack or is_damaged:
        time_to_chase = framedata.last_frame(opp_char, chase_scenario) - current_frame
    
    target_pos_x = framedata.roll_end_position(gamestate, opponent)
    target_pos_y = opponent.y
    is_mistech = framedata.has_misteched(opponent)
    if is_mistech:
        opp_speed_x = opponent.speed_x_attack + opponent.speed_ground_x_self
        target_pos_x += framedata.slide_distance(opponent, opp_speed_x, opponent.action_frame)
    elif framedata.is_hit(opponent) or not opponent.on_ground:
        time_to_chase = opponent.hitstun_frames_left
        target_pos_x, target_pos_y, _ = framedata.project_hit_location(gamestate, opponent)
    
    # Account for delay
    time_to_chase -= console.online_delay
    
    move_location = get_slide_pos(player, framedata, console.online_delay)
    pred_dx = abs(move_location[0] - target_pos_x)
    
    dy = abs(player.y - target_pos_y)
    if dy < 2 and not opponent.on_ground:
        return
    
    if dy > 8:
        return
    
    current_facing = player.facing
    # If we are turning already, we assume it is the other direction
    if player.action == Action.TURNING:
        current_facing = not current_facing
    new_facing = target_pos_x >= player.x
    new_pred_facing = target_pos_x >= move_location[0]
        
    shielding = framedata.is_shielding(player)
    
    do_wavedash = False
    target_dx = 15
    dashgrab_dx = 10
    if local_char == Character.CPTFALCON:
        do_wavedash = True
        target_dx = 15
        dashgrab_dx = 10
    elif local_char == Character.MARTH:
        target_dx = 25
        dashgrab_dx = 15
    
    if do_wavedash:
        if (pred_dx < target_dx and
            abs(player.speed_ground_x_self) > 0.5 and
            new_pred_facing == new_facing and
            time_to_chase > first_grab_frame + 15):
            queue_wavedash(kb_controller, player, 0, 0.5, -0.3)
    
    player_size = float(framedata.characterdata[local_char]["size"])
    in_range = (new_facing == current_facing and
                pred_dx < target_dx and
                dy < player_size)
    
    can_turn = (new_facing != current_facing and
                time_to_chase > last_grab_frame and
                not is_mistech)
    
    if (can_turn and
        pred_dx < target_dx and
        dy < player_size):
        queue_turn(kb_controller, new_facing)
    
    can_grab = (in_range and
                time_to_chase <= last_grab_frame and
                time_to_chase >= first_grab_frame)
    
    if is_damaged and chase_scenario == Action.GRAB_PUMMELED:
        can_grab = False
    
    # 12 frames is arbitrary, but roughly a good enough breathing room
    # After 20 frames, most mistechs are either finished or cannot be hit
    currently_misteching = (current_frame < 10 and chase_scenario == Action.TECH_MISS_UP or chase_scenario == Action.TECH_MISS_DOWN)
    can_jab = (in_range and currently_misteching and
               (player.action == Action.CROUCH_START or
                player.action == Action.CROUCH_END or
                player.action == Action.STANDING or
                player.action == Action.TURNING or
                player.action == Action.WALK_FAST or
                player.action == Action.WALK_MIDDLE or
                player.action == Action.WALK_SLOW) and
               (player.character != Character.GANONDORF))
    if can_jab:
        queue_jab(kb_controller, player, hold_frames=time_to_chase)
        return
    
    dash_grab = 0
    if pred_dx > dashgrab_dx:
        dash_grab = 1 if new_facing else -1
    
    if can_grab and not is_attack and not is_mistech:
        queue_jcgrab(kb_controller, player, dash_grab)
    elif is_attack:
        if pred_dx < 25 and not shielding:
            queue_shield(kb_controller, frames=framedata.last_hitbox_frame(opp_char, chase_scenario) - current_frame)
        elif new_facing == current_facing and shielding:
            queue_jcgrab(kb_controller, player)

def queue_crouch(kb_controller, frames=1, delay=0, use_current_frame=False):
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
    
    if use_current_frame and current_frame != kb_controller.gamestate.frame:
        current_frame -= 1
    
    current_frame += delay
    
    stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.DOWN)
    left_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.LEFT)
    rigth_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.RIGHT)
    if kb_controller.hotkeys_state[left_input] or kb_controller.hotkeys_state[rigth_input]:
        kb_controller.queue_input('stick', {'stick': Button.BUTTON_MAIN, 'x': 0.5, 'y': 0.5}, current_frame + 1, current_frame + 1)
        current_frame += 1
    
    _, new_y = kb_controller.get_tilt(stick_input, False, True)
    kb_controller.queue_input('stick', {'stick': Button.BUTTON_MAIN, 'x': 0.5, 'y': new_y}, current_frame + 1, current_frame + 1 + frames)
    kb_controller.queue_redo(current_frame + 1 + frames, stick_input)

def queue_cstick(kb_controller, analog_direction, use_current_frame=False):
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
    
    if use_current_frame and current_frame != kb_controller.gamestate.frame:
        current_frame -= 1
    
    if analog_direction == Analog.NEUTRAL:
        stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_C, Analog.RIGHT)
        kb_controller.queue_input('stick', {'stick': Button.BUTTON_MAIN, 'x': 0.5, 'y': 0.5}, current_frame + 1, current_frame + 1)
        kb_controller.queue_input('button', Button.BUTTON_A, current_frame + 2, current_frame + 3)
        kb_controller.queue_redo(current_frame + 3, stick_input)
        return

    stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_C, analog_direction)
    offset = 0
    if kb_controller.hotkeys_state[stick_input]:
        kb_controller.queue_input('stick', {'stick': Button.BUTTON_C, 'x': 0.5, 'y': 0.5}, current_frame + 1, current_frame + 1)
        offset = 1
    
    new_x, new_y = kb_controller.get_tilt(stick_input, False, True)
    kb_controller.queue_input('stick', {'stick': Button.BUTTON_C, 'x': new_x, 'y': new_y}, current_frame + 1 + offset, current_frame + 2 + offset)

def queue_special(kb_controller, analog_direction, frames=1, delay=0, use_current_frame=False):
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
    
    if use_current_frame and current_frame != kb_controller.gamestate.frame:
        current_frame -= 1
        
    current_frame += delay
    
    if analog_direction != Analog.NEUTRAL:
        stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, analog_direction)
        new_x, new_y = kb_controller.get_tilt(stick_input, False, True)
        # Ensure we do not use jump when doing up specials
        if analog_direction == Analog.UP:
            new_x = 0.5
            new_y = 1.3
        # Ensure we do not fast fall when doing down specials
        elif analog_direction == Analog.DOWN:
            new_x = 0.5
            new_y = 0.1725
        kb_controller.queue_input('stick', {'stick': Button.BUTTON_MAIN, 'x': new_x, 'y': new_y}, current_frame + 1, current_frame + 1 + frames)
    
    kb_controller.queue_input('button', Button.BUTTON_B, current_frame + 1, current_frame + 2 + frames)

def queue_ledgedash(kb_controller, player, jump_direction=0, hold_in_frames=0, wavedash_direction=0, max_x=0, wd_delay=0, wavedash_x=0, wavedash_y=0):
    # Drop from ledge, jump inwards, wavedash inwards
    queue_crouch(kb_controller)
    queue_shorthop(kb_controller, jump_direction, max_x, True)
    if hold_in_frames != 0:
        queue_turn(kb_controller, player.facing, hold_in_frames, max_x)
    if wavedash_y != 0:
        queue_wavedash(kb_controller, player, wavedash_direction, set_x=wavedash_x, set_y=wavedash_y, delay=wd_delay)

def handle_ledgedash(kb_controller, gamestate, player, opponent, interruptable=False, no_impact_land=False, ecb_shift=False):
    ledgedash_key = kb_controller.hotkeys_state[29]
    if (kb_controller.inputs_reserved >= gamestate.frame or not ledgedash_key or
        (player.action != Action.EDGE_HANGING and player.action != Action.EDGE_CATCHING)):
        if player.character == Character.CPTFALCON:
            if (player.action == Action.FALLING and
                (player.action_frame >= 1 and player.action_frame <= 8)):
                ecb_shift = True
            elif (player.action == Action.SWORD_DANCE_3_LOW and
                (player.action_frame >= 44 and player.action_frame <= 50) or
                (player.action_frame >= 55 and player.action_frame <= 58)):
                no_impact_land = True
            else:
                no_impact_land = False
        elif player.character == Character.FALCO:
            if (player.action == Action.FALLING and
                (player.action_frame == 1 or
                (player.action_frame >= 4 and player.action_frame <= 8))):
                ecb_shift = True
            elif player.action == Action.SWORD_DANCE_1_AIR:
                ecb_shift = True
            elif (player.action == Action.SWORD_DANCE_4_MID and
                (player.action_frame == 22)):
                ecb_shift = True
            elif (player.action == Action.DEAD_FALL and
                  (player.action_frame == 7)):
                ecb_shift = True
            else:
                ecb_shift = False
        elif player.character == Character.GANONDORF:
            if (player.action == Action.SWORD_DANCE_3_LOW and
                (player.action_frame == 51 or player.action_frame == 54)):
                ecb_shift = True
            elif (player.action == Action.JUMPING_ARIAL_FORWARD and
                  player.action_frame == 14 or
                  (player.action_frame >= 28 and player.action_frame <= 33)):
                ecb_shift = True
            else:
                ecb_shift = False
        elif player.character == Character.LUIGI:
            if (player.action == Action.FALLING and
                (player.action_frame >= 6 and player.action_frame <= 9)):
                ecb_shift = True
            elif (player.action == Action.SWORD_DANCE_4_MID and
                  (player.action_frame == 26)):
                ecb_shift = True
            else:
                ecb_shift = False
        elif player.character == Character.SHEIK:
            if (player.action == Action.FALLING and
                (player.action_frame == 1 or player.action_frame == 3 or player.action_frame >= 5)):
                ecb_shift = True
            elif (player.action == Action.DEAD_FALL):
                ecb_shift = True
            elif (player.action == Action.DOWN_B_GROUND_START and
                  (player.action_frame >= 23 and player.action_frame <= 28) or
                  player.action_frame == 39):
                ecb_shift = True
            else:
                ecb_shift = False
        return interruptable, no_impact_land, ecb_shift
    
    finish_wavedash = kb_controller.hotkeys_state[25]
    finish_interrupt = kb_controller.hotkeys_state[24]
    force_normal_stall = kb_controller.hotkeys_state[23]
    left_hotkey = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.LEFT)
    pressing_left = kb_controller.hotkeys_state[left_hotkey]
    right_hotkey = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.RIGHT)
    pressing_right = kb_controller.hotkeys_state[right_hotkey]
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
    
    max_x = 1.3 if player.facing else -0.3
    jump_direction = 1 if player.facing else -1
    wavedash_direction = 1 if player.facing else -1
    wavedash_x = -0.3 if player.facing else 1.3
    wavedash_y = -0.3
    jump_in_x = 1.3 if player.facing else -0.3
    
    local_char = player.character
    jump_in_frames = 6
    hold_in_frames = 2
    fall_frames = 4
    fast_fall_interrupt = False
    fast_fall_stall_start = False
    fast_fall_stall_wait = 0
    fast_fall_stall_end = True
    aerial_interrupt = Analog.LEFT if player.facing else Analog.RIGHT
    always_interruptable = False
    jump_regrab = True
    normal_stall = True
    wd_delay = 0
    nil_delay = 0
    if finish_wavedash or finish_interrupt:
        wavedash_x = 1.3 if player.facing else -0.3
        wavedash_y += 0.37
    if local_char == Character.CPTFALCON:
        jump_in_frames = 9
        hold_in_frames = 6
        if gamestate.stage == melee.Stage.YOSHIS_STORY:
            hold_in_frames = 7
        if finish_wavedash:
            hold_in_frames = 8
        if interruptable and finish_interrupt:
            hold_in_frames = 4
        fall_frames = 5
    if local_char == Character.DK:
        aerial_interrupt = None
        jump_in_frames = 7
        hold_in_frames = 5
        fall_frames = 8
        if finish_wavedash:
            hold_in_frames = 7
    elif local_char == Character.FALCO:
        aerial_interrupt = None
        normal_stall = False
        jump_in_frames = 0
        hold_in_frames = 1 if pressing_right or pressing_left else 2
        if ecb_shift:
            hold_in_frames = 2
        # elif finish_wavedash and (pressing_left or pressing_right):
        #     wavedash_y = -0.3 + 0.21 # Using a steep wavedash to hit the ground earlier
        fall_frames = 10
    elif local_char == Character.GANONDORF:
        wavedash_x += 0.55 if player.facing else -0.55
        jump_in_frames = 13
        hold_in_frames = 1
        if finish_wavedash:
            hold_in_frames = 11
            if ecb_shift:
                hold_in_frames = 12
            if gamestate.stage == melee.Stage.YOSHIS_STORY:
                if not pressing_left and not pressing_right:
                    hold_in_frames = 13
            elif gamestate.stage == melee.Stage.POKEMON_STADIUM:
                if not pressing_left and not pressing_right:
                    hold_in_frames = 13
        aerial_interrupt = None
        if finish_interrupt:
            wavedash_y = 0
            hold_in_frames = 16
        fall_frames = 5
    elif local_char == Character.JIGGLYPUFF:
        aerial_interrupt = None
        normal_stall = False
        if finish_wavedash:
            hold_in_frames = 3
        fall_frames = 11
    elif local_char == Character.LINK:
        wavedash_x += 0.55 if player.facing else -0.55
        jump_in_frames = 7
        hold_in_frames = 0
        fast_fall_stall_wait = 9
        if gamestate.stage == melee.Stage.YOSHIS_STORY:
            hold_in_frames = 1
        if finish_wavedash:
            hold_in_frames = 5
        # Select a random aerial interrupt
        rand_int = random.randint(0, 4)
        if rand_int == 0:
            aerial_interrupt = Analog.NEUTRAL
        elif rand_int == 1:
            aerial_interrupt = Analog.UP
        elif rand_int == 2:
            aerial_interrupt = Analog.LEFT
        elif rand_int == 3:
            aerial_interrupt = Analog.DOWN
        elif rand_int == 4:
            aerial_interrupt = Analog.RIGHT
        always_interruptable = True
    elif local_char == Character.LUIGI:
        wavedash_x += 0.55 if player.facing else -0.55
        jump_in_frames = 5
        if ecb_shift:
            jump_in_frames = 7
            if gamestate.stage == melee.Stage.BATTLEFIELD:
                jump_in_frames = 9
        hold_in_frames = 5
        # fast_fall_stall_wait = 4
        fall_frames = 20
        if finish_wavedash or finish_interrupt:
            hold_in_frames = 3
            # After stalling, Luigi's ECB is shifted, so we have to modify the wavedash
            if ecb_shift:
                hold_in_frames = 4
                wavedash_direction = 0
        fast_fall_interrupt = True
        fast_fall_stall_start = True
        aerial_interrupt = None
        always_interruptable = True
        jump_regrab = False
    elif local_char == Character.MARTH:
        jump_in_frames = 11
        hold_in_frames = 5
        fall_frames = 7
        if finish_wavedash or finish_interrupt:
            hold_in_frames = 11
        else:
            wavedash_x += 0.55 if player.facing else -0.55
        aerial_interrupt = None
    elif local_char == Character.MEWTWO:
        normal_stall = False
        jump_regrab = False
    elif local_char == Character.PEACH:
        fall_frames = 14
        if gamestate.stage == melee.Stage.BATTLEFIELD:
            fall_frames = 12
        if finish_wavedash:
            hold_in_frames = 22
            if gamestate.stage == melee.Stage.BATTLEFIELD:
                jump_direction = 0
                hold_in_frames = 0
                wd_delay = 24
                wavedash_y = 0.5
        normal_stall = False
        jump_regrab = False
    elif local_char == Character.PICHU:
        normal_stall = False
        jump_regrab = False
        if finish_wavedash:
            hold_in_frames = 0
    elif local_char == Character.ROY:
        jump_in_frames = 11
        fast_fall_stall_wait = 2
        if finish_wavedash:
            hold_in_frames = 10
        elif finish_interrupt:
            fall_frames = 2
            if gamestate.stage == melee.Stage.YOSHIS_STORY:
                hold_in_frames = 9
            else:
                hold_in_frames = 15
        fast_fall_interrupt = True
        aerial_interrupt = Analog.NEUTRAL
        always_interruptable = True
    elif local_char == Character.SAMUS:
        aerial_interrupt = Analog.UP
        always_interruptable = True
        jump_in_frames = 11
        hold_in_frames = 4
        fall_frames = 5
        if gamestate.stage == melee.Stage.YOSHIS_STORY:
            fast_fall_stall_end = False
        if gamestate.stage == melee.Stage.BATTLEFIELD:
            jump_in_x = 0.9 if player.facing else 0.1
        if finish_wavedash:
            hold_in_frames = 11
            if gamestate.stage == melee.Stage.BATTLEFIELD:
                jump_direction = 0
                hold_in_frames = 11
        if finish_interrupt:
            fall_frames = 1
            hold_in_frames = 7
    elif local_char == Character.SHEIK:
        wavedash_x += 0.55 if player.facing else -0.55
        jump_in_frames = 8
        hold_in_frames = 5
        if ecb_shift:
            hold_in_frames = 6
        if gamestate.stage == melee.Stage.BATTLEFIELD:
            jump_in_frames = 9
            if ecb_shift:
                jump_in_frames = 10
        fall_frames = 6
        if finish_wavedash:
            hold_in_frames = 4
            if ecb_shift:
                hold_in_frames = 5
        fast_fall_stall_start = True
        jump_regrab = False
    
    # Only wavedash in the direction the player is moving
    if ((finish_wavedash or
         (finish_interrupt and not aerial_interrupt)) and
        ((not pressing_left and not pressing_right) or
        (pressing_left and player.facing) or
        (pressing_right and not player.facing))):
        wavedash_direction = 0
        wavedash_x = 0.5
    
    # No impact lands are high priority, so we skip stalls
    if no_impact_land and (finish_wavedash or finish_interrupt):
        queue_crouch(kb_controller)
        queue_shorthop(kb_controller, jump_direction, delay=nil_delay)
        return False, False, False
    
    if finish_wavedash:
        queue_ledgedash(kb_controller, player, jump_direction, hold_in_frames, wavedash_direction, max_x, wd_delay, wavedash_x, wavedash_y)
        return False, False, False
    
    if finish_interrupt and aerial_interrupt and (interruptable or always_interruptable):
        # Drop from ledge, jump inwards, do aerial interrupt input
        queue_crouch(kb_controller, fall_frames if fast_fall_interrupt else 1)
        queue_shorthop(kb_controller, jump_direction, jump_in_x, True)
        queue_turn(kb_controller, player.facing, hold_in_frames, max_x)
        queue_cstick(kb_controller, aerial_interrupt)
        return False, False, False
    elif finish_interrupt and not aerial_interrupt:
        queue_ledgedash(kb_controller, player, jump_direction, hold_in_frames, wavedash_direction, max_x, wd_delay, wavedash_x, wavedash_y)
        return False, False, False
    
    dx = abs(player.x - opponent.x)
    
    wait_type = random.randint(0, 1)
    if force_normal_stall:
        wait_type = 0
    if wait_type == 0 and not finish_interrupt and normal_stall and dx > 15:
        # Drop from ledge, jump inwards, wavedash back to ledge
        queue_crouch(kb_controller, 2 if fast_fall_stall_start else 1)
        queue_shorthop(kb_controller, jump_direction, jump_in_x, use_current_frame=True)
        queue_turn(kb_controller, player.facing, jump_in_frames, max_x)
        queue_wavedash(kb_controller, player, -1 if player.facing else 1, wavedash_x, wavedash_y)
        if hold_in_frames != 0:
            queue_turn(kb_controller, player.facing, hold_in_frames, max_x)
        if fast_fall_stall_end:
            queue_crouch(kb_controller, delay=fast_fall_stall_wait)
        return False, True, False
    elif (wait_type == 1 and jump_regrab) or (wait_type == 0 and jump_regrab and (dx <= 15 or finish_interrupt)):
        # Drop from ledge with fast fall and jump
        queue_crouch(kb_controller, fall_frames)
        queue_shorthop(kb_controller)
        return True, False, False
    else:
        if local_char == Character.FALCO:
            # Drop from ledge and up b or side b into ledge
            queue_crouch(kb_controller)
            queue_jump(kb_controller, player, jump_direction)
            analog_direction = Analog.UP
            special_delay = 0
            if gamestate.stage == melee.Stage.BATTLEFIELD:
                special_delay = 2
            if random.randint(0, 1) == 0:
                analog_direction = Analog.RIGHT if player.facing else Analog.LEFT
                if gamestate.stage == melee.Stage.BATTLEFIELD:
                    special_delay = 1
            queue_special(kb_controller, analog_direction, delay=special_delay)
        elif local_char == Character.LUIGI:
            # Drop from ledge and up b up to ledge
            queue_crouch(kb_controller, fall_frames)
            queue_special(kb_controller, Analog.UP)
        elif local_char == Character.MEWTWO:
            # Soft drop from ledge and up b into ledge
            queue_turn(kb_controller, not player.facing, 6)
            queue_special(kb_controller, Analog.UP, use_current_frame=True)
            queue_turn(kb_controller, player.facing, 9)
        elif local_char == Character.PEACH:
            # Drop from ledge and up b up to ledge
            queue_crouch(kb_controller, fall_frames)
            queue_special(kb_controller, Analog.UP)
        elif local_char == Character.PICHU:
            # Drop from ledge and up b into ledge
            queue_crouch(kb_controller)
            queue_special(kb_controller, Analog.UP)
            queue_turn(kb_controller, player.facing, 9)
        elif local_char == Character.SHEIK:
            # Drop from ledge and up b up to ledge
            queue_crouch(kb_controller, fall_frames)
            queue_special(kb_controller, Analog.UP)
            
        return False, False, False

def handle_gentleman(kb_controller, gamestate, player, opponent, framedata):
    active_key = kb_controller.hotkeys_state[30]
    if (kb_controller.inputs_reserved >= gamestate.frame or not active_key or
        not player.on_ground or framedata.is_attacking(player)):
        return
    
    move_location = get_slide_pos(player, framedata, 3)
    target_pos = get_fly_pos(opponent, gamestate, framedata, 3)
    pred_dx = abs(move_location[0] - target_pos[0])
    
    gentleman = False
    opponent_size = float(framedata.characterdata[opponent.character]["size"])
    if pred_dx < 7 + opponent_size:
        gentleman = True
        
    # do a single jab and repeat
    if kb_controller.hotkeys_state[25]:
        queue_jab(kb_controller, player, 1)
        crouch_delay = 13
        if gentleman:
            crouch_delay += 2
        queue_crouch(kb_controller, delay=crouch_delay)
        return
    
    queue_jab(kb_controller, player, 3, gentleman)

def queue_zdrop(kb_controller, player, framedata, with_facing=0, use_current_frame=False):
    if player.on_ground:
        queue_shorthop(kb_controller, with_facing, use_current_frame=True)
    
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
    
    if use_current_frame and current_frame != kb_controller.gamestate.frame:
        current_frame -= 1
    
    # Ensure stick is neutral
    stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.RIGHT)
    kb_controller.queue_input('stick', {'stick': Button.BUTTON_MAIN, 'x': 0.5, 'y': 0.5}, current_frame + 1, current_frame + 2)
    kb_controller.queue_redo(current_frame + 2, stick_input)
    
    jumpsquat_frames = framedata.last_frame(player.character, Action.KNEE_BEND)
    if jumpsquat_frames != -1:
        current_frame += jumpsquat_frames
    else:
        # Default jumpsquat placeholder
        current_frame += 4
    
    kb_controller.queue_input(
        'button',
        Button.BUTTON_Z,
        current_frame + 1,
        current_frame + 2
    )

def calculate_wavedash_x(start_x, target_x, facing, optimal_distance=10):
    dx = abs(start_x - target_x)
    percentage_wavedash = (dx / optimal_distance)
    wavedash_x = 1.3 if facing else -0.3
    offset_x = -0.625 if facing else 0.625
    wavedash_x += (offset_x * (1 - percentage_wavedash))
    return wavedash_x

def handle_aciddrop(kb_controller, gamestate, player, opponent, framedata, has_dropped=False, holding_bomb=False, threw_bomb=False):
    active_key = kb_controller.hotkeys_state[30]
    if (kb_controller.inputs_reserved >= gamestate.frame or not active_key or
        framedata.is_attacking(player)):
        return has_dropped
    
    # Check if airborne
    if (not player.on_ground and
        not player.action == Action.AIRDODGE and
        player.y > 4):
        return has_dropped
    
    # On ledge, pull a bomb
    if player.action == Action.EDGE_HANGING or player.action == Action.EDGE_CATCHING:
        if not holding_bomb:
            queue_crouch(kb_controller)
            queue_shorthop(kb_controller, use_current_frame=True)
            queue_special(kb_controller, Analog.DOWN, use_current_frame=True)
            holding_bomb = True
        else:
            return False
    
    # When offstage, drop the bomb and hit it for a recovery
    if player.off_stage:
        if holding_bomb:
            if player.jumps_left != 0 or player.action == Action.JUMPING_ARIAL_FORWARD:
                queue_jump(kb_controller, player)
                queue_zdrop(kb_controller, player, framedata, use_current_frame=True)
                queue_cstick(kb_controller, Analog.NEUTRAL, True)
            else:
                queue_cstick(kb_controller, Analog.UP)
                return True
        elif threw_bomb:
            queue_special(kb_controller, Analog.UP)
    
    # Check if landing
    is_landing = (
        (player.action == Action.LANDING_SPECIAL or
         player.action == Action.LANDING) and
        player.action_frame > console.online_delay + 1
    )
    in_jumpsquat = player.action == Action.KNEE_BEND and player.action_frame > console.online_delay
    if is_landing or in_jumpsquat:
        return has_dropped
    
    if framedata.is_item_pulling(player):
        return False
    
    if has_dropped:
        # Pick the bomb back up
        queue_jab(kb_controller, player)
        return False
    
    # No bomb to drop
    if not holding_bomb:
        return False
    
    move_location = get_slide_pos(player, framedata, 3)
    target_pos = get_fly_pos(opponent, gamestate, framedata, 3)
    new_pred_facing = target_pos[0] >= player.x
    bomb_drop_x = move_location[0]
    bomb_drop_x += 7.5 if new_pred_facing else -7.5
    pred_dx = abs(move_location[0] - target_pos[0])
    pred_dy = abs(move_location[1] - target_pos[1])
    true_dx = abs(bomb_drop_x - target_pos[0])
    if true_dx > 10 or pred_dy > 10:
        return False
    
    # Turn to face the opponent
    if new_pred_facing != player.facing:
        queue_turn(kb_controller, new_pred_facing, 1)
    
    new_pred_facing = target_pos[0] >= bomb_drop_x
    
    # Calculate wavedash x based on distance to bomb drop position
    wavedash_x = calculate_wavedash_x(bomb_drop_x, target_pos[0], new_pred_facing)
    
    # Drop the bomb
    queue_zdrop(kb_controller, player, framedata)
    # Wavedash towards the bomb's predicted position
    queue_wavedash(kb_controller, player, new_pred_facing if pred_dx > 10 else 0, wavedash_x, -0.3, False, True)
    return True

def handle_airdash(kb_controller, gamestate, player, framedata):
    active_key = kb_controller.hotkeys_state[30]
    if (kb_controller.inputs_reserved >= gamestate.frame or not active_key or
        not player.on_ground or framedata.is_attacking(player)):
        return
    
    if player.action != Action.LANDING_SPECIAL:
        queue_shorthop(kb_controller, 0, use_current_frame=True)
        
        dash_delay = 1
        if player.character == Character.MEWTWO:
            dash_delay = 3
        
        queue_special(kb_controller, Analog.UP, delay=dash_delay, use_current_frame=True)

def handle_airturn(kb_controller, gamestate, player, framedata):
    active_key = kb_controller.hotkeys_state[30]
    if (kb_controller.inputs_reserved >= gamestate.frame or not active_key or
        player.on_ground or framedata.is_attacking(player)):
        return

    queue_turn(kb_controller, not player.facing)
    hold_frames = 1
    if player.character == Character.SHEIK:
        hold_frames = 7
    queue_special(kb_controller, Analog.NEUTRAL, hold_frames, use_current_frame=True)
    # DK is default 4
    cancel_delay = 4
    if player.character == Character.MEWTWO:
        cancel_delay = 14
    elif player.character == Character.SHEIK:
        cancel_delay = -2
        
    queue_shield(kb_controller, delay=cancel_delay)
    # Set reserve time so it loops at the correct frame
    kb_controller.inputs_reserved += hold_frames + cancel_delay

def check_projectile_collision(player, opponent, projectile):
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
    check_frames = console.online_delay + 2
    if opponent.character == Character.SAMUS:
        check_frames += 2
    for i in range(0, console.online_delay + 2):
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

def handle_projectiles(kb_controller, gamestate, player, framedata, opponent, knownprojectiles):
    if (not player.on_ground or kb_controller.inputs_reserved >= gamestate.frame or
        framedata.is_attacking(player) or framedata.is_shielding(player)):
        return
    
    for projectile in knownprojectiles:
        will_collide = check_projectile_collision(player, opponent, projectile)
        if will_collide:
            queue_shield(kb_controller, redo=False, zpress=True)

def is_shielding(player, kb_controller, framedata):
    if not framedata.is_actionable(player) or player.action == Action.KNEE_BEND:
        return False
    
    button_shield = False
    shield_buttons = kb_controller.get_button_hotkey(Button.BUTTON_L)
    shield_buttons.append(kb_controller.get_button_hotkey(Button.BUTTON_R))
    for button in shield_buttons:
        if kb_controller.hotkeys_state[button]:
            button_shield = True
    
    return button_shield or framedata.is_shielding(player)

def handle_shieldoption(kb_controller, gamestate, player, framedata, opponent, stage_bounds):
    if (not player.on_ground or kb_controller.inputs_reserved >= gamestate.frame or
        player.hitstun_frames_left < 0 or not is_shielding(player, kb_controller, framedata)):
        kb_controller.force_tilt = False
        kb_controller.force_tilt_platform = False
        return
    
    # Ensure we do not roll while shielding by forcing tilt values instead of full stick values
    kb_controller.force_tilt = True
    if player.y > 1:
        kb_controller.force_tilt_platform = True
    if kb_controller.hotkeys_state[24] or kb_controller.hotkeys_state[25]:
        kb_controller.force_tilt = False
        kb_controller.force_tilt_platform = False
    
    target_pos = get_fly_pos(opponent, gamestate, framedata, 3)
    if opponent.on_ground and framedata.is_actionable(opponent):
        target_pos = get_slide_pos(opponent, framedata, 3)
    
    shield_buttons = kb_controller.get_button_hotkey(Button.BUTTON_L)
    for button in shield_buttons:
        if kb_controller.hotkeys_state[button]:
            # Modify current stick values to aim up/down towards the opponent
            if target_pos[1] > player.y:
                kb_controller.current_stick_state[melee.Button.BUTTON_MAIN]['y'] = 0.825
            return
    
    time_left = max(player.hitlag_left, console.online_delay)
    
    if player.action == Action.SHIELD_REFLECT:
        time_left += 2
    elif player.action != Action.SHIELD_STUN:
        time_left = 0
    
    frames_left = framedata.iasa(opponent.character, opponent.action) - opponent.action_frame
    grab_frame = framedata.first_hitbox_frame(player.character, Action.GRAB)
    dx = target_pos[0] - player.x
    new_facing = dx > 0
    can_grab = (frames_left > grab_frame and new_facing == player.facing and abs(dx) < 15)
    current_frame = gamestate.frame + time_left
    if can_grab:
        kb_controller.queue_input('button', Button.BUTTON_A, current_frame, current_frame + 1)
        return
        
    right_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.RIGHT)
    left_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.LEFT)
    direction = 1 if kb_controller.hotkeys_state[right_input] else -1 if kb_controller.hotkeys_state[left_input] else 0
    
    if stage_bounds != None:
        stage_left_dx = abs(player.x - stage_bounds[0][0])
        stage_right_dx = abs(stage_bounds[1][0] - player.x)
        if (stage_left_dx < 5 or stage_right_dx < 5):
            if direction == -1:
                direction = 1
            elif direction == 1:
                direction = -1
            
    closest_platform = framedata.get_closest_platform(gamestate, [player.x, player.y])
    if not closest_platform is None:
        platform_x, platform_y, platform_width = closest_platform
        half_width = platform_width/2
        # Check if we're close enough to the platform to wave dash
        if abs(player.x - platform_x) > half_width or player.off_stage:
            return
    
    queue_wavedash(kb_controller, player, direction, delay=time_left)

def handle_walltech(kb_controller, gamestate, player, stage_bounds_ground, framedata, has_teched=False, sdi_frames=0):
    if player.on_ground:
        return False, 0
    
    # Can only tech if in this range of damage states
    if player.action.value < Action.DAMAGE_HIGH_1.value or player.action.value > Action.DAMAGE_FLY_ROLL.value:
        return False, 0
    
    # We ensure we only sdi in hitlag
    if player.hitlag_left <= console.online_delay - 1:
        return False, 0
    
    current_frame = gamestate.frame
    stage = gamestate.stage
    pos_x = player.position.x
    pos_y = player.position.y
    player_size = float(framedata.characterdata[player.character]["size"])
    dx = abs(abs(pos_x) - stage_bounds_ground[1][0])
    dy = abs(abs(pos_y) - player_size)
    teched = has_teched
    
    # Calculate maximum travel distance and skip if no tech possible
    sdi_dist = 16
    if pos_y > -6 or dx > sdi_dist or dy > sdi_dist:
        return False, 0
    
    # Ensure the analog stick is reset to neutral
    # stick_val = kb_controller.current_stick_state[melee.Button.BUTTON_MAIN]
    # if stick_val['x'] != 0.5 or stick_val['y'] != 0.5:
    #     controller.tilt_analog(Button.BUTTON_MAIN, 0.5, 0.5)
    
    # Ensure shield button is unpressed
    kb_controller.inputs_reserved = current_frame + 2
    shield_input = kb_controller.get_button_hotkey(Button.BUTTON_L)[1]
    if kb_controller.hotkeys_state[shield_input]:
        controller.release_button(Button.BUTTON_L)
        kb_controller.inputs_reserved += 1
    
    set_x = -0.3 if pos_x > 0 else 1.3
    set_y = 1.3 if pos_y < 0 else -0.3
    
    speed_x = player.speed_x_attack + player.speed_air_x_self
    speed_y = player.speed_y_attack + player.speed_y_self
    
    upwards_angle = speed_y > abs(speed_x)
    inwards_angle = speed_x > abs(speed_y)
    if pos_x > 0:
        inwards_angle = speed_x < -abs(speed_y)
    outwards_angle = speed_x < -abs(speed_y)
    if pos_x > 0:
        outwards_angle = speed_x > abs(speed_y)
    downwards_angle = speed_y < -abs(speed_x)
    
    tech_ready = False
    # We SDI depending on the angle
    if upwards_angle:
        if sdi_frames == 0:
            # Inwards
            set_x = -0.3 if pos_x > 0 else 1.3
            set_y = 0.5
        elif sdi_frames == 1:
            # Upwards
            set_x = 0.5
            set_y = 1.3
        elif sdi_frames == 2:
            # Inwards again, then tech
            set_x = -0.3 if pos_x > 0 else 1.3
            set_y = 0.5
            tech_ready = True
        else:
            set_x = -0.3 if pos_x > 0 else 1.3
            set_y = 0.5
    elif inwards_angle:
        if sdi_frames == 0:
            # Upwards
            set_x = 0.5
            set_y = 1.3
            if (stage != melee.Stage.BATTLEFIELD and
                stage != melee.Stage.POKEMON_STADIUM and
                stage != melee.Stage.YOSHIS_STORY):
                tech_ready = True
        elif sdi_frames == 1:
            # In and up, then tech
            set_x = -0.3 if pos_x > 0 else 1.3
            set_y = 1.3
            if (stage == melee.Stage.BATTLEFIELD or
                stage == melee.Stage.POKEMON_STADIUM or
                stage == melee.Stage.YOSHIS_STORY):
                tech_ready = True
        else:
            set_x = -0.3 if pos_x > 0 else 1.3
            set_y = 1.3
    elif outwards_angle:
        if sdi_frames == 0:
            if stage != melee.Stage.BATTLEFIELD:
                # Upwards
                set_x = 0.5
                set_y = 1.3
            else:
                # Inwards
                set_x = -0.3 if pos_x > 0 else 1.3
                set_y = 0.5
        elif sdi_frames == 1:
            if stage != melee.Stage.BATTLEFIELD:
                # In and up, then tech
                set_x = -0.3 if pos_x > 0 else 1.3
                set_y = 1.3
                tech_ready = True
            else:
                # Upwards, and tech
                set_x = 0.5
                set_y = 1.3
                tech_ready = True
        elif sdi_frames == 2 and stage == melee.Stage.BATTLEFIELD:
            # Inwards again, then tech
            set_x = -0.3 if pos_x > 0 else 1.3
            set_y = 0.5
        else:
            set_x = -0.3 if pos_x > 0 else 1.3
            set_y = 1.3
            if stage == melee.Stage.BATTLEFIELD:
                set_x = -0.3 if pos_x > 0 else 1.3
                set_y = 0.5
    elif downwards_angle:
        if sdi_frames == 0:
            # Inwards
            set_x = -0.3 if pos_x > 0 else 1.3
            set_y = 0.5
        elif sdi_frames == 1:
            # In and up, then tech
            set_x = -0.3 if pos_x > 0 else 1.3
            set_y = 1.3
            tech_ready = True
        else:
            set_x = -0.3 if pos_x > 0 else 1.3
            set_y = 1.3
    
    controller.tilt_analog(Button.BUTTON_MAIN, set_x, set_y)
    
    if tech_ready and not has_teched:
        controller.press_button(Button.BUTTON_L)
        teched = True
    
    sdi_frames += 1

    # Ensure we reset inputs to previous states
    stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.RIGHT)
    kb_controller.queue_redo(current_frame + 2, stick_input)
    kb_controller.queue_input('button', Button.BUTTON_L, current_frame + 2, current_frame + 3)

    return teched, sdi_frames

def handle_samusattack(kb_controller, gamestate, player, framedata):
    active_key = kb_controller.hotkeys_state[30]
    do_missiles = kb_controller.hotkeys_state[25]
    if (kb_controller.inputs_reserved >= gamestate.frame or not active_key):
        return
    
    last_frame = framedata.last_frame(player.character, player.action)
    attacking = framedata.is_attacking(player) and player.action_frame < last_frame - console.online_delay
    if (do_missiles and framedata.is_actionable(player) and
        not attacking):
        direction = Analog.RIGHT if player.facing else Analog.LEFT
        if player.on_ground:
            missile_end = ((player.action == Action.SWORD_DANCE_2_HIGH and player.action_frame == 47) or
                           (player.action == Action.SWORD_DANCE_1 and player.action_frame == 57))
            # Shield drop
            if (missile_end or not attacking) and player.y > 1:
                queue_shield(kb_controller)
                queue_turn(kb_controller, player.facing, set_x = 0.5, set_y = 0.1625)
            elif missile_end:
                queue_shorthop(kb_controller, use_current_frame=True)
            elif player.y < 1 and not gamestate.stage in [melee.Stage.POKEMON_STADIUM, melee.Stage.YOSHIS_STORY]:
                queue_special(kb_controller, direction)
            elif player.action == Action.LANDING and player.action_frame == 1:
                queue_shorthop(kb_controller, use_current_frame=True)
        elif player.speed_y_self <= 0:
            # Fastfall missile
            queue_crouch(kb_controller)
            queue_special(kb_controller, direction, use_current_frame=True)
        else:
            # Normal missile
            queue_special(kb_controller, direction)
        return
    
    in_morphball = (player.action == Action.SWORD_DANCE_4_HIGH or
                    player.action == Action.SWORD_DANCE_4_MID or
                    player.action == Action.NEUTRAL_B_CHARGING)
    
    if not in_morphball and (not player.on_ground or framedata.is_attacking(player)):
        return
    
    action_frame = player.action_frame
    right_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.RIGHT)
    direction = True if kb_controller.hotkeys_state[right_input] else False
    
    if not in_morphball:
        queue_special(kb_controller, Analog.DOWN)
    elif action_frame == 36:
        queue_turn(kb_controller, direction, 1, set_x=0.5, set_y=0.5)
        queue_turn(kb_controller, not direction, 1)
        queue_turn(kb_controller, direction, 1)
        queue_crouch(kb_controller, frames=1)

def handle_shine(kb_controller, gamestate, player, opponent_player, framedata, shine_on_shield=False):
    active_key = kb_controller.hotkeys_state[30]
    in_shine = (player.action == Action.DOWN_B_GROUND_START or
                player.action == Action.DOWN_B_GROUND)
    if (not player.on_ground or kb_controller.inputs_reserved >= gamestate.frame or
        not active_key):
        return shine_on_shield
    
    if not in_shine and framedata.is_attacking(player):
        return False
    
    action_frame = player.action_frame
    right_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.RIGHT)
    left_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.LEFT)
    direction = 0
    if kb_controller.hotkeys_state[right_input]:
        direction = 1
    elif kb_controller.hotkeys_state[left_input]:
        direction = -1
        
    opponent_size = float(framedata.characterdata[opponent_player.character]["size"])
    
    if not in_shine and player.action != Action.KNEE_BEND:
        shine_delay = 0
        if player.action == Action.DASHING or is_shielding(opponent_player, kb_controller, framedata):
            queue_jump(kb_controller, player)
            shine_delay += 3
        queue_special(kb_controller, Analog.DOWN, delay=shine_delay)
        move_location = get_slide_pos(opponent_player, framedata, 3)
        if not opponent_player.on_ground:
            move_location = get_fly_pos(opponent_player, gamestate, framedata, 3)
        dist = abs(player.x - move_location[0])
        disty = abs(player.y - move_location[1])
        return True if dist < 11.8 and disty < opponent_size else False
    elif player.hitlag_left > 0:
        time_left = player.hitlag_left - console.online_delay
        if framedata.is_shielding(opponent_player):
            queue_jump(kb_controller, player, delay=time_left, use_current_frame=True)
            return True
        else:
            queue_wavedash(kb_controller, player, direction, use_current_frame=True, delay=time_left)
    elif not shine_on_shield:
        if direction != 0:
            queue_wavedash(kb_controller, player, direction, use_current_frame=True)
        else:
            queue_jump(kb_controller, player)
            queue_special(kb_controller, Analog.DOWN, delay=3)
    elif shine_on_shield and player.hitlag_left <= 0:
        queue_shorthop(kb_controller, direction, use_current_frame=True)
        queue_cstick(kb_controller, Analog.NEUTRAL)
        return False
    
    return shine_on_shield

def handle_edgecancel(kb_controller, gamestate, player, framedata):
    if (kb_controller.inputs_reserved >= gamestate.frame or
        player.on_ground or not framedata.is_attacking(player) or not kb_controller.edge_cancels):
        return
    
    move_position = get_fly_pos(player, gamestate, framedata, 2, 5)
    closest_edge, edge_type = framedata.get_closest_edge(gamestate, move_position)
    if closest_edge is None:
        return

    # Get character stats for movement calculations
    gravity = framedata.characterdata[player.character]["Gravity"]
    termvelocity = framedata.characterdata[player.character]["TerminalVelocity"]
    mobility = framedata.characterdata[player.character]["AirMobility"]
    airspeed = framedata.characterdata[player.character]["AirSpeed"]
    fastfallspeed = framedata.characterdata[player.character]["FastFallSpeed"]
    
    # Current speeds including both self movement and attack momentum
    speed_x = player.speed_air_x_self + player.speed_x_attack
    speed_y = player.speed_y_self + player.speed_y_attack

    x, y = move_position[0], move_position[1]
    edge_x, edge_y = closest_edge

    # Basic validation checks
    if y < edge_y and abs(edge_x - x) <= 50:
        return  # Must be above platform to edge cancel

    # Determine if we're moving towards the edge
    moving_towards_edge = (edge_type == -1 and speed_x < 0) or (edge_type == 1 and speed_x > 0)
    if not moving_towards_edge:
        # Original case: need more momentum towards edge
        if edge_type == 1:  # Right edge - need to move right
            mobility = abs(mobility)
        else:  # Left edge - need to move left
            mobility = -abs(mobility)
    else:
        # New case: potentially overshooting, may need to counter-turn
        # Flip mobility to oppose current movement
        if edge_type == 1:  # Right edge - need to counter left
            mobility = -abs(mobility)
        else:  # Left edge - need to counter right
            mobility = abs(mobility)

    frames_x = 0
    positions = []
    frame_found = False
    will_overshoot = False
    fastfall_frame = None
    can_fastfall = speed_y > 0  # Can only fastfall after reaching apex
    
    # Project movement frame by frame
    while frames_x < 60:  # Safety limit
        prev_y = y
        prev_x = x
        
        # Update vertical position and speed
        y += speed_y
        
        # Check if we've reached apex and can fastfall
        if speed_y > 0 and speed_y - gravity <= 0:
            can_fastfall = True
        
        speed_y -= gravity
        # Apply fastfall speed if we're past apex
        if can_fastfall:
            speed_y = max(-fastfallspeed, speed_y)
        else:
            speed_y = max(-termvelocity, speed_y)

        # Update horizontal position and speed
        x += speed_x
        speed_x += mobility
        speed_x = max(-airspeed, speed_x)
        speed_x = min(airspeed, speed_x)
        
        # Store trajectory for debugging
        positions.append((x, y))
        
        # Check for edge crossing
        if edge_y <= prev_y and edge_y > y:
            # For left edges, check if we cross from right to left
            # For right edges, check if we cross from left to right
            if edge_type == -1:
                if prev_x >= edge_x:
                    # Check if we'll overshoot
                    will_overshoot = x < edge_x - 5  # Allow small tolerance
                    frame_found = True
                    break
            else:  # edge_type == 1
                if prev_x <= edge_x:
                    # Check if we'll overshoot
                    will_overshoot = x > edge_x + 5  # Allow small tolerance
                    frame_found = True
                    break
        
        # If we can fastfall and haven't set the fastfall frame yet,
        # calculate if fastfalling now would get us to the edge
        if can_fastfall and fastfall_frame is None:
            test_y = y
            test_speed_y = -fastfallspeed
            frames_to_edge = 0
            
            while test_y > edge_y and frames_to_edge < 20:
                test_y += test_speed_y
                frames_to_edge += 1
            
            # If fastfalling now would get us to the edge at approximately
            # the same time as our horizontal movement, set the fastfall frame
            if frame_found or (frames_to_edge > 0 and frames_to_edge <= 5):
                fastfall_frame = frames_x + console.online_delay
        
        frames_x += 1

        # Early exit if we can't complete the edge cancel in time
        remaining_attack_frames = framedata.last_frame(player.character, player.action) - player.action_frame
        if frames_x > remaining_attack_frames:
            return

    if not frame_found:
        return

    # Queue the appropriate turn input based on movement needs
    direction = False
    if moving_towards_edge and will_overshoot:
        # Counter-turn to slow down
        if edge_type == -1:  # Left edge - turn right to slow down
            direction = True
            queue_turn(kb_controller, True, frames_x)
        else:  # Right edge - turn left to slow down
            queue_turn(kb_controller, False, frames_x)
    else:
        # Original case - turn towards edge to maintain/gain momentum
        if edge_type == -1:  # Left edge - turn left
            queue_turn(kb_controller, False, frames_x)
        else:  # Right edge - turn right
            direction = True
            queue_turn(kb_controller, True, frames_x)
    
    # Queue the fastfall input if we found a good frame to do it
    if fastfall_frame is not None:
        # Queue a downward input on the control stick
        current_frame = gamestate.frame
        kb_controller.queue_input('stick', {'stick': Button.BUTTON_MAIN, 'x': 1.3 if direction else -0.3, 'y': -0.3}, 
                                current_frame + fastfall_frame, current_frame + fastfall_frame + 1)
        # Reset the stick position after fastfalling
        stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.RIGHT)
        kb_controller.queue_redo(current_frame + fastfall_frame + 1, stick_input)

def can_waveland(player, framedata):
    return (
        not framedata.is_attacking(player) and
        (framedata.is_falling(player) or framedata.is_jumping(player)) and
        player.y > -2.5
    )

def handle_waveland(kb_controller, gamestate, player, framedata):
    active_key = kb_controller.hotkeys_state[24]
    ledgedash_key = kb_controller.hotkeys_state[29]
    if (player.on_ground or kb_controller.inputs_reserved >= gamestate.frame + 2 or
        not active_key or ledgedash_key or not can_waveland(player, framedata) or
        player.action == Action.PLATFORM_DROP):
        return
    
    pos_x = player.x
    pos_y = player.y
    y_margin_above = 0
    y_margin_below = 0
    fly_margin = 0
    predict_frames = 2
    waveland_x = 0
    waveland_y = 0
    waveland_delay = 0
    fastfall_frames = [0]
    fastfallspeed = framedata.characterdata[player.character]["FastFallSpeed"]
    size = float(framedata.characterdata[player.character]["size"])
    
    if player.character == Character.CPTFALCON:
        y_margin_above = 5
        y_margin_below = 4
        fly_margin = 8
        if (player.action in [Action.JUMPING_ARIAL_FORWARD, Action.JUMPING_ARIAL_BACKWARD]):
            y_margin_above = 0
            fly_margin = 5
        if player.action == Action.FALLING:
            y_margin_below = 3
        if player.speed_y_self <= 0:
            predict_frames = 3
            if player.action == Action.JUMPING_FORWARD:
                y_margin_below = 5.65
    elif player.character == Character.FALCO:
        if player.action == Action.JUMPING_BACKWARD:
            y_margin_below = 2
            waveland_y = 0.09
            fastfall_frames = [11, 25]
        elif player.action == Action.JUMPING_FORWARD:
            y_margin_below = 2
            waveland_y = 0.09
            fastfall_frames = [11, 25]
        elif player.action == Action.FALLING:
            y_margin_below = 2
            waveland_y = 0.09
        if player.speed_y_self > 0:
            fly_margin = 5
            waveland_y = 0.3225
            if player.action in [Action.JUMPING_ARIAL_FORWARD, Action.JUMPING_ARIAL_BACKWARD]:
                y_margin_above = 1
                waveland_y = 0.09
    if player.character == Character.GANONDORF:
        y_margin_below = 11
        y_margin_above = 5
        fly_margin = 5
        if player.action == Action.JUMPING_ARIAL_BACKWARD:
            y_margin_below = 4
            fastfall_frames = [17, 18]
            if player.speed_y_self > 0:
                y_margin_above = 0
                fly_margin = 1
                waveland_y = 0.09
        if player.action in [Action.JUMPING_FORWARD, Action.JUMPING_BACKWARD]:
            fastfall_frames = [15, 19]
            y_margin_below = 4
        # if (player.action in [Action.JUMPING_ARIAL_FORWARD, Action.JUMPING_ARIAL_BACKWARD]):
        #     y_margin_above = 0
        #     fly_margin = 4
        #     if player.action == Action.JUMPING_ARIAL_BACKWARD:
        #         y_margin_below = 5
        #     elif player.action == Action.JUMPING_ARIAL_FORWARD and player.speed_y_self <= 0:
        #         waveland_y = 0.5
        # if player.action == Action.FALLING:
        #     y_margin_below = 8
        # if player.speed_y_self <= 0:
        #     predict_frames = 3
        #     if player.action == Action.JUMPING_FORWARD:
        #         y_margin_below = 5.65
        #     if player.action == Action.JUMPING_BACKWARD:
        #         y_margin_below = 5
    elif player.character == Character.LINK:
        fly_margin = 5
        if player.action == Action.JUMPING_ARIAL_BACKWARD:
            y_margin_below = 5
    elif player.character == Character.LUIGI:
        fly_margin = 5
        if player.action in [Action.JUMPING_ARIAL_FORWARD, Action.JUMPING_ARIAL_BACKWARD]:
            fly_margin = 4
    elif player.character == Character.MARTH:
        y_margin_below = 1
        if player.action in [Action.JUMPING_FORWARD, Action.JUMPING_BACKWARD]:
            fly_margin = 6
            waveland_y = 0.09
            fastfall_frames = [22, 31]
        if (player.action in [Action.JUMPING_ARIAL_FORWARD, Action.JUMPING_ARIAL_BACKWARD]):
            fly_margin = 5
            fastfall_frames = [26]
    elif player.character == Character.ROY:
        y_margin_below = 1
        if player.action in [Action.JUMPING_FORWARD, Action.JUMPING_BACKWARD]:
            fly_margin = 5
            y_margin_below = 3
            waveland_y = 0.19
            fastfall_frames = [13, 22]
        if (player.action in [Action.JUMPING_ARIAL_FORWARD, Action.JUMPING_ARIAL_BACKWARD]):
            fly_margin = 4
            y_margin_below = 1
            fastfall_frames = [21]
            if player.speed_y_self > 0:
                waveland_y = 0.09
    elif player.character == Character.SAMUS:
        y_margin_below = 6
        fly_margin = 8
        if player.action in [Action.JUMPING_BACKWARD, Action.FALLING]:
            y_margin_below = 8
        if player.speed_y_self > 0:
            fly_margin = 2
    elif player.character == Character.SHEIK:
        fly_margin = 7
        y_margin_below = 1
        if player.action in [Action.JUMPING_FORWARD, Action.JUMPING_BACKWARD]:
            y_margin_above = 8
        if player.action in [Action.JUMPING_ARIAL_FORWARD, Action.JUMPING_ARIAL_BACKWARD]:
            fly_margin = 5
            y_margin_below = 5
            if player.speed_y_self <= 0:
                waveland_y = 0.09
        if player.action == Action.FALLING:
            y_margin_below = 4
            waveland_y = 0.09
            
    can_fastfall = player.speed_y_self <= 0 and player.speed_y_self > -fastfallspeed and fastfall_frames[0] == 0
    if player.action_frame in fastfall_frames:
        can_fastfall = True
    do_fastfall = False
    if (can_fastfall):
        do_fastfall = True
        player.speed_y_self = -fastfallspeed
        
    move_location = get_fly_pos(player, gamestate, framedata, predict_frames, fly_margin, True)
    speed_x = player.speed_air_x_self + player.speed_x_attack
    speed_y = player.speed_y_self + player.speed_y_attack
    
    closest_platform = framedata.get_closest_platform(gamestate, move_location)
    if closest_platform is None:
        return

    platform_x, platform_y, platform_width = closest_platform
    half_width = platform_width/2
    platform_left = platform_x - half_width
    platform_right = platform_x + half_width

    # Check if we're moving towards the platform
    moving_towards_platform = (platform_left < move_location[0] < platform_right)
    if not moving_towards_platform:
        # If not, check if we're close enough to the platform to wave land
        if abs(move_location[0] - platform_x) > half_width:
            if player.off_stage:
                return
            
            # Revert to base platform
            base_platform = framedata.get_platforms(gamestate, [pos_x, pos_y])[0]
            platform_y = base_platform[0]
            platform_left = base_platform[1]
            platform_right = base_platform[2]

    if do_fastfall:
        queue_crouch(kb_controller, use_current_frame=True)
    
    # Get direction of waveland to perform
    right_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.RIGHT)
    left_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.LEFT)
    direction = 1 if kb_controller.hotkeys_state[right_input] else -1 if kb_controller.hotkeys_state[left_input] else 0
    waveland_x = -waveland_x if direction == -1 else waveland_x

    true_speed_x = speed_x
    if speed_x > 0:
        true_speed_x += size / 2
    elif speed_x < 0:
        true_speed_x -= size / 2
    true_x = move_location[0] + true_speed_x

    # Check if we're in position to wave land
    if speed_y == 0:
        return
    if speed_x > 0 and true_x > platform_right:
        return
    if speed_x < 0 and true_x < platform_left:
        return
    if speed_y > 0 and move_location[1] > platform_y - y_margin_above and pos_y >= platform_y - y_margin_above:
        return
    if speed_y < 0 and move_location[1] > platform_y + y_margin_below:
        return
    # Don't waveland if we don't need to
    elif speed_y < 0 and direction == 0:
        return

    # Queue the wave land input
    queue_wavedash(kb_controller, player, direction, set_x=waveland_x, set_y=waveland_y, do_jump=False, delay=waveland_delay)
    kb_controller.inputs_reserved += console.online_delay * 2

def reset_game_state(kb_controller):
    kb_controller.input_queue.clear()
    kb_controller.inputs_reserved = 0

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

def main():
    initialized = False
    local_port = 0
    selected_character = Character.CPTFALCON
    selected_costume = 0
    tech_lockout = 0
    meteor_jump_lockout = 0
    ledge_grab_count = 0
    meteor_ff_lockout = 0
    powershielded_last = False
    opponent_ports = []
    opponent_port = 0
    alive = False
    interruptable = False
    no_impact_land = False
    ecb_shift = False
    acid_dropped = False
    stage_bounds_ground, stage_bounds_air, left_plat_bounds, right_plat_bounds, top_plat_bounds = None, None, None, None, None
    has_teched = False
    sdi_frames = 0
    shine_on_shield = False
     
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

    framedata = melee.framedata.FrameData()
    
    if args.standard_human:
        # Read in dolphin's controller config file
        kb_controller = KBController(args.config)
    
    # Main loop
    while True:

        # "step" to the next frame
        gamestate = console.step()
        
        # Do keyboard updates
        kb_controller.update(gamestate)
        
        if gamestate is None:
            initialized = False
            continue

        # The console object keeps track of how long your bot is taking to process frames
        #   And can warn you if it's taking too long
        if console.processingtime * 1000 > 12:
            print("WARNING: Last frame took " + str(console.processingtime*1000) + "ms to process.")

        in_game = gamestate.menu_state in [melee.Menu.IN_GAME, melee.Menu.SUDDEN_DEATH]

        # What menu are we in?
        if in_game:
            if not initialized:
                stage_bounds_ground, stage_bounds_air, left_plat_bounds, right_plat_bounds, top_plat_bounds = initialize_game_state(gamestate)
                initialized = True
                alive = True
            
            local_port, opponent_ports, opponent_port, alive = update_player_info(gamestate, local_port, opponent_ports, alive, selected_costume, selected_character)
            
            if not alive:
                continue
            
            local_player = gamestate.players[local_port]
            handle_l_cancel(kb_controller, local_player, framedata)
            if stage_bounds_ground != None:
                handle_edgecancel(
                    kb_controller,
                    gamestate,
                    local_player,
                    framedata
                )
            
            if opponent_port not in gamestate.players:
                continue
            
            opponent_player = gamestate.players[opponent_port]
            
            # Pick the right climber to be the opponent
            if opponent_player.nana is not None:
                xdist = opponent_player.nana.x - local_player.x
                ydist = opponent_player.nana.y - local_player.y
                dist = math.sqrt((xdist**2) + (ydist**2))
                if dist < gamestate.distance:
                    gamestate.distance = dist
                    popo = opponent_player
                    opponent_player = opponent_player.nana
                    opponent_player.nana = popo

            knownprojectiles = []
            bomb_held = False
            bomb_thrown = False
            bomb_airborne = False
            for projectile in gamestate.projectiles:
                # Held turnips and link bombs
                if projectile.type in [ProjectileType.TURNIP, ProjectileType.LINK_BOMB, ProjectileType.YLINK_BOMB]:
                    if projectile.subtype in [4, 5]:
                        continue
                    if projectile.owner == local_port:
                        bomb_held = projectile.subtype == 0
                        bomb_thrown = projectile.subtype == 2
                        bomb_airborne = projectile.subtype == 3
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

            # Platform drop is fully actionable. Don't be fooled
            if opponent_player.action == Action.PLATFORM_DROP:
                opponent_player.hitstun_frames_left = 0
            
            if stage_bounds_ground != None:
                has_teched, sdi_frames = handle_walltech(kb_controller, gamestate, local_player, stage_bounds_ground, framedata, has_teched, sdi_frames)
            
            # Skip non-actionable frames
            frames_left = (framedata.last_frame(local_player.character, local_player.action) - console.online_delay) - local_player.action_frame
            if not framedata.is_actionable(local_player) and frames_left > 0:
                continue
            
            if local_player.hitlag_left > 0:
                frames_left = local_player.hitlag_left - console.online_delay
            
            if local_player.character == Character.CPTFALCON:
                handle_gentleman(kb_controller, gamestate, local_player, opponent_player, framedata)
            elif local_player.character == Character.FALCO:
                shine_on_shield = handle_shine(kb_controller, gamestate, local_player, opponent_player, framedata, shine_on_shield)
            elif local_player.character == Character.LINK:
                acid_dropped = bomb_airborne
                acid_dropped = handle_aciddrop(kb_controller, gamestate, local_player, opponent_player, framedata, acid_dropped, bomb_held, bomb_thrown)
            elif local_player.character == Character.SAMUS:
                handle_samusattack(kb_controller, gamestate, local_player, framedata)
            if can_airdash(local_player):
                handle_airdash(kb_controller, gamestate, local_player, framedata)
            if can_airturn(local_player):
                handle_airturn(kb_controller, gamestate, local_player, framedata)
            
            interruptable, no_impact_land, ecb_shift = handle_ledgedash(kb_controller,gamestate,local_player,opponent_player,interruptable,no_impact_land,ecb_shift)
            
            if frames_left > 0 or kb_controller.inputs_reserved > gamestate.frame + 1:
                continue
            
            handle_counter_and_dodge(kb_controller, gamestate, local_player, opponent_player, framedata)
            handle_techchase(kb_controller, gamestate, local_player, opponent_player, framedata)
            handle_projectiles(kb_controller, gamestate, local_player, framedata, opponent_player, knownprojectiles)
            handle_shieldoption(kb_controller, gamestate, local_player, framedata, opponent_player, stage_bounds_ground)
            handle_waveland(
                kb_controller,
                gamestate,
                local_player,
                framedata
            )
            
            if log:
                log.logframe(gamestate)
                log.writeframe()
        else:
            reset_game_state(kb_controller)
            initialized = False
            local_port = 0
            tech_lockout = 0
            meteor_jump_lockout = 0
            ledge_grab_count = 0
            meteor_ff_lockout = 0
            powershielded_last = False
            opponent_ports = []
            opponent_port = 0
            alive = False
            interruptable = False
            no_impact_land = False
            ecb_shift = False
            acid_dropped = False
            stage_bounds_ground, stage_bounds_air, left_plat_bounds, right_plat_bounds, top_plat_bounds = None, None, None, None, None
            has_teched = False
            sdi_frames = 0
            shine_on_shield = False
            if gamestate.menu_state in [melee.enums.Menu.CHARACTER_SELECT, melee.enums.Menu.SLIPPI_ONLINE_CSS]:
                selected_character = gamestate.players[1].character_selected
                selected_costume = gamestate.players[1].costume
            
            # If we're not in game, don't log the frame
            if log:
                log.skipframe()
                
if __name__ == '__main__':
    main()