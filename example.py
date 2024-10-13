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
            if num == 27 or num == 29 or num == 30:
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
            if num == 29 or num == 30:
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
        first_button = buttons.pop(0)
        if len(buttons) >= 1:
            current_frame = self.gamestate.frame
            for button in buttons:
                # Check if there's a press for this button in the current frame
                press_in_current_frame = any(
                    input['type'] == 'button' and
                    input['value'] == button and
                    input['start_frame'] == current_frame
                    for input in self.input_queue
                )
                
                # If there's a press in the current frame, schedule the release for the next frame
                release_frame = current_frame + 1 if press_in_current_frame else current_frame
                
                self.queue_input('button', button, release_frame, release_frame)
        
        controller.release_button(first_button)

    def calculate_current_tilt(self, stick):
        x, y = 0.5, 0.5
        
        if stick == melee.Button.BUTTON_MAIN:
            # Check main stick directional inputs (1-4)
            if self.hotkeys_state[1]: y = max(y, 1.0375)  # Up
            if self.hotkeys_state[3]: y = min(y, -0.0475)  # Down
            if self.hotkeys_state[2]: x = min(x, -0.0375)  # Left
            if self.hotkeys_state[4]: x = max(x, 1.0425)  # Right
        elif stick == melee.Button.BUTTON_C:
            # Check C-stick directional inputs (5-8)
            if self.hotkeys_state[5]: y = max(y, 1.0375)  # C-Up
            if self.hotkeys_state[7]: y = min(y, -0.0475)  # C-Down
            if self.hotkeys_state[6]: x = min(x, -0.0375)  # C-Left
            if self.hotkeys_state[8]: x = max(x, 1.0425)  # C-Right
        
        return self.apply_tilt_mod(x, y)

    def human_tilt_analog(self, num):
        button, _ = self.get_hotkey_stick(num)
        tilt = self.get_tilt(num)
        
        if button == Button.BUTTON_C:
            tilt_x = tilt[0]
            tilt_y = tilt[1]
            if tilt_x != 0.5:
                tilt_x = 1.3 if tilt[0] > 0.5 else -0.3
            if tilt_y != 0.5:
                tilt_y = 1.3 if tilt[1] > 0.5 else -0.3
            tilt = (tilt_x, tilt_y)
        
        controller.tilt_analog(button, tilt[0], tilt[1])

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
            self.reserved_inputs.add(value)
        elif input_type == 'stick':
            self.reserved_inputs.add(value['stick'])
        elif input_type == 'shoulder':
            self.reserved_inputs.add(melee.Button.BUTTON_L)  # Assuming L shoulder for simplicity
        
    def process_and_clean_input_queue(self, current_frame):
        new_queue = []
        for input in self.input_queue:
            if current_frame >= input['end_frame'] and input['end_frame'] > 0:
                self.release_input(input)
                if input['type'] == 'button':
                    self.reserved_inputs.discard(input['value'])
                elif input['type'] == 'stick':
                    self.reserved_inputs.discard(input['value']['stick'])
                elif input['type'] == 'shoulder':
                    self.reserved_inputs.discard(melee.Button.BUTTON_L)
                continue
            if current_frame >= input['start_frame']:
                if input['type'] == 'redo':
                    self.redo_hotkey(input['value'])
                    continue
                self.apply_input(input)
                
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
            if button and button[0] in self.reserved_inputs:
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
                self.human_press_shoulder()
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

def initialize_game_state(gamestate):
    stage = gamestate.stage
    if stage == melee.Stage.NO_STAGE:
        return
    
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

def update_player_info(gamestate, local_port, opponent_ports, alive, costume):
    if local_port not in gamestate.players or len(opponent_ports) == 0 and alive:
        local_port = get_target_player(gamestate, 'SOUL#127') or melee.gamestate.port_detector(gamestate, Character.CPTFALCON, costume)
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

