"""Helper functions to be able to query Melee frame data in a way useful to bots

None of the functions and structures here are strictly necessary for making a bot.
But they contain a vast and detailed amount of Melee-specific physics calculations
and state information that would be difficult to discover on your own.
"""

import csv
import os
import math
from collections import defaultdict
from melee import enums
from melee.enums import Action, Character, AttackState, DodgeState
from melee import stages

class FrameData:
    """Set of helper functions and data structures for knowing Melee frame data

    Note:
        The frame data in libmelee is written to be useful to bots, and behave in a sane way,
        not necessarily be binary-compatible with in-game structures or values.
    """
    def __init__(self, write=False):
        if write:
            self.csvfile = open('framedata.csv', 'a')
            fieldnames = ['character', 'action', 'frame',
                          'hitbox_1_status', 'hitbox_1_size', 'hitbox_1_x', 'hitbox_1_y',
                          'hitbox_2_status', 'hitbox_2_size', 'hitbox_2_x', 'hitbox_2_y',
                          'hitbox_3_status', 'hitbox_3_size', 'hitbox_3_x', 'hitbox_3_y',
                          'hitbox_4_status', 'hitbox_4_size', 'hitbox_4_x', 'hitbox_4_y',
                          'locomotion_x', 'locomotion_y', 'iasa', 'facing_changed', 'projectile',
                          'intangible']
            self.writer = csv.DictWriter(self.csvfile, fieldnames=fieldnames)
            self.writer.writeheader()
            self.rows = []

            self.actionfile = open("actiondata.csv", "a")
            fieldnames = ["character", "action", "zeroindex"]
            self.actionwriter = csv.DictWriter(self.actionfile, fieldnames=fieldnames)
            self.actionwriter.writeheader()
            self.actionrows = []

            self.prevfacing = {}
            self.prevprojectilecount = {}

        #Read the existing framedata
        path = os.path.dirname(os.path.realpath(__file__))
        self.framedata = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
        with open(path + "/framedata.csv") as csvfile:
            # A list of dicts containing the frame data
            csvreader = list(csv.DictReader(csvfile))
            # Build a series of nested dicts for faster read access
            for frame in csvreader:
                # Pull out the character, action, and frame
                character = Character(int(frame["character"]))
                action = Action(int(frame["action"]))
                action_frame = int(frame["frame"])
                self.framedata[character][action][action_frame] = \
                    {"hitbox_1_status": frame["hitbox_1_status"] == "True", \
                    "hitbox_1_size": float(frame["hitbox_1_size"]), \
                    "hitbox_1_x": float(frame["hitbox_1_x"]), \
                    "hitbox_1_y": float(frame["hitbox_1_y"]), \
                    "hitbox_2_status": frame["hitbox_2_status"] == "True", \
                    "hitbox_2_size": float(frame["hitbox_2_size"]), \
                    "hitbox_2_x": float(frame["hitbox_2_x"]), \
                    "hitbox_2_y": float(frame["hitbox_2_y"]), \
                    "hitbox_3_status": frame["hitbox_3_status"] == "True", \
                    "hitbox_3_size": float(frame["hitbox_3_size"]), \
                    "hitbox_3_x": float(frame["hitbox_3_x"]), \
                    "hitbox_3_y": float(frame["hitbox_3_y"]), \
                    "hitbox_4_status": frame["hitbox_4_status"] == "True", \
                    "hitbox_4_size": float(frame["hitbox_4_size"]), \
                    "hitbox_4_x": float(frame["hitbox_4_x"]), \
                    "hitbox_4_y": float(frame["hitbox_4_y"]), \
                    "locomotion_x": float(frame["locomotion_x"]), \
                    "locomotion_y": float(frame["locomotion_y"]), \
                    "iasa": frame["iasa"] == "True", \
                    "facing_changed": frame["facing_changed"] == "True", \
                    "projectile": frame["projectile"] == "True", \
                    "intangible": frame["intangible"] == "True"}

        #read the character data csv
        self.characterdata = dict()
        path = os.path.dirname(os.path.realpath(__file__))
        with open(path + "/characterdata.csv") as csvfile:
            reader = csv.DictReader(csvfile)
            for line in reader:
                del line["Character"]
                #Convert all fields to numbers
                for key, value in line.items():
                    line[key] = float(value)
                self.characterdata[Character(line["CharacterIndex"])] = line

    def is_grab(self, character, action):
        """For the given character, is the supplied action a grab?

        Args:
            character (enums.Character): The character we're interested in
            action (enums.Action): The action we're interested in

        This includes command grabs, such as Bowser's claw. Not just Z-grabs."""
        if action in [Action.GRAB, Action.GRAB_RUNNING]:
            return True

        # Yea, I know. The sword dance isn't the right name
        if character in [Character.CPTFALCON, Character.GANONDORF] and \
                action in [Action.SWORD_DANCE_3_MID, Action.SWORD_DANCE_3_LOW]:
            return True

        if character == Character.BOWSER and \
                action in [Action.NEUTRAL_B_ATTACKING_AIR, Action.SWORD_DANCE_3_MID]:
            return True

        if character == Character.YOSHI and \
                action in [Action.NEUTRAL_B_CHARGING_AIR, Action.SWORD_DANCE_2_MID]:
            return True

        if character == Character.MEWTWO and \
                action in [Action.SWORD_DANCE_2_MID, Action.SWORD_DANCE_3_HIGH]:
            return True

        return False

    def is_roll(self, character, action):
        """For a given character, is the supplied action a roll?

        libmelee has a liberal definition of 'roll'. A roll is essentially a move that:
         1) Has no hitbox
         2) Is inactionable

        Spot dodge and (most) taunts for example are considered 'rolls' to this function

        Args:
            character (enums.Character): The character we're interested in
            action (enums.Action): The action we're interested in
        """
        # Marth counter
        if character == Character.MARTH and action == Action.MARTH_COUNTER:
            return True
        if character == Character.MARTH and action == Action.MARTH_COUNTER_FALLING:
            return True

        # Turns out that the actions we'd call a "roll" are fairly few. Let's just
        # hardcode them since it's just more cumbersome to do otherwise
        rolls = [Action.SPOTDODGE, Action.ROLL_FORWARD, Action.ROLL_BACKWARD, \
            Action.NEUTRAL_TECH, Action.FORWARD_TECH, Action.BACKWARD_TECH, \
            Action.NEUTRAL_GETUP, Action.GROUND_GETUP, Action.TECH_MISS_UP, Action.TECH_MISS_DOWN, \
            Action.LYING_GROUND_UP, Action.LYING_GROUND_DOWN, Action.GETUP_ATTACK, Action.GROUND_ATTACK_UP, \
            Action.EDGE_GETUP_SLOW, Action.EDGE_GETUP_QUICK, Action.EDGE_ROLL_SLOW, \
            Action.EDGE_ROLL_QUICK, Action.GROUND_ROLL_FORWARD_UP, Action.GROUND_ROLL_BACKWARD_UP, \
            Action.GROUND_ROLL_FORWARD_DOWN, Action.GROUND_ROLL_BACKWARD_DOWN, Action.SHIELD_BREAK_FLY, \
            Action.SHIELD_BREAK_FALL, Action.SHIELD_BREAK_DOWN_U, Action.SHIELD_BREAK_DOWN_D, \
            Action.SHIELD_BREAK_STAND_U, Action.SHIELD_BREAK_STAND_D, Action.TAUNT_RIGHT, Action.TAUNT_LEFT, Action.SHIELD_BREAK_TEETER]
        return action in rolls

    def is_bmove(self, character, action):
        """For a given character, is the supplied action a 'B-Move'

        B-Moves tend to be weird, so it's useful to know if this is a thing that warrants a special case

        Args:
            character (enums.Character): The character we're interested in
            action (enums.Action): The action we're interested in
        """
        # If we're missing it, don't call it a B move
        if action == Action.UNKNOWN_ANIMATION:
            return False

        # Don't consider peach float to be a B move
        #   But the rest of her float aerials ARE
        if character == Character.PEACH and action in [Action.LASER_GUN_PULL, \
                Action.NEUTRAL_B_CHARGING, Action.NEUTRAL_B_ATTACKING]:
            return False
        # Peach smashes also shouldn't be B moves
        if character == Character.PEACH and action in [Action.SWORD_DANCE_2_MID, Action.SWORD_DANCE_1, \
                Action.SWORD_DANCE_2_HIGH]:
            return False

        if Action.LASER_GUN_PULL.value <= action.value:
            return True

        return False

    #Returns boolean on if the given action is an attack (contains a hitbox)
    def is_attack(self, character, action):
        """For a given character, is the supplied action an attack?

        It is an attack if it has a hitbox at any point in the action. Not necessarily right now.

        Args:
            character (enums.Character): The character we're interested in
            action (enums.Action): The action we're interested in
        """
        # For each frame...
        for _, frame in self.framedata[character][action].items():
            if frame:
                if frame['hitbox_1_status'] or frame['hitbox_2_status'] or frame['hitbox_3_status'] or \
                        frame['hitbox_4_status'] or frame['projectile']:
                    return True
        return False

    def is_shield(self, action):
        """Is the given action a Shielding action?

        Args:
            action (enums.Action): The action we're interested in
        """
        return action in [Action.SHIELD, Action.SHIELD_START, Action.SHIELD_REFLECT, Action.SHIELD_STUN, Action.SHIELD_RELEASE]

    def max_jumps(self, character):
        """ Returns the number of double-jumps the given character has.

        Args:
            character (enums.Character): The character we're interested in

        Note:
            This means in general, not according to the current gamestate
        """
        if character == Character.JIGGLYPUFF:
            return 5
        if character == Character.KIRBY:
            return 5
        return 1

    # Returns an attackstate enum
    #    WINDUP
    #    ATTACKING
    #    COOLDOWN
    #    NOT_ATTACKING
    def attack_state(self, character, action, action_frame):
        """For the given player, returns their current attack state as an AttackState enum

        Args:
            character (enums.Character): The character we're interested in
            action (enums.Action): The action we're interested in
            action_frame (int): The frame of the action we're interested in
        """
        if not self.is_attack(character, action):
            return AttackState.NOT_ATTACKING

        if action_frame < self.first_hitbox_frame(character, action):
            return AttackState.WINDUP

        if action_frame > self.last_hitbox_frame(character, action):
            return AttackState.COOLDOWN

        return AttackState.ATTACKING
    
    # Returns a dodgestate enum
    #    WINDUP
    #    INTANGIBLE
    #    COOLDOWN
    #    NOT_DODGING
    def dodge_state(self, character, action, action_frame):
        """For the given player, returns their current attack state as an AttackState enum

        Args:
            character (enums.Character): The character we're interested in
            action (enums.Action): The action we're interested in
            action_frame (int): The frame of the action we're interested in
        """
        if self.intangible_window(character, action) == (0, 0):
            return DodgeState.NOT_DODGING

        if action_frame < self.first_intangible_frame(character, action):
            return DodgeState.WINDUP

        if action_frame > self.first_intangible_frame(character, action):
            return DodgeState.COOLDOWN

        return DodgeState.DODGING

    def range_forward(self, character, action, action_frame):
        """Returns the maximum remaining range of the given attack, in the forward direction
            (relative to how the character starts facing)

        Range "remaining" means that it won't consider hitboxes that we've already passed.

        Args:
            character (enums.Character): The character we're interested in
            action (enums.Action): The action we're interested in
            action_frame (int): The frame of the action we're interested in
        """
        attackrange = 0
        lastframe = self.last_hitbox_frame(character, action)
        for i in range(action_frame+1, lastframe+1):
            attackingframe = self._getframe(character, action, i)
            if attackingframe is None:
                continue

            if attackingframe['hitbox_1_status']:
                attackrange = max(attackingframe["hitbox_1_size"] + attackingframe["hitbox_1_x"], attackrange)
            if attackingframe['hitbox_2_status']:
                attackrange = max(attackingframe["hitbox_2_size"] + attackingframe["hitbox_2_x"], attackrange)
            if attackingframe['hitbox_3_status']:
                attackrange = max(attackingframe["hitbox_3_size"] + attackingframe["hitbox_3_x"], attackrange)
            if attackingframe['hitbox_4_status']:
                attackrange = max(attackingframe["hitbox_4_size"] + attackingframe["hitbox_4_x"], attackrange)
        return attackrange

    def range_backward(self, character, action, action_frame):
        """Returns the maximum remaining range of the given attack, in the backwards direction
        (relative to how the character starts facing)

        Range "remaining" means that it won't consider hitboxes that we've already passed.

        Args:
            character (enums.Character): The character we're interested in
            action (enums.Action): The action we're interested in
            action_frame (int): The frame of the action we're interested in
        """
        attackrange = 0
        lastframe = self.last_hitbox_frame(character, action)
        for i in range(action_frame+1, lastframe+1):
            attackingframe = self._getframe(character, action, i)
            if attackingframe is None:
                continue

            if attackingframe['hitbox_1_status']:
                attackrange = min(-attackingframe["hitbox_1_size"] + attackingframe["hitbox_1_x"], attackrange)
            if attackingframe['hitbox_2_status']:
                attackrange = min(-attackingframe["hitbox_2_size"] + attackingframe["hitbox_2_x"], attackrange)
            if attackingframe['hitbox_3_status']:
                attackrange = min(-attackingframe["hitbox_3_size"] + attackingframe["hitbox_3_x"], attackrange)
            if attackingframe['hitbox_4_status']:
                attackrange = min(-attackingframe["hitbox_4_size"] + attackingframe["hitbox_4_x"], attackrange)
        return abs(attackrange)


    def in_range(self, attacker, defender, stage):
        """Calculates if an attack is in range of a given defender

        Args:
            attacker (gamestate.PlayerState): The attacking player
            defender (gamestate.PlayerState): The defending player
            stage (enums.Stage): The stage being played on

        Returns:
            integer with the frame that the specified attack will hit the defender
            0 if it won't hit

        Note:
            This considers the defending character to have a single hurtbox, centered
            at the x,y coordinates of the player (adjusted up a little to be centered)
        """
        lastframe = self.last_hitbox_frame(attacker.character, attacker.action)

        # Adjust the defender's hurtbox up a little, to be more centered.
        #   the game keeps y coordinates based on the bottom of a character, not
        #   their center. So we need to move up by one radius of the character's size
        defender_size = float(self.characterdata[defender.character]["size"])
        defender_y = defender.y + defender_size

        # Running totals of how far the attacker will travel each frame
        attacker_x = attacker.position.x
        attacker_y = attacker.position.y

        onground = attacker.on_ground

        attacker_speed_x = 0
        if onground:
            attacker_speed_x = attacker.speed_ground_x_self
        else:
            attacker_speed_x = attacker.speed_air_x_self
        attacker_speed_y = attacker.speed_y_self

        friction = self.characterdata[attacker.character]["Friction"]
        gravity = self.characterdata[attacker.character]["Gravity"]
        termvelocity = self.characterdata[attacker.character]["TerminalVelocity"]

        for i in range(attacker.action_frame+1, lastframe+1):
            attackingframe = self._getframe(attacker.character, attacker.action, i)
            if attackingframe is None:
                continue

            # Figure out how much the attaker will be moving this frame
            #   Is there any locomotion in the animation? If so, use that
            locomotion_x = float(attackingframe["locomotion_x"])
            locomotion_y = float(attackingframe["locomotion_y"])
            if locomotion_y == 0 and locomotion_x == 0:
                # There's no locomotion, so let's figure out how the attacker will be moving...
                #   Are they on the ground or in the air?
                if onground:
                    attacker_speed_y = 0
                    # Slow down the speed by the character's friction, then apply it
                    if attacker_speed_x > 0:
                        attacker_speed_x = max(0, attacker_speed_x - friction)
                    else:
                        attacker_speed_x = min(0, attacker_speed_x + friction)
                    attacker_x += attacker_speed_x
                # If attacker is in tha air...
                else:
                    # First consider vertical movement. They will decelerate towards the stage
                    attacker_speed_y = max(-termvelocity, attacker_speed_y - gravity)
                    # NOTE Assume that the attacker will keep moving how they currently are
                    # If they do move halfway, then this will re-calculate later runs

                    attacker_y += attacker_speed_y
                    # Did we hit the ground this frame? If so, let's make some changes
                    if attacker_y <= 0 and abs(attacker_x) < stages.EDGE_GROUND_POSITION[stage]:
                        # TODO: Let's consider A moves that cancel when landing
                        attacker_y = 0
                        attacker_speed_y = 0
                        onground = True

                    attacker_x += attacker_speed_x
            else:
                attacker_x += locomotion_x
                attacker_y += locomotion_y

            if attackingframe['hitbox_1_status'] or attackingframe['hitbox_2_status'] or \
                    attackingframe['hitbox_3_status'] or attackingframe['hitbox_4_status']:
                # Calculate the x and y positions of all 4 hitboxes for this frame
                hitbox_1_x = float(attackingframe["hitbox_1_x"])
                hitbox_1_y = float(attackingframe["hitbox_1_y"]) + attacker_y
                hitbox_2_x = float(attackingframe["hitbox_2_x"])
                hitbox_2_y = float(attackingframe["hitbox_2_y"]) + attacker_y
                hitbox_3_x = float(attackingframe["hitbox_3_x"])
                hitbox_3_y = float(attackingframe["hitbox_3_y"]) + attacker_y
                hitbox_4_x = float(attackingframe["hitbox_4_x"])
                hitbox_4_y = float(attackingframe["hitbox_4_y"]) + attacker_y

                # Flip the horizontal hitboxes around if we're facing left
                if not attacker.facing:
                    hitbox_1_x *= -1
                    hitbox_2_x *= -1
                    hitbox_3_x *= -1
                    hitbox_4_x *= -1

                hitbox_1_x += attacker_x
                hitbox_2_x += attacker_x
                hitbox_3_x += attacker_x
                hitbox_4_x += attacker_x

                # Now see if any of the hitboxes are in range
                distance1 = math.sqrt((hitbox_1_x - defender.position.x)**2 + (hitbox_1_y - defender_y)**2)
                distance2 = math.sqrt((hitbox_2_x - defender.position.x)**2 + (hitbox_2_y - defender_y)**2)
                distance3 = math.sqrt((hitbox_3_x - defender.position.x)**2 + (hitbox_3_y - defender_y)**2)
                distance4 = math.sqrt((hitbox_4_x - defender.position.x)**2 + (hitbox_4_y - defender_y)**2)

                if distance1 < defender_size + float(attackingframe["hitbox_1_size"]):
                    return i
                if distance2 < defender_size + float(attackingframe["hitbox_2_size"]):
                    return i
                if distance3 < defender_size + float(attackingframe["hitbox_3_size"]):
                    return i
                if distance4 < defender_size + float(attackingframe["hitbox_4_size"]):
                    return i
        return 0

    def dj_height(self, character_state):
        """Returns the height the character's double jump will take them.
        If character is in jump already, returns how heigh that one goes

        Args:
            character_state (gamestate.PlayerState): The player we're calculating for
        """
        # Peach's DJ doesn't follow normal physics rules. Hardcoded it
        if character_state.character == Character.PEACH:
            # She can't get height if not in the jump action
            if character_state.action != Action.JUMPING_ARIAL_FORWARD:
                if character_state.jumps_left == 0:
                    return 0
                return 33.218964577
            # This isn't exact. But it's close
            return 33.218964577 * (1 - (character_state.action_frame / 60))

        gravity = self.characterdata[character_state.character]["Gravity"]
        initdjspeed = self.characterdata[character_state.character]["InitDJSpeed"]
        if character_state.jumps_left == 0:
            initdjspeed = character_state.speed_y_self - gravity

        if character_state.character == Character.JIGGLYPUFF:
            if character_state.jumps_left >= 5:
                initdjspeed = 1.586
            if character_state.jumps_left == 4:
                initdjspeed = 1.526
            if character_state.jumps_left == 3:
                initdjspeed = 1.406
            if character_state.jumps_left == 2:
                initdjspeed = 1.296
            if character_state.jumps_left <= 1:
                initdjspeed = 1.186

        distance = 0

        while initdjspeed > 0:
            distance += initdjspeed
            initdjspeed -= gravity
        return distance

    def frames_until_dj_apex(self, character_state):
        """Return the number of frames it takes for the character to reach the apex of
        their double jump. If they haven't used it yet, then calculate it as if they
        jumped right now.

        Args:
            character_state (gamestate.PlayerState): The player we're calculating for
        """
        # Peach's DJ doesn't follow normal physics rules. Hardcoded it
        # She can float-cancel, so she can be falling at any time during the jump
        if character_state.character == Character.PEACH:
            return 1

        gravity = self.characterdata[character_state.character]["Gravity"]
        initdjspeed = self.characterdata[character_state.character]["InitDJSpeed"]
        if character_state.jumps_left == 0:
            initdjspeed = character_state.speed_y_self - gravity

        if character_state.character == Character.JIGGLYPUFF:
            if character_state.jumps_left >= 5:
                initdjspeed = 1.586
            if character_state.jumps_left == 4:
                initdjspeed = 1.526
            if character_state.jumps_left == 3:
                initdjspeed = 1.406
            if character_state.jumps_left == 2:
                initdjspeed = 1.296
            if character_state.jumps_left <= 1:
                initdjspeed = 1.186

        frames = 0
        while initdjspeed > 0:
            frames += 1
            initdjspeed -= gravity
        return frames

    def _getframe(self, character, action, action_frame):
        """Returns a raw frame dict for the specified frame """
        if self.framedata[character][action][action_frame]:
            return self.framedata[character][action][action_frame]
        return None

    def last_frame(self, character, action):
        """Returns the last frame of the specified action
         -1 if the action doesn't exist

        Args:
            character (enums.Character): The character we're calculating for
            action (enums.Action): The action we're calculating for
        """
        if not self.framedata[character][action]:
            return -1
        return max(self.framedata[character][action].keys())

    def last_roll_frame(self, character, action):
        """Returns the last frame of the roll
         -1 if not a roll

        Args:
            character_state (gamestate.PlayerState): The player we're calculating for
            action (enums.Action): The action the character is in
         """
        if not self.is_roll(character, action):
            return -1
        return self.last_frame(character, action)

    def roll_end_position(self, gamestate, player):
        """Returns the x coordinate that the current roll will end in

        Args:
            gamestate (GameState): The current game state to use
            player (gamestate.PlayerState): The player we're calculating for
        """
        distance = 0
        try:
            #TODO: Take current momentum into account
            # Loop through each frame in the attack
            for action_frame in self.framedata[player.character][player.action]:
                # Only care about frames that haven't happened yet
                if action_frame > player.action_frame:
                    distance += self.framedata[player.character][player.action][action_frame]["locomotion_x"]

            # We can derive the direction we're supposed to be moving by xor'ing a few things together...
            #   1) Current facing
            #   2) Facing changed in the frame data
            #   3) Is backwards roll
            facingchanged = self.framedata[player.character][player.action][player.action_frame]["facing_changed"]
            backroll = player.action in [Action.ROLL_BACKWARD, Action.GROUND_ROLL_BACKWARD_UP, \
                Action.GROUND_ROLL_BACKWARD_DOWN, Action.BACKWARD_TECH]
            if not (player.facing ^ facingchanged ^ backroll):
                distance = -distance

            position = player.position.x + distance
            stage = gamestate.stage
            if player.action not in [Action.TECH_MISS_UP, Action.TECH_MISS_DOWN, Action.LYING_GROUND_UP, Action.LYING_GROUND_DOWN]:
                # Adjust the position to account for the fact that we can't roll off the platform
                side_platform_height, side_platform_left, side_platform_right = stages.side_platform_position(player.position.x > 0, gamestate)
                top_platform_height, top_platform_left, top_platform_right = stages.top_platform_position(gamestate)
                if player.position.y < 5:
                    position = min(position, stages.EDGE_GROUND_POSITION[stage])
                    position = max(position, -stages.EDGE_GROUND_POSITION[stage])
                elif (side_platform_height is not None) and abs(player.position.y - side_platform_height) < 5:
                    position = min(position, side_platform_right)
                    position = max(position, side_platform_left)
                elif (top_platform_height is not None) and abs(player.position.y - top_platform_height) < 5:
                    position = min(position, top_platform_right)
                    position = max(position, top_platform_left)
            return position
        # If we get a key error, just assume this animation doesn't go anywhere
        except KeyError:
            return player.position.x

    def first_hitbox_frame(self, character, action):
        """Returns the first frame that a hitbox appears for a given action
           returns -1 if no hitboxes (not an attack action)

        Args:
            character (enums.Character): The character we're interested in
            action (enums.Action): The action we're interested in
        """
        # Grab only the subset that have a hitbox
        hitboxes = []
        for action_frame, frame in self.framedata[character][action].items():
            if frame:
                #Does this frame have a hitbox?
                if frame['hitbox_1_status'] or frame['hitbox_2_status'] \
                    or frame['hitbox_3_status'] or frame['hitbox_4_status'] or \
                        frame['projectile']:
                    hitboxes.append(action_frame)
        if not hitboxes:
            return -1
        return min(hitboxes)

    def hitbox_count(self, character, action):
        """Returns the number of hitboxes an attack has

        Args:
            character (enums.Character): The character we're interested in
            action (enums.Action): The action we're interested in

        Note:
           By this we mean is it a multihit attack? (Peach's down B?)
           or a single-hit attack? (Marth's fsmash?)
        """
        # Grab only the subset that have a hitbox

        # This math doesn't work for Samus's UP_B
        #   Because the hitboxes are contiguous
        if character == Character.SAMUS and action in [Action.SWORD_DANCE_3_MID, Action.SWORD_DANCE_3_LOW]:
            return 7
        if character == Character.YLINK and action == Action.SWORD_DANCE_4_MID:
            return 10

        hitboxes = []
        for action_frame, frame in self.framedata[character][action].items():
            if frame:
                #Does this frame have a hitbox?
                if frame['hitbox_1_status'] or frame['hitbox_2_status'] \
                    or frame['hitbox_3_status'] or frame['hitbox_4_status'] or \
                        frame['projectile']:
                    hitboxes.append(action_frame)
        if not hitboxes:
            return 0
        hashitbox = False
        count = 0
        # Every time we go from NOT having a hit box to having one, up the count
        for i in range(1, max(hitboxes)+1):
            hashitbox_new = i in hitboxes
            if hashitbox_new and not hashitbox:
                count += 1
            hashitbox = hashitbox_new
        return count

    def iasa(self, character, action):
        """Returns the first frame of an attack that the character is interruptible (actionable)

        returns -1 if not an attack

        Args:
            character (enums.Character): The character we're interested in
            action (enums.Action): The action we're interested in
        """
        if not self.is_attack(character, action):
            return -1
        iasaframes = []
        allframes = []
        for action_frame, frame in self.framedata[character][action].items():
            if frame:
                #Does this frame have a hitbox?
                allframes.append(action_frame)
                if frame["iasa"]:
                    iasaframes.append(action_frame)
        if not iasaframes:
            return max(allframes)
        return min(iasaframes)

    def last_hitbox_frame(self, character, action):
        """Returns the last frame that a hitbox appears for a given action

        returns -1 if no hitboxes (not an attack action)

        Args:
            character (enums.Character): The character we're interested in
            action (enums.Action): The action we're interested in

        """
        # Grab only the subset that have a hitbox
        hitboxes = []
        for action_frame, frame in self.framedata[character][action].items():
            if frame:
                #Does this frame have a hitbox?
                if frame['hitbox_1_status'] or frame['hitbox_2_status'] \
                    or frame['hitbox_3_status'] or frame['hitbox_4_status'] or \
                        frame['projectile']:
                    hitboxes.append(action_frame)
        if not hitboxes:
            return -1
        return max(hitboxes)

    def frame_count(self, character, action):
        """Returns the count of total frames in the given action.

        Args:
            character (enums.Character): The character we're interested in
            action (enums.Action): The action we're interested in
        """
        frames = []
        for action_frame, _ in self.framedata[character][action].items():
            frames.append(action_frame)
        if not frames:
            return -1
        return max(frames)
    
    def first_intangible_frame(self, character, action):
        """Returns the first frame of an attack that the character is intangible
        
        returns -1 if no intangible frames
        
        Args:
            character (enums.Character): The character we're interested in
            action (enums.Action): The action we're interested in
        """
        # Grab only the subset that have intangibility
        frames = []
        for action_frame, frame in self.framedata[character][action].items():
            if frame:
                # Does this frame have intangibility?
                if frame['intangible']:
                    frames.append(action_frame)
        if not frames:
            return -1
        return min(frames)
    
    def last_intangible_frame(self, character, action):
        """Returns the last frame of an attack that the character is intangible
        
        returns -1 if no intangible frames
        
        Args:
            character (enums.Character): The character we're interested in
            action (enums.Action): The action we're interested in
        """
        # Grab only the subset that have intangibility
        frames = []
        for action_frame, frame in self.framedata[character][action].items():
            if frame:
                # Does this frame have intangibility?
                if frame['intangible']:
                    frames.append(action_frame)
        if not frames:
            return -1
        return max(frames)

    def _cleanupcsv(self):
        """ Helper function to remove all the non-attacking, non-rolling, non-B move actions """
        #Make a list of all the attacking action names
        attacks = []
        for row in self.rows:
            if row['hitbox_1_status'] or row['hitbox_2_status'] or \
                    row['hitbox_3_status'] or row['hitbox_4_status'] or \
                    row['projectile']:
                attacks.append(row['action'])
        #remove duplicates
        attacks = list(set(attacks))
        #Make a second pass, removing anything not in the list
        for row in list(self.rows):
            if row['action'] not in attacks and not self.is_roll(Character(row['character']), Action(row['action'])) \
                    and not self.is_bmove(Character(row['character']), Action(row['action'])):
                self.rows.remove(row)

    def _record_frame(self, gamestate):
        """ Record the frame in the given gamestate"""

        # First, adjust and record zero-indexing
        actionrow = {'character': gamestate.opponent_state.character.value, \
            'action': gamestate.opponent_state.action.value, \
            'zeroindex': False}

        if gamestate.opponent_state.action_frame == 0:
            actionrow["zeroindex"] = True
            gamestate.opponent_state.action_frame += 1

        alreadythere = False
        for i in self.actionrows:
            if i['character'] == actionrow['character'] and i['action'] == actionrow['action']:
                alreadythere = True
                if actionrow["zeroindex"]:
                    gamestate.opponent_state.action_frame += 1

        if not alreadythere:
            self.actionrows.append(actionrow)

        # So here's the deal... We don't want to count horizontal momentum for almost
        #   all air moves. Except a few. So let's just enumerate those. It's ugly,
        #   but whatever, you're not my boss
        xspeed = 0
        airmoves = gamestate.opponent_state.action in [Action.EDGE_ROLL_SLOW, Action.EDGE_ROLL_QUICK, Action.EDGE_GETUP_SLOW, \
            Action.EDGE_GETUP_QUICK, Action. EDGE_ATTACK_SLOW, Action.EDGE_ATTACK_QUICK, \
            Action.EDGE_JUMP_1_SLOW, Action.EDGE_JUMP_1_QUICK, Action.EDGE_JUMP_2_SLOW, Action.EDGE_JUMP_2_QUICK]

        if gamestate.opponent_state.on_ground or airmoves:
            xspeed = gamestate.opponent_state.position.x - gamestate.opponent_state.__prev_x

        # This is a bit strange, but here's why:
        #   The vast majority of actions don't actually affect vertical speed
        #   For most, the character just moves according to their normal momentum
        #   Any exceptions can be manually edited in
        #  However, there's plenty of attacks that make the character fly upward at a set
        #   distance, like up-b's. So keep those around
        yspeed = max(gamestate.opponent_state.position.y - gamestate.opponent_state.__prev_y, 0)

        # Some actions never have locomotion. Make sure to not count it
        if gamestate.opponent_state.action in [Action.TECH_MISS_UP, Action.TECH_MISS_DOWN, Action.LYING_GROUND_UP, Action.LYING_GROUND_DOWN]:
            xspeed = 0
            yspeed = 0

        row = { 'character': gamestate.opponent_state.character.value,
                'action': gamestate.opponent_state.action.value,
                'frame': gamestate.opponent_state.action_frame,
                'hitbox_1_status': gamestate.opponent_state.hitbox_1_status,
                'hitbox_1_x': (gamestate.opponent_state.hitbox_1_x - gamestate.opponent_state.position.x),
                'hitbox_1_y': (gamestate.opponent_state.hitbox_1_y - gamestate.opponent_state.position.y),
                'hitbox_1_size' : gamestate.opponent_state.hitbox_1_size,
                'hitbox_2_status': gamestate.opponent_state.hitbox_2_status,
                'hitbox_2_x': (gamestate.opponent_state.hitbox_2_x - gamestate.opponent_state.position.x),
                'hitbox_2_y': (gamestate.opponent_state.hitbox_2_y - gamestate.opponent_state.position.y),
                'hitbox_2_size' : gamestate.opponent_state.hitbox_2_size,
                'hitbox_3_status': gamestate.opponent_state.hitbox_3_status,
                'hitbox_3_x': (gamestate.opponent_state.hitbox_3_x - gamestate.opponent_state.position.x),
                'hitbox_3_y': (gamestate.opponent_state.hitbox_3_y - gamestate.opponent_state.position.y),
                'hitbox_3_size' : gamestate.opponent_state.hitbox_3_size,
                'hitbox_4_status': gamestate.opponent_state.hitbox_4_status,
                'hitbox_4_x': (gamestate.opponent_state.hitbox_4_x - gamestate.opponent_state.position.x),
                'hitbox_4_y': (gamestate.opponent_state.hitbox_4_y - gamestate.opponent_state.position.y),
                'hitbox_4_size' : gamestate.opponent_state.hitbox_4_size,
                'locomotion_x' : xspeed,
                'locomotion_y' : yspeed,
                'iasa' : gamestate.opponent_state.iasa,
                'facing_changed' : False,
                'projectile' : False
              }

        # Do we already have the previous frame recorded?
        for i in self.rows:
            if i['character'] == row['character'] and i['action'] == row['action'] and i['frame'] == row['frame']-1:
                # If the facing changed once, always have it changed
                if i["facing_changed"]:
                    row["facing_changed"] = True
        # If the facing changed from last frame, set the facing changed bool
        oldfacing = self.prevfacing.get(gamestate.opponent_state.action)
        if (oldfacing is not None) and (oldfacing != gamestate.opponent_state.facing):
            row["facing_changed"] = True

        if gamestate.opponent_state.facing == row["facing_changed"]:
            row["locomotion_x"] = -row["locomotion_x"]
        # If this is a backwards roll, flip it again
        if gamestate.opponent_state.action in [Action.ROLL_BACKWARD, Action.GROUND_ROLL_BACKWARD_UP, \
                Action.GROUND_ROLL_BACKWARD_DOWN, Action.BACKWARD_TECH]:
            row["locomotion_x"] = -row["locomotion_x"]

        if not gamestate.opponent_state.hitbox_1_status:
            row['hitbox_1_x'] = 0
            row['hitbox_1_y'] = 0
            row['hitbox_1_size'] = 0
        if not gamestate.opponent_state.hitbox_2_status:
            row['hitbox_2_x'] = 0
            row['hitbox_2_y'] = 0
            row['hitbox_2_size'] = 0
        if not gamestate.opponent_state.hitbox_3_status:
            row['hitbox_3_x'] = 0
            row['hitbox_3_y'] = 0
            row['hitbox_3_size'] = 0
        if not gamestate.opponent_state.hitbox_4_status:
            row['hitbox_4_x'] = 0
            row['hitbox_4_y'] = 0
            row['hitbox_4_size'] = 0

        # If this frame goes from having 0 projectiles to more than 0, then flag it
        oldprojcount = self.prevprojectilecount.get(gamestate.opponent_state.action)
        if oldprojcount is not None and oldprojcount == 0 and len(gamestate.projectiles) > 0:
            # Turnips are thrown, so don't count the turnip pull
            if gamestate.opponent_state.character != Character.PEACH or \
                    gamestate.opponent_state.action != Action.SWORD_DANCE_3_HIGH:
                row["projectile"] = True

        alreadythere = False
        for i in self.rows:
            if i['character'] == row['character'] and i['action'] == row['action'] and i['frame'] == row['frame']:
                alreadythere = True

        # Kludgey changes below:
        #   Marth's neutral attack 1 technically doesn't IASA until the last two frames,
        #       but it "loops" much sooner. Let's just call "looping" the same as IASA
        if row["character"] == Character.MARTH.value and row["action"] == Action.NEUTRAL_ATTACK_1.value \
                and row["frame"] >= 20:
            row["iasa"] = True
        if row["character"] == Character.PIKACHU.value and row["action"] == Action.NEUTRAL_ATTACK_1.value \
                and row["frame"] >= 6:
            row["iasa"] = True

        # Don't count the projectile during samus's charging
        if row["character"] == Character.SAMUS.value and row["action"] == Action.NEUTRAL_B_ATTACKING.value:
            row["projectile"] = False

        if not alreadythere:
            self.rows.append(row)

        self.prevfacing[gamestate.opponent_state.action] = gamestate.opponent_state.facing
        self.prevprojectilecount[gamestate.opponent_state.action] = len(gamestate.projectiles)

    def save_recording(self):
        """ DEV USE ONLY
        Saves a recorded frame to the framedata csv
        """
        self._cleanupcsv()
        self.writer.writerows(self.rows)
        self.actionwriter.writerows(self.actionrows)
        self.csvfile.close()
        self.actionfile.close()

    def slide_distance(self, player, initspeed, frames):
        """How far a character will slide in the given number of frames

        Args:
            player (gamestate.PlayerState): The player we're interested in
            initspeed (float): The character's starting speed
            frames (int): Maximum number of frames to calculate for
        """
        normalfriction = self.characterdata[player.character]["Friction"]
        friction = normalfriction
        totaldistance = 0
        walkspeed = self.characterdata[player.character]["MaxWalkSpeed"]
        # Just the speed, not direction
        absspeed = abs(initspeed)
        multiplier = 1
        for i in range(frames):
            # Special case for these two damn animations, for some reason. Thanks melee
            if player.action in [Action.TECH_MISS_UP]:
                if player.action_frame + i < 18:
                    friction = .051
                    multiplier = 1
                else:
                    friction = normalfriction
            # If we're sliding faster than the character's walk speed, then
            #   the slowdown is doubled
            elif absspeed > walkspeed:
                multiplier = 2
            else:
                multiplier = 1

            absspeed -= friction * multiplier
            if absspeed < 0:
                break
            totaldistance += absspeed
        if initspeed < 0:
            totaldistance = -totaldistance

        return totaldistance

    def _ccw(self, A,B,C):
        """Check if points A, B, and C are in counterclockwise order."""
        return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])

    def _on_segment(self, p, q, r):
        """Check if point q lies on the segment pr."""
        return min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])

    def _collinear(self, A, B, C):
        """Check if points A, B, and C are collinear"""
        return (B[1] - A[1]) * (C[0] - A[0]) == (C[1] - A[1]) * (B[0] - A[0])

    def _intersect(self, A,B,C,D):
        """Return true if line segments AB and CD intersect"""
        if self._ccw(A, C, D) != self._ccw(B, C, D) and self._ccw(A, B, C) != self._ccw(A, B, D):
            return True
        
        if self._collinear(A, B, C) and self._on_segment(A, C, B):
            return True
        
        if self._collinear(A, B, D) and self._on_segment(A, D, B):
            return True
        
        if self._collinear(C, D, A) and self._on_segment(C, A, D):
            return True
        
        if self._collinear(C, D, B) and self._on_segment(C, B, D):
            return True
        
        return False

    def get_platforms(self, gamestate, reference_pos=None):
        # Get list of all platforms, tuples of (height, left, right)
        platforms = []
        stage = gamestate.stage
        if stage == enums.Stage.NO_STAGE:
            return platforms
        
        height = 0
        if stage == enums.Stage.FOUNTAIN_OF_DREAMS:
            height = 0.002875
            slope_start = 51.1992
            slope_end = 53.633595
            slope_top = 0.623875
        elif stage == enums.Stage.YOSHIS_STORY:
            slope_start = 39.2005
        if reference_pos is not None and stage in [enums.Stage.FOUNTAIN_OF_DREAMS, enums.Stage.YOSHIS_STORY]:
            reference_x = abs(reference_pos[0])
            if reference_x > slope_start:
                if stage == enums.Stage.FOUNTAIN_OF_DREAMS:
                    # calc_slope = (slope_top - height) / (slope_end - slope_start)
                    height = slope_top
                elif stage == enums.Stage.YOSHIS_STORY:
                    height = -0.208339309495 * (reference_x - slope_start) + height
        platforms.append((height, -stages.EDGE_GROUND_POSITION[stage], stages.EDGE_GROUND_POSITION[stage]))
        top_plat = stages.top_platform_position(gamestate)
        if top_plat[0] is not None:
            platforms.append(top_plat)
        left_plat = stages.left_platform_position(gamestate)
        if left_plat[0] is not None:
            platforms.append(left_plat)
        right_plat = stages.right_platform_position(gamestate)
        if right_plat[0] is not None:
            platforms.append(right_plat)
        
        return platforms

    def get_closest_platform(self, gamestate, position, check_below=True):
        if gamestate.stage == enums.Stage.NO_STAGE:
            return None
        
        nearest_dist = 1000
        nearest_platform = None
        below_dist = 1000
        below_platform = None
        for platform in self.get_platforms(gamestate, position):
            left_edge = (platform[1], platform[0])
            right_edge = (platform[2], platform[0])
            
            if left_edge[0] is None:
                continue
            
            xdist = position[0] - left_edge[0]
            ydist = position[1] - left_edge[1]
            dist = math.sqrt((xdist**2) + (ydist**2))
            if dist < nearest_dist:
                nearest_dist = dist
                width = right_edge[0] - left_edge[0]
                nearest_platform = (left_edge[0] + width/2, left_edge[1], width)
            if left_edge[1] <= position[1] and dist < below_dist:
                below_dist = dist
                below_platform = (left_edge[0] + width/2, left_edge[1], width)
                        
        if check_below:
            return below_platform
            
        return nearest_platform
    
    def get_closest_edge(self, gamestate, position, check_below=True):
        if gamestate.stage == enums.Stage.NO_STAGE:
            return None
        
        nearest_dist = 1000
        nearest_edge = (None, 0)
        below_edge = (None, 0)
        below_dist = 1000
        for platform in self.get_platforms(gamestate):
            for i in range(1, len(platform)):
                edge_type = -1 if i == 1 else 1
                edge = (platform[i], platform[0])
                
                if edge[0] is None:
                    continue
                
                xdist = position[0] - edge[0]
                ydist = position[1] - edge[1]
                dist = math.sqrt((xdist**2) + (ydist**2))
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest_edge = (edge, edge_type)
                if edge[1] <= position[1] and dist < below_dist:
                    below_dist = dist
                    below_edge = (edge, edge_type)
                        
        if check_below:
            return below_edge
            
        return nearest_edge

    def project_hit_location(self, gamestate, player, frames=-1, y_margin=0.0, collide_below_platforms=False):
        """How far does the given character fly, assuming they've been hit?
            Only considers air-movement, not ground sliding.
            Projection ends if hitstun ends, or if a platform is encountered

        Note:
            Platform collision doesn't take ECB changes into account.
                This means that the timing of collision can be off by a couple frames. Since it's possible
                for someone's Y position to travel below the platform by quite a bit before registering as "collided"

        Args:
            gamestate (GameState): The current game state to use
            player (GameState.PlayerState): The player state to calculate for
            frames (int): The number of frames to calculate for. -1 means "until end of hitstun"

        Returns:
            (float, float, int): x, y coordinates of the place the character will end up at the end of hitstun, plus frames until that position
        """
        speed_x, speed_y_attack, speed_y_self = player.speed_x_attack, player.speed_y_attack, player.speed_y_self
        position_x, position_y = player.position.x, player.position.y
        termvelocity = self.characterdata[player.character]["TerminalVelocity"]
        gravity = self.characterdata[player.character]["Gravity"]
        
        if player.on_ground and not self.is_hit(player):
            gravity = 0

        # Get list of all platforms, tuples of (height, left, right)
        platforms = self.get_platforms(gamestate)

        angle = math.atan2(speed_x, speed_y_attack)
        horizontal_decay = abs(0.051 * math.cos(-angle + (math.pi/2)))
        vertical_decay = abs(0.051 * math.sin(-angle + (math.pi/2)))

        init_frames = frames
        if init_frames == -1:
            init_frames = player.hitstun_frames_left
        
        frames_left = init_frames

        # Always quit out after 180 iterations just in case. So we don't accidentally infinite loop here
        failsafe = 180
        
        # Check if initial frame is already intersecting with a platform
        for platform in platforms:
            # We have two line segments. Check if they intersect
            #   AB is platform, CD is character
            A = (platform[1], platform[0])
            B = (platform[2], platform[0])
            C = (position_x, position_y + y_margin)
            D = (position_x+speed_x, position_y + speed_y_attack + speed_y_self)
            
            if self._intersect(A, B, C, D):
                # speed_x/2 to just assume we intersect half way through. This will be wrong, but close enough
                return (position_x+(speed_x/2), platform[0], 181-failsafe)

        while frames_left > 0 and failsafe > 0:
            # Check if the character will hit a platform
            for platform in platforms:
                # Collisions with platforms can only happen from above
                if not collide_below_platforms and position_y < platform[0]:
                    continue
                
                # We have two line segments. Check if they intersect
                #   AB is platform, CD is character
                A = (platform[1], platform[0])
                B = (platform[2], platform[0])
                C = (position_x, position_y + y_margin)
                D = (position_x+speed_x, position_y + speed_y_attack + speed_y_self)
                
                if self._intersect(A, B, C, D):
                    # speed_x/2 to just assume we intersect half way through. This will be wrong, but close enough
                    return (position_x+(speed_x/2), platform[0], 181-failsafe)

            position_x += speed_x
            position_y += speed_y_attack
            position_y += speed_y_self

            # Update the speeds
            speed_y_self = max(-termvelocity, speed_y_self - gravity)

            if speed_y_attack > 0:
                speed_y_attack = max(0, speed_y_attack - vertical_decay)
            else:
                speed_y_attack = min(0, speed_y_attack + vertical_decay)

            if speed_x > 0:
                speed_x = max(0, speed_x - horizontal_decay)
            else:
                speed_x = min(0, speed_x + horizontal_decay)
            failsafe -= 1
            frames_left -= 1

        return position_x, position_y, init_frames
    
    def is_attacking(self, player):
        """Whether the player is in an attacking state"""
        return (
            self.is_attack(player.character, player.action) or
            self.is_normal_attacking(player) or
            self.is_special_attacking(player) or
            self.is_item_attacking(player) or
            self.is_grabbing(player)
        )
    
    def in_iasa_attack(self, player):
        """Whether the player is in an interruptible attack state"""
        iasa_frame = self.iasa(player.character, player.action)
        return (
            iasa_frame != -1 and
            iasa_frame <= player.action_frame
        )
        
    def can_attack(self, player):
        """Whether the player can perform a normal or special attack in the current state"""
        return (
            self.is_actionable(player) and
            not self.is_grabbing(player) and
            not self.is_shielding(player) and
            not player.action == Action.KNEE_BEND
        )
        
    def can_special_attack(self, player):
        """Whether the player can perform a special attack in the current state"""
        return (
            self.can_attack(player) and
            not player.action == Action.DASHING and
            not player.action == Action.RUN_BRAKE
        )
        
    def can_jump(self, player):
        """Whether the player can jump in their current state"""
        return (
            self.is_actionable(player)
        )
        
    def can_pass_platforms(self, player):
        """Whether the player can fall through platforms in their current state"""
        return (
            self.is_falling(player) and
            # Check if stick y-axis is below specific value
            player.controller_state.raw_main_stick[1] <= -45
        )
        
    def counter_action(self, player):
        """Get the action corresponding to a counter for the given player.
           None if no counter is possible"""
        airborne = player.on_ground
        character = player.character
        
        if character == Character.ROY or character == Character.MARTH:
            if not airborne:
                return Action.DOWN_B_GROUND
            else:
                return Action.DOWN_B_AIR
        
        if character == Character.PEACH:
            if not airborne:
                return Action.DOWN_B_STUN
            else:
                return Action.UP_B_GROUND
        
        return None
    
    def counter_window(self, player):
        """Get the counter window for the given player
           (0, 0) if no counter is possible"""
        character = player.character
        
        if character == Character.ROY:
            return (7, 21)
        elif character == Character.MARTH:
            return (4, 30)
        elif character == Character.PEACH:
            return (10, 30)
            
        return (0, 0)
    
    def intangible_window(self, player, action):
        """Get the intangibility window for the given player and action
           (0, 0) if there is no intangibility for the given action"""
        character = player.character
        
        first_frame = self.first_intangible_frame(character, action)
        last_frame = self.last_intangible_frame(character, action)
        
        if first_frame != -1:
            return (first_frame, last_frame)
            
        return (0, 0)
    
    def check_attack(self, gamestate, player):
        """Checks whether the player's current attack will be successfully performed"""
        if self.is_attacking(player):
            character = player.character
            action = player.action
            current_frame = player.action_frame
            state = self.attack_state(character, action, current_frame)
            
            if state == AttackState.ATTACKING:
                return True
            elif state == AttackState.WINDUP:
                # TODO: Simulate surrounding players' attacks to verify the windup will be uninterrupted
                if player.on_ground:
                    # TODO: Account for cases like wispy which slide players off ledges
                    return True
                else:
                    # We project the player's position until they reach an attacking frame
                    frames_left = self.first_hitbox_frame(character, action) - current_frame
                    position_x, position_y, end_frame = self.project_hit_location(gamestate, player, frames_left)
                    
                    # This is guaranteed to be an intersection with the stage or a platform
                    if end_frame < frames_left:
                        return False
                    
                    return True
                    
        return self.is_grabbing(player) or self.is_special_attacking(player)
    
    def is_actionable(self, player):
        """Whether the player is able to change their action
           in the current state"""
        return (
            not self.is_dead(player) and
            not self.is_hit(player) and
            not self.is_damaged(player) and
            # TODO: Account for iasa special attacks
            (not self.is_normal_attacking(player) or self.in_iasa_attack(player)) and
            not player.action == Action.NOTHING_STATE and
            not player.action == Action.ON_HALO_DESCENT and
            not player.action == Action.DEAD_FALL and
            not player.action == Action.SPECIAL_FALL_FORWARD and
            not player.action == Action.SPECIAL_FALL_BACK and
            not player.action == Action.TECH_MISS_UP and
            not player.action == Action.GROUND_GETUP and
            not player.action == Action.GROUND_ROLL_FORWARD_UP and
            not player.action == Action.GROUND_ROLL_BACKWARD_UP and
            not player.action == Action.TECH_MISS_DOWN and
            not player.action == Action.NEUTRAL_GETUP and
            not player.action == Action.GROUND_ROLL_FORWARD_DOWN and
            not player.action == Action.GROUND_ROLL_BACKWARD_DOWN and
            not player.action == Action.NEUTRAL_TECH and
            not player.action == Action.FORWARD_TECH and
            not player.action == Action.BACKWARD_TECH and
            not player.action == Action.SHIELD_BREAK_FLY and
            not player.action == Action.SHIELD_BREAK_FALL and
            not player.action == Action.SHIELD_BREAK_DOWN_U and
            not player.action == Action.SHIELD_BREAK_DOWN_D and
            not player.action == Action.SHIELD_BREAK_STAND_U and
            not player.action == Action.SHIELD_BREAK_STAND_D and
            not player.action == Action.SHIELD_BREAK_TEETER and
            not player.action == Action.ROLL_FORWARD and
            not player.action == Action.ROLL_BACKWARD and
            not player.action == Action.SPOTDODGE and
            not player.action == Action.AIRDODGE and
            not player.action == Action.EDGE_CATCHING and
            not player.action == Action.EDGE_GETUP_SLOW and
            not player.action == Action.EDGE_GETUP_QUICK and
            not player.action == Action.EDGE_ROLL_SLOW and
            not player.action == Action.EDGE_ROLL_QUICK and
            not player.action == Action.EDGE_JUMP_1_SLOW and
            not player.action == Action.EDGE_JUMP_2_SLOW and
            not player.action == Action.EDGE_JUMP_1_QUICK and
            not player.action == Action.EDGE_JUMP_2_QUICK and
            not player.action == Action.TAUNT_RIGHT and
            not player.action == Action.TAUNT_LEFT and
            not player.action == Action.ENTRY and
            not player.action == Action.ENTRY_START and
            not player.action == Action.ENTRY_END and
            not player.action == Action.LASER_GUN_PULL
        )
    
    def is_dead(self, player):
        """Whether the player is in a death state"""
        return (
            player.action == Action.DEAD_DOWN or
            player.action == Action.DEAD_FLY or
            player.action == Action.DEAD_FLY_SPLATTER or
            player.action == Action.DEAD_FLY_SPLATTER_FLAT or
            player.action == Action.DEAD_FLY_SPLATTER_FLAT_ICE or
            player.action == Action.DEAD_FLY_STAR or
            player.action == Action.DEAD_FLY_STAR_ICE or
            player.action == Action.DEAD_LEFT or
            player.action == Action.DEAD_RIGHT or
            player.action == Action.DEAD_UP
        )

    def is_thrown(self, player):
        """Whether the player is in a thrown state"""
        return (
            player.action == Action.THROWN_FORWARD or
            player.action == Action.THROWN_BACK or
            player.action == Action.THROWN_UP or
            player.action == Action.THROWN_DOWN or
            player.action == Action.THROWN_DOWN_2 or
            player.action == Action.THROWN_KIRBY_STAR or
            player.action == Action.THROWN_COPY_STAR or
            player.action == Action.THROWN_KIRBY or
            player.action == Action.BURY or
            player.action == Action.DAMAGE_BIND or
            player.action == Action.THROWN_MEWTWO or
            player.action == Action.THROWN_MEWTWO_AIR
        )

    def is_damaged(self, player):
        """Whether the player is in a damage state"""
        return (
            player.action == Action.DAMAGE_HIGH_1 or
            player.action == Action.DAMAGE_HIGH_2 or
            player.action == Action.DAMAGE_HIGH_3 or
            player.action == Action.DAMAGE_NEUTRAL_1 or
            player.action == Action.DAMAGE_NEUTRAL_2 or
            player.action == Action.DAMAGE_NEUTRAL_3 or
            player.action == Action.DAMAGE_LOW_1 or
            player.action == Action.DAMAGE_LOW_2 or
            player.action == Action.DAMAGE_LOW_3 or
            player.action == Action.DAMAGE_AIR_1 or
            player.action == Action.DAMAGE_AIR_2 or
            player.action == Action.DAMAGE_AIR_3 or
            player.action == Action.DAMAGE_SCREW or
            player.action == Action.DAMAGE_SCREW_AIR or
            player.action == Action.DAMAGE_FLY_HIGH or
            player.action == Action.DAMAGE_FLY_NEUTRAL or
            player.action == Action.DAMAGE_FLY_LOW or
            player.action == Action.DAMAGE_FLY_TOP or
            player.action == Action.DAMAGE_FLY_ROLL or
            player.action == Action.LYING_GROUND_UP_HIT or
            player.action == Action.DAMAGE_GROUND or
            player.action == Action.PUMMELED_HIGH or
            player.action == Action.GRAB_PUMMELED or
            player.action == Action.DAMAGE_SONG or
            player.action == Action.DAMAGE_SONG_WAIT or
            player.action == Action.DAMAGE_SONG_RV or
            player.action == Action.DAMAGE_BIND or
            player.action == Action.DAMAGE_ICE or
            player.action == Action.DAMAGE_ICE_JUMP or
            self.is_thrown(player)
        )
    
    def is_grabbed(self, player):
        """Whether the player is in a grabbed state"""
        return (
            player.action == Action.GRABBED or
            player.action == Action.GRAB_PULL or
            player.action == Action.GRAB_ESCAPE or
            player.action == Action.GRAB_JUMP or
            player.action == Action.GRAB_NECK or
            player.action == Action.GRAB_FOOT or
            player.action == Action.GRABBED_WAIT_HIGH
        )
    
    def has_misteched(self, player):
        return (player.action == Action.TECH_MISS_UP or
                player.action == Action.TECH_MISS_DOWN or
                player.action == Action.LYING_GROUND_UP or
                player.action == Action.LYING_GROUND_DOWN)
    
    def is_hit(self, player):
        """Whether the player is in a hit state"""
        return (
            self.is_damaged(player) or
            player.action == Action.SHIELD_STUN or
            player.action == Action.BURY_WAIT or
            player.action == Action.BURY_JUMP or
            player.action == Action.DOWN_REFLECT or
            player.action == Action.DOWN_B_STUN or
            (player.hitstun_frames_left and
             (self.is_damaged(player) or
              player.action == Action.TUMBLING))
        )
        
    def is_normal_attacking(self, player):
        """Whether the player is in an normal attack state"""
        return (
            player.action == Action.NEUTRAL_ATTACK_1 or
            player.action == Action.NEUTRAL_ATTACK_2 or
            player.action == Action.NEUTRAL_ATTACK_3 or
            player.action == Action.LOOPING_ATTACK_START or
            player.action == Action.LOOPING_ATTACK_MIDDLE or
            player.action == Action.LOOPING_ATTACK_END or
            player.action == Action.FTILT_HIGH or
            player.action == Action.FTILT_HIGH_MID or
            player.action == Action.FTILT_MID or
            player.action == Action.FTILT_LOW_MID or
            player.action == Action.FTILT_LOW or
            player.action == Action.UPTILT or
            player.action == Action.DOWNTILT or
            player.action == Action.FSMASH_HIGH or
            player.action == Action.FSMASH_MID_HIGH or
            player.action == Action.FSMASH_MID or
            player.action == Action.FSMASH_MID_LOW or
            player.action == Action.FSMASH_LOW or
            player.action == Action.UPSMASH or
            player.action == Action.DOWNSMASH or
            player.action == Action.NAIR or
            player.action == Action.FAIR or
            player.action == Action.BAIR or
            player.action == Action.UAIR or
            player.action == Action.DAIR or
            player.action == Action.NAIR_LANDING or
            player.action == Action.FAIR_LANDING or
            player.action == Action.BAIR_LANDING or
            player.action == Action.UAIR_LANDING or
            player.action == Action.DAIR_LANDING or
            player.action == Action.LIFT_WAIT or
            player.action == Action.LIFT_WALK_1 or
            player.action == Action.LIFT_WALK_2 or
            player.action == Action.LIFT_TURN or
            player.action == Action.GROUND_ATTACK_UP or
            player.action == Action.GETUP_ATTACK or
            player.action == Action.EDGE_ATTACK_SLOW or
            player.action == Action.EDGE_ATTACK_QUICK or
            player.action == Action.THROW_UP or
            player.action == Action.THROW_DOWN or
            player.action == Action.THROW_BACK or
            player.action == Action.THROW_FORWARD
        )
        
    def is_special_attacking(self, player):
        """Whether the player is in a special attack state"""
        return (
            self.is_bmove(player.character, player.action) and
            (player.action == Action.YOSHI_EGG or
            player.action == Action.KIRBY_YOSHI_EGG or
            player.action == Action.DOWN_REFLECT or
            player.action == Action.LASER_GUN_PULL or
            player.action == Action.NEUTRAL_B_CHARGING or
            player.action == Action.NEUTRAL_B_ATTACKING or
            player.action == Action.NEUTRAL_B_FULL_CHARGE or
            player.action == Action.NEUTRAL_B_CHARGING_AIR or
            player.action == Action.NEUTRAL_B_ATTACKING_AIR or
            player.action == Action.NEUTRAL_B_FULL_CHARGE_AIR or
            player.action == Action.DOWN_B_GROUND_START or
            player.action == Action.DOWN_B_GROUND or
            player.action == Action.SHINE_TURN or
            player.action == Action.DOWN_B_STUN or
            player.action == Action.DOWN_B_AIR or
            player.action == Action.UP_B_GROUND or
            player.action == Action.SHINE_RELEASE_AIR or
            player.action == Action.SWORD_DANCE_1 or
            player.action == Action.SWORD_DANCE_2_HIGH or
            player.action == Action.SWORD_DANCE_2_MID or
            player.action == Action.SWORD_DANCE_3_HIGH or
            player.action == Action.SWORD_DANCE_3_MID or
            player.action == Action.SWORD_DANCE_3_LOW or
            player.action == Action.SWORD_DANCE_4_HIGH or
            player.action == Action.SWORD_DANCE_4_MID or
            player.action == Action.SWORD_DANCE_4_LOW or
            player.action == Action.SWORD_DANCE_1_AIR or
            player.action == Action.SWORD_DANCE_2_HIGH_AIR or
            player.action == Action.SWORD_DANCE_2_MID_AIR or
            player.action == Action.SWORD_DANCE_3_HIGH_AIR or
            player.action == Action.SWORD_DANCE_3_MID_AIR or
            player.action == Action.SWORD_DANCE_3_LOW_AIR or
            player.action == Action.SWORD_DANCE_4_HIGH_AIR or
            player.action == Action.SWORD_DANCE_4_MID_AIR or
            player.action == Action.SWORD_DANCE_4_LOW_AIR or
            player.action == Action.FOX_ILLUSION_START or
            player.action == Action.FOX_ILLUSION or
            player.action == Action.FOX_ILLUSION_SHORTENED or
            player.action == Action.FIREFOX_WAIT_GROUND or
            player.action == Action.FIREFOX_WAIT_AIR or
            player.action == Action.FIREFOX_GROUND or
            player.action == Action.FIREFOX_AIR or
            player.action == Action.UP_B_AIR or
            player.action == Action.MARTH_COUNTER or
            player.action == Action.MARTH_COUNTER_FALLING or
            player.action == Action.NESS_SHEILD_START or
            player.action == Action.NESS_SHEILD or
            player.action == Action.NESS_SHEILD_AIR or
            player.action == Action.NESS_SHEILD_AIR_END or
            player.action == Action.DK_GROUND_POUND_START or
            player.action == Action.DK_GROUND_POUND or
            player.action == Action.DK_GROUND_POUND_END or
            player.action == Action.KIRBY_BLADE_GROUND or
            player.action == Action.KIRBY_BLADE_UP or
            player.action == Action.KIRBY_BLADE_APEX or
            player.action == Action.KIRBY_BLADE_DOWN or
            player.action == Action.KIRBY_STONE_FORMING_GROUND or
            player.action == Action.KIRBY_STONE_RESTING or
            player.action == Action.KIRBY_STONE_RELEASE or
            player.action == Action.KIRBY_STONE_FORMING_AIR or
            player.action == Action.KIRBY_STONE_FALLING or
            player.action == Action.KIRBY_STONE_UNFORMING)
        )
    
    def is_item_attacking(self, player):
        """Whether the player is in an item attack state"""
        return (
            player.action == Action.ITEM_THROW_LIGHT_FORWARD or
            player.action == Action.ITEM_THROW_LIGHT_BACK or
            player.action == Action.ITEM_THROW_LIGHT_HIGH or
            player.action == Action.ITEM_THROW_LIGHT_LOW or
            player.action == Action.ITEM_THROW_LIGHT_DASH or
            player.action == Action.ITEM_THROW_LIGHT_DROP or
            player.action == Action.ITEM_THROW_LIGHT_AIR_FORWARD or
            player.action == Action.ITEM_THROW_LIGHT_AIR_BACK or
            player.action == Action.ITEM_THROW_LIGHT_AIR_HIGH or
            player.action == Action.ITEM_THROW_LIGHT_AIR_LOW or
            player.action == Action.ITEM_THROW_HEAVY_FORWARD or
            player.action == Action.ITEM_THROW_HEAVY_BACK or
            player.action == Action.ITEM_THROW_HEAVY_HIGH or
            player.action == Action.ITEM_THROW_HEAVY_LOW or
            player.action == Action.ITEM_THROW_LIGHT_SMASH_FORWARD or
            player.action == Action.ITEM_THROW_LIGHT_SMASH_BACK or
            player.action == Action.ITEM_THROW_LIGHT_SMASH_UP or
            player.action == Action.ITEM_THROW_LIGHT_SMASH_DOWN or
            player.action == Action.ITEM_THROW_LIGHT_AIR_SMASH_FORWARD or
            player.action == Action.ITEM_THROW_LIGHT_AIR_SMASH_BACK or
            player.action == Action.ITEM_THROW_LIGHT_AIR_SMASH_HIGH or
            player.action == Action.ITEM_THROW_LIGHT_AIR_SMASH_LOW or
            player.action == Action.ITEM_THROW_HEAVY_AIR_SMASH_FORWARD or
            player.action == Action.ITEM_THROW_HEAVY_AIR_SMASH_BACK or
            player.action == Action.ITEM_THROW_HEAVY_AIR_SMASH_HIGH or
            player.action == Action.ITEM_THROW_HEAVY_AIR_SMASH_LOW or
            player.action == Action.BEAM_SWORD_SWING_1 or
            player.action == Action.BEAM_SWORD_SWING_2 or
            player.action == Action.BEAM_SWORD_SWING_3 or
            player.action == Action.BEAM_SWORD_SWING_4 or
            player.action == Action.BAT_SWING_1 or
            player.action == Action.BAT_SWING_2 or
            player.action == Action.BAT_SWING_3 or
            player.action == Action.BAT_SWING_4 or
            player.action == Action.PARASOL_SWING_1 or
            player.action == Action.PARASOL_SWING_2 or
            player.action == Action.PARASOL_SWING_3 or
            player.action == Action.PARASOL_SWING_4 or
            player.action == Action.FAN_SWING_1 or
            player.action == Action.FAN_SWING_2 or
            player.action == Action.FAN_SWING_3 or
            player.action == Action.FAN_SWING_4 or
            player.action == Action.STAR_ROD_SWING_1 or
            player.action == Action.STAR_ROD_SWING_2 or
            player.action == Action.STAR_ROD_SWING_3 or
            player.action == Action.STAR_ROD_SWING_4 or
            player.action == Action.LIP_STICK_SWING_1 or
            player.action == Action.LIP_STICK_SWING_2 or
            player.action == Action.LIP_STICK_SWING_3 or
            player.action == Action.LIP_STICK_SWING_4 or
            player.action == Action.ITEM_PARASOL_OPEN or
            player.action == Action.ITEM_PARASOL_FALL or
            player.action == Action.ITEM_PARASOL_FALL_SPECIAL or
            player.action == Action.ITEM_PARASOL_DAMAGE_FALL or
            player.action == Action.GUN_SHOOT or
            player.action == Action.GUN_SHOOT_AIR or
            player.action == Action.GUN_SHOOT_EMPTY or
            player.action == Action.GUN_SHOOT_AIR_EMPTY or
            player.action == Action.FIRE_FLOWER_SHOOT or
            player.action == Action.FIRE_FLOWER_SHOOT_AIR or
            player.action == Action.ITEM_SCREW or
            player.action == Action.ITEM_SCREW_AIR or
            player.action == Action.DAMAGE_SCREW or
            player.action == Action.DAMAGE_SCREW_AIR or
            player.action == Action.ITEM_SCOPE_START or
            player.action == Action.ITEM_SCOPE_RAPID or
            player.action == Action.ITEM_SCOPE_FIRE or
            player.action == Action.ITEM_SCOPE_END or
            player.action == Action.ITEM_SCOPE_AIR_START or
            player.action == Action.ITEM_SCOPE_AIR_RAPID or
            player.action == Action.ITEM_SCOPE_AIR_FIRE or
            player.action == Action.ITEM_SCOPE_AIR_END or
            player.action == Action.ITEM_SCOPE_START_EMPTY or
            player.action == Action.ITEM_SCOPE_RAPID_EMPTY or
            player.action == Action.ITEM_SCOPE_FIRE_EMPTY or
            player.action == Action.ITEM_SCOPE_END_EMPTY or
            player.action == Action.ITEM_SCOPE_AIR_START_EMPTY or
            player.action == Action.ITEM_SCOPE_AIR_RAPID_EMPTY or
            player.action == Action.ITEM_SCOPE_AIR_FIRE_EMPTY or
            player.action == Action.ITEM_SCOPE_AIR_END_EMPTY or
            player.action == Action.WARP_STAR_JUMP or
            player.action == Action.WARP_STAR_FALL or
            player.action == Action.HAMMER_WAIT or
            player.action == Action.HAMMER_WALK or
            player.action == Action.HAMMER_TURN or
            player.action == Action.HAMMER_KNEE_BEND or
            player.action == Action.HAMMER_FALL or
            player.action == Action.HAMMER_JUMP or
            player.action == Action.HAMMER_LANDING
        )
        
    def is_grabbing(self, player):
        """Whether the player is in a Z-grab state"""
        return (
            player.action == Action.GRAB or
            player.action == Action.GRAB_PULLING or
            player.action == Action.GRAB_RUNNING or
            player.action == Action.GRAB_RUNNING_PULLING or
            player.action == Action.GRAB_WAIT or
            player.action == Action.GRAB_PUMMEL or
            player.action == Action.GRAB_BREAK or
            player.action == Action.THROW_FORWARD or
            player.action == Action.THROW_BACK or
            player.action == Action.THROW_UP or
            player.action == Action.THROW_DOWN or
            player.action == Action.GRAB_PULLING_HIGH or
            player.action == Action.LIFT_WAIT or
            player.action == Action.LIFT_WALK_1 or
            player.action == Action.LIFT_WALK_2 or
            player.action == Action.LIFT_TURN
        )
        
    def is_shielding(self, player):
        return (
            player.action == Action.SHIELD_START or
            player.action == Action.SHIELD or
            player.action == Action.SHIELD_STUN or
            player.action == Action.SHIELD_REFLECT
        )
        
    def is_falling(self, player):
        """Whether the player is in a fall state"""
        return (
            player.action == Action.FALLING or
            player.action == Action.FALLING_FORWARD or
            player.action == Action.FALLING_BACKWARD or
            player.action == Action.FALLING_AERIAL or
            player.action == Action.FALLING_AERIAL_FORWARD or
            player.action == Action.FALLING_AERIAL_BACKWARD or
            player.action == Action.DEAD_FALL or
            player.action == Action.SPECIAL_FALL_FORWARD or
            player.action == Action.SPECIAL_FALL_BACK or
            player.action == Action.ITEM_PARASOL_FALL or
            player.action == Action.ITEM_PARASOL_FALL_SPECIAL or
            player.action == Action.ITEM_PARASOL_DAMAGE_FALL or
            player.action == Action.PLATFORM_DROP or
            player.action == Action.EDGE_JUMP_2_SLOW or
            player.action == Action.EDGE_JUMP_2_QUICK or
            player.action == Action.WARP_STAR_FALL or
            player.action == Action.HAMMER_FALL or
            player.action == Action.PARASOL_FALLING
        )
    
    def is_item_pulling(self, player):
        """Whether the player is pulling out an item"""
        player_char = player.character
        player_action = player.action
        return (
            player_action == Action.ITEM_PICKUP_LIGHT or
            player_action == Action.ITEM_PICKUP_HEAVY or
            (
                player_char == Character.LINK and
                player_action == Action.SWORD_DANCE_1_AIR or
                player_action == Action.SWORD_DANCE_2_HIGH_AIR
            ) or
            (
                player_char == Character.PEACH and
                player_action == Action.SWORD_DANCE_3_HIGH
            )
        )
    
    def is_jumping(self, player):
        return (player.action == Action.KNEE_BEND or
                player.action == Action.JUMPING_FORWARD or
                player.action == Action.JUMPING_BACKWARD or
                player.action == Action.JUMPING_ARIAL_FORWARD or
                player.action == Action.JUMPING_ARIAL_BACKWARD)