def queue_turn(kb_controller, new_facing, run_frames=0, set_x=0.0):
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
    
    stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.RIGHT)
    if not new_facing:
        stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.LEFT)
        
    new_x, new_y = kb_controller.get_tilt(stick_input, False)[0], 0.5
    if run_frames == 0:
        new_x += -0.25 if new_facing else 0.25
    else:
        new_x = 1.3 if new_facing else -1.3
        
    if set_x != 0.0:
        new_x = set_x
    
    kb_controller.queue_input('stick', {'stick': Button.BUTTON_MAIN, 'x': new_x, 'y': new_y}, current_frame + 1, current_frame + 2 + run_frames)
    kb_controller.queue_redo(current_frame + 2 + run_frames, stick_input)

def queue_shorthop(kb_controller, with_facing=0, use_current_frame=False, delay=0):
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
    
    if use_current_frame and current_frame != kb_controller.gamestate.frame:
        current_frame -= 1
        
    current_frame += delay
    
    if with_facing != 0:
        stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.RIGHT)
        if with_facing == -1:
            stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.LEFT)
            
        new_x, new_y = kb_controller.get_tilt(stick_input, False)[0], 0.5
    
        kb_controller.queue_input('stick', {'stick': Button.BUTTON_MAIN, 'x': new_x, 'y': new_y}, current_frame + 1, current_frame + 2)
        kb_controller.queue_redo(current_frame + 1, stick_input)
    
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
        if local_char == Character.CPTFALCON:
            current_frame += 3
        elif local_char == Character.GANONDORF:
            current_frame += 5
        elif local_char == Character.SHEIK:
            current_frame += 2
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
    
    kb_controller.queue_input('stick', {'stick': Button.BUTTON_MAIN, 'x': new_x, 'y': new_y}, current_frame + 1, current_frame + 3)
    kb_controller.queue_redo(current_frame + 3, stick_input)
    
    kb_controller.queue_input('button', Button.BUTTON_L, current_frame + 2, current_frame + 3)
    kb_controller.queue_redo(current_frame + 3, shield_button)

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

def queue_jab(kb_controller, player, jab_count=1, gentleman=False):
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
        kb_controller.queue_input(
            'button',
            Button.BUTTON_A,
            start,
            end
        )

def get_slide_pos(player, framedata, time=1):
    # Calculate location after sliding
    move_location = [player.x, player.y]
    speed_x = player.speed_x_attack + player.speed_ground_x_self
    if speed_x > 0:
        slide_dist = framedata.slide_distance(player, speed_x, time)
        move_location = [player.x + slide_dist, player.y]
        
    return move_location

def get_fly_pos(player, gamestate, framedata, time=1):
    # Calculate location during flight
    if framedata.is_hit(player) or not player.on_ground:
        target_pos_x, target_pos_y, _ = framedata.project_hit_location(gamestate, player, time)
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
    first_grab_frame = framedata.first_hitbox_frame(local_char, Action.GRAB) - console.online_delay
    last_grab_frame = framedata.last_hitbox_frame(local_char, Action.GRAB)
    time_to_chase = framedata.last_roll_frame(opp_char, chase_scenario) - current_frame
    is_attack = framedata.is_attack(opp_char, chase_scenario)
    if chase_scenario == Action.NEUTRAL_GETUP:
        time_to_chase = 30 - current_frame
    elif is_attack or is_damaged:
        time_to_chase = framedata.last_frame(opp_char, chase_scenario) - current_frame
    
    # Account for delay and input frames
    time_to_chase -= console.online_delay + 6
    
    target_pos_x = framedata.roll_end_position(gamestate, opponent)
    target_pos_y = opponent.y
    is_mistech = framedata.has_misteched(opponent)
    if is_mistech:
        opp_speed_x = opponent.speed_x_attack + opponent.speed_ground_x_self
        target_pos_x += framedata.slide_distance(opponent, opp_speed_x, opponent.action_frame)
    elif framedata.is_hit(opponent) or not opponent.on_ground:
        time_to_chase = opponent.hitstun_frames_left
        target_pos_x, target_pos_y, _ = framedata.project_hit_location(gamestate, opponent)
        # Account only for delay
        time_to_chase -= console.online_delay
    
    move_location = get_slide_pos(player, framedata, time_to_chase)
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
    # In scenarios where we would move past the target, we face the other direction
    if (new_pred_facing != new_facing and
        chase_scenario != Action.NEUTRAL_GETUP and
        chase_scenario != Action.GROUND_GETUP):
        new_facing = new_pred_facing
        
    shielding = framedata.is_shielding(player)
    if not shielding:
        if pred_dx > 25:
            queue_turn(kb_controller, new_facing, 1)
        elif pred_dx > 12 and new_facing == current_facing:
            dash_grab = 1 if current_facing else -1
        
        if new_facing != current_facing:
            queue_turn(kb_controller, new_facing)
        
    # Calculate wavedash x based on distance to tarrget position
    wavedash_x = calculate_wavedash_x(target_pos_x, move_location[0], new_facing, 15)
    
    if (pred_dx > 20 and (player.action == Action.RUN_BRAKE or
        player.action == Action.TURNING_RUN or
        shielding)):
        queue_wavedash(kb_controller, player, 1 if new_facing else -1, wavedash_x, -0.3, use_current_frame=True)
        return
    
    player_size = float(framedata.characterdata[local_char]["size"])
    can_grab = (new_facing == current_facing and
                pred_dx < 25 and
                dy < player_size and
                time_to_chase < last_grab_frame and
                time_to_chase > first_grab_frame)
    
    if is_damaged and chase_scenario == Action.GRAB_PUMMELED:
        can_grab = False
    
    dash_grab = 0
    
    if can_grab and not is_attack and not is_mistech:
        queue_jcgrab(kb_controller, player, dash_grab)
    elif is_attack:
        if pred_dx < 25 and not shielding:
            queue_shield(kb_controller, frames=framedata.last_hitbox_frame(opp_char, chase_scenario) - current_frame)
        elif new_facing == current_facing:
            queue_jcgrab(kb_controller, player)

def queue_crouch(kb_controller, frames=1, delay=0):
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
    
    current_frame += delay
    
    stick_input = kb_controller.get_analog_hotkey(Button.BUTTON_MAIN, Analog.DOWN)
    new_x, new_y = kb_controller.get_tilt(stick_input, False, True)
    kb_controller.queue_input('stick', {'stick': Button.BUTTON_MAIN, 'x': new_x, 'y': new_y}, current_frame + 1, current_frame + 1 + frames)
    kb_controller.queue_redo(current_frame + 1 + frames, stick_input)

def queue_cstick(kb_controller, analog_direction):
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
    
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
            new_y -= 0.25
        # Ensure we do not fast fall when doing down specials
        elif analog_direction == Analog.DOWN:
            new_x = 0.5
            new_y += 0.25
        kb_controller.queue_input('stick', {'stick': Button.BUTTON_MAIN, 'x': new_x, 'y': new_y}, current_frame + 1, current_frame + 3)
        kb_controller.queue_redo(current_frame + 3, stick_input)
        current_frame += 1
    
    kb_controller.queue_input('button', Button.BUTTON_B, current_frame + 1, current_frame + 2 + frames)

def queue_ledgedash(kb_controller, player, jump_direction=0, hold_in_frames=0, wavedash_direction=0, max_x=0):
    # Drop from ledge, jump inwards, wavedash inwards
    queue_crouch(kb_controller)
    queue_shorthop(kb_controller, jump_direction)
    if hold_in_frames != 0:
        queue_turn(kb_controller, player.facing, hold_in_frames, max_x)
    queue_wavedash(kb_controller, player, wavedash_direction)

def handle_ledgedash(kb_controller, gamestate, player, interruptable=False, stalled=False):
    ledgedash_key = kb_controller.hotkeys_state[29]
    if (kb_controller.inputs_reserved >= gamestate.frame or not ledgedash_key or
        (player.action != Action.EDGE_HANGING and player.action != Action.EDGE_CATCHING)):
        return interruptable, stalled
    
    finish_wavedash = kb_controller.hotkeys_state[25]
    finish_interrupt = kb_controller.hotkeys_state[24]
    
    max_x = 1.3 if player.facing else -0.3
    jump_direction = 1 if player.facing else -1
    wavedash_direction = 1 if player.facing else -1
    wavedash_x = -0.3 if player.facing else 1.3
    wavedash_y = -0.3
    
    local_char = player.character
    jump_in_frames = 6
    hold_in_frames = 2
    fall_frames = 4
    fast_fall_interrupt = False
    fast_fall_stall_start = False
    fast_fall_stall_wait = 0
    aerial_interrupt = Analog.LEFT if player.facing else Analog.RIGHT
    always_interruptable = False
    jump_regrab = True
    normal_stall = True
    if local_char == Character.CPTFALCON:
        jump_in_frames = 9
        hold_in_frames = 5
        if player.action == Action.EDGE_CATCHING and player.action_frame == 5:
            jump_in_frames = 8
            hold_in_frames = 5
        fall_frames = 5
        #if gamestate.stage == melee.Stage.DREAMLAND:
        #    jump_in_frames = 10
        #elif gamestate.stage == melee.Stage.YOSHIS_STORY:
        #    jump_in_frames = 9
    elif local_char == Character.GANONDORF:
        wavedash_x += 0.55 if player.facing else -0.55
        jump_in_frames = 11
        hold_in_frames = 1
        fall_frames = 4
        if finish_wavedash:
            hold_in_frames = 9
    elif local_char == Character.JIGGLYPUFF:
        aerial_interrupt = None
        normal_stall = False
        if finish_wavedash:
            hold_in_frames = 3
        fall_frames = 11
    elif local_char == Character.LINK:
        wavedash_x += 0.55 if player.facing else -0.55
        jump_in_frames = 6
        hold_in_frames = 0
        fast_fall_stall_wait = 9
        if finish_wavedash:
            hold_in_frames = 4
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
        hold_in_frames = 0
        fast_fall_stall_wait = 5
        fall_frames = 20
        if finish_wavedash or finish_interrupt:
            hold_in_frames = 1
            # After stalling, Luigi's ECB is shifted, so we have to modify the wavedash
            if stalled:
                hold_in_frames = 2
                wavedash_direction = 0
        fast_fall_interrupt = True
        fast_fall_stall_start = True
        aerial_interrupt = None
        always_interruptable = True
        jump_regrab = False
    elif local_char == Character.MEWTWO:
        normal_stall = False
        jump_regrab = False
    elif local_char == Character.PEACH:
        fall_frames = 14
        if finish_wavedash:
            hold_in_frames = 22
        normal_stall = False
        jump_regrab = False
    elif local_char == Character.PICHU:
        normal_stall = False
        jump_regrab = False
        if finish_wavedash:
            hold_in_frames = 0
    elif local_char == Character.ROY:
        jump_in_frames = 8
        if gamestate.stage == melee.Stage.YOSHIS_STORY:
            jump_in_frames = 9
        fast_fall_stall_wait = 2
        if finish_wavedash:
            hold_in_frames = 8
            if gamestate.stage == melee.Stage.YOSHIS_STORY:
                hold_in_frames = 9
        elif finish_interrupt:
            fall_frames = 2
            if gamestate.stage == melee.Stage.YOSHIS_STORY:
                hold_in_frames = 8
            else:
                hold_in_frames = 12
        fast_fall_interrupt = True
        aerial_interrupt = Analog.NEUTRAL
        always_interruptable = True
    elif local_char == Character.SHEIK:
        wavedash_x += 0.55 if player.facing else -0.55
        jump_in_frames = 8
        hold_in_frames = 3
        fall_frames = 5
        if finish_wavedash:
            hold_in_frames = 2
        fast_fall_stall_start = True
        jump_regrab = False
    
    if finish_wavedash:
        queue_ledgedash(kb_controller, player, jump_direction, hold_in_frames, wavedash_direction, max_x)
        return False, False
    
    if finish_interrupt and aerial_interrupt and (interruptable or always_interruptable):
        # Drop from ledge, jump inwards, do aerial interrupt input
        queue_crouch(kb_controller, fall_frames if fast_fall_interrupt else 1)
        queue_shorthop(kb_controller, jump_direction, True if fast_fall_interrupt else False)
        queue_turn(kb_controller, player.facing, hold_in_frames, max_x)
        queue_cstick(kb_controller, aerial_interrupt)
        return False, False
    elif finish_interrupt and not aerial_interrupt:
        queue_ledgedash(kb_controller, player, jump_direction, hold_in_frames, wavedash_direction, max_x)
        return False, False
    
    wait_type = random.randint(0, 1)
    if wait_type == 0 and not finish_interrupt and normal_stall:
        # Drop from ledge, jump inwards, wavedash back to ledge
        queue_crouch(kb_controller, 2 if fast_fall_stall_start else 1)
        queue_shorthop(kb_controller, jump_direction)
        queue_turn(kb_controller, player.facing, jump_in_frames, max_x)
        queue_wavedash(kb_controller, player, -1 if player.facing else 1, set_x=wavedash_x, set_y=wavedash_y)
        if hold_in_frames != 0:
            queue_turn(kb_controller, player.facing, hold_in_frames, max_x)
        queue_crouch(kb_controller, delay=fast_fall_stall_wait)
        return False, True
    elif wait_type == 0 and not normal_stall:
        if local_char == Character.PICHU:
            # Drop from ledge and up b inwards
            queue_crouch(kb_controller)
            queue_special(kb_controller, Analog.UP)
            queue_turn(kb_controller, player.facing, 9)
        return False, False
    elif wait_type == 1 and jump_regrab:
        # Drop from ledge with fast fall and jump
        queue_crouch(kb_controller, fall_frames)
        queue_shorthop(kb_controller)
        return True, False
    else:
        if local_char == Character.LUIGI:
            # Drop from ledge with fast fall and up b
            queue_crouch(kb_controller, fall_frames)
            queue_special(kb_controller, Analog.UP)
        elif local_char == Character.MEWTWO:
            # Drop from ledge via turn an up b inwards
            queue_turn(kb_controller, not player.facing, 6)
            queue_special(kb_controller, Analog.UP, use_current_frame=True)
            queue_turn(kb_controller, player.facing, 9)
        elif local_char == Character.PEACH:
            # Drop from ledge and up b
            queue_crouch(kb_controller, fall_frames)
            queue_special(kb_controller, Analog.UP)
        elif local_char == Character.PICHU:
            # Drop from ledge and up b inwards
            queue_crouch(kb_controller)
            queue_special(kb_controller, Analog.UP)
            queue_turn(kb_controller, player.facing, 9)
        elif local_char == Character.SHEIK:
            # Drop from ledge and up b
            queue_crouch(kb_controller, fall_frames)
            queue_special(kb_controller, Analog.UP)
            
        return False, False

def handle_gentleman(kb_controller, gamestate, player, opponent, framedata):
    active_key = kb_controller.hotkeys_state[30]
    if (kb_controller.inputs_reserved >= gamestate.frame or not active_key or
        not player.on_ground or framedata.is_attacking(player)):
        return
    
    move_location = get_slide_pos(player, framedata, 3)
    target_pos = get_fly_pos(opponent, gamestate, framedata, 3)
    pred_dx = abs(move_location[0] - target_pos[0])
    
    gentleman = False
    if pred_dx < 20:
        gentleman = True
    
    queue_jab(kb_controller, player, 3, gentleman)

def queue_zdrop(kb_controller, player, framedata, with_facing=0):
    if player.on_ground:
        queue_shorthop(kb_controller, with_facing, True)
    
    current_frame = kb_controller.gamestate.frame if kb_controller.inputs_reserved == 0 else kb_controller.inputs_reserved
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

def handle_aciddrop(kb_controller, gamestate, player, opponent, framedata, has_dropped=False):
    active_key = kb_controller.hotkeys_state[30]
    if (kb_controller.inputs_reserved >= gamestate.frame or not active_key or
        framedata.is_attacking(player)):
        return has_dropped
    
    # Check if airborne
    if (not player.on_ground and
        not player.action == Action.AIRDODGE and
        player.y > 4):
        return has_dropped
    
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
        queue_jab(kb_controller, player)
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
    
    if new_pred_facing != player.facing:
        queue_turn(kb_controller, new_pred_facing, 1)
    
    new_pred_facing = target_pos[0] >= bomb_drop_x
    
    # Calculate wavedash x based on distance to bomb drop position
    wavedash_x = calculate_wavedash_x(bomb_drop_x, target_pos[0], new_pred_facing)
    
    queue_zdrop(kb_controller, player, framedata)
    queue_wavedash(kb_controller, player, new_pred_facing if pred_dx > 10 else 0, wavedash_x, -0.3, False, True)
    return True

def handle_airdash(kb_controller, gamestate, player, framedata):
    active_key = kb_controller.hotkeys_state[30]
    if (kb_controller.inputs_reserved >= gamestate.frame or not active_key or
        not player.on_ground or framedata.is_attacking(player)):
        return
    
    if player.action != Action.LANDING_SPECIAL:
        queue_shorthop(kb_controller, 0, True)
        
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

def handle_shieldoption(kb_controller, gamestate, player, framedata, opponent):
    if (not player.on_ground or kb_controller.inputs_reserved >= gamestate.frame or
        player.hitstun_frames_left <= 0 or not framedata.is_shielding(player)):
        return
    if not kb_controller.hotkeys_state[25]:
        if player.action != Action.SHIELD_STUN and player.action != Action.SHIELD_REFLECT:
            return
            
        shield_buttons = kb_controller.get_button_hotkey(Button.BUTTON_L)
        for button in shield_buttons:
            if kb_controller.hotkeys_state[button]:
                return
    
    time_left = max(player.hitlag_left, console.online_delay)
        
    if player.action == Action.SHIELD_REFLECT:
        time_left += 2
            
    target_pos = get_fly_pos(opponent, gamestate, framedata, 3)
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
    queue_wavedash(kb_controller, player, direction, delay=time_left)

def handle_walltech(kb_controller, gamestate, player, framedata, opponent):
    if player.on_ground or kb_controller.inputs_reserved >= gamestate.frame:
        return

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

def main():
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
    stalled = False
    acid_dropped = False
    
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
                initialize_game_state(gamestate)
                initialized = True
                alive = True
            
            local_port, opponent_ports, opponent_port, alive = update_player_info(gamestate, local_port, opponent_ports, alive, costume)
            
            if not alive:
                continue
            
            local_player = gamestate.players[local_port]
            handle_l_cancel(kb_controller, local_player, framedata)
            
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
            bomb_found = False
            for projectile in gamestate.projectiles:
                # Held turnips and link bombs
                if projectile.type in [ProjectileType.TURNIP, ProjectileType.LINK_BOMB, ProjectileType.YLINK_BOMB]:
                    if projectile.subtype in [0, 4, 5]:
                        continue
                    elif projectile.subtype == 3 and projectile.owner == local_port:
                        bomb_found = True
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
            
            # Skip non-actionable frames
            frames_left = (framedata.last_frame(local_player.character, local_player.action) - console.online_delay) - local_player.action_frame
            if not framedata.is_actionable(local_player) and frames_left > 0:
                continue
            
            if local_player.hitlag_left > 0:
                frames_left = local_player.hitlag_left - console.online_delay
            
            if local_player.character == Character.CPTFALCON:
                handle_gentleman(kb_controller, gamestate, local_player, opponent_player, framedata)
            elif local_player.character == Character.LINK:
                acid_dropped = bomb_found
                acid_dropped = handle_aciddrop(kb_controller, gamestate, local_player, opponent_player, framedata, acid_dropped)
            if can_airdash(local_player):
                handle_airdash(kb_controller, gamestate, local_player, framedata)
            if can_airturn(local_player):
                handle_airturn(kb_controller, gamestate, local_player, framedata)
            
            if frames_left > 0 or kb_controller.inputs_reserved > 0:
                continue
            
            handle_counter_and_dodge(kb_controller, gamestate, local_player, opponent_player, framedata)
            handle_techchase(kb_controller, gamestate, local_player, opponent_player, framedata)
            interruptable, stalled = handle_ledgedash(kb_controller, gamestate, local_player, interruptable, stalled)
            handle_projectiles(kb_controller, gamestate, local_player, framedata, opponent_player, knownprojectiles)
            handle_shieldoption(kb_controller, gamestate, local_player, framedata, opponent_player)
            
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
            stalled = False
            acid_dropped = False
            
            # If we're not in game, don't log the frame
            if log:
                log.skipframe()
                
if __name__ == '__main__':
    main()