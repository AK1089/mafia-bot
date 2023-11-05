from enum import Enum

class ChannelIDs(Enum):
    thoughts = 1033586597158994010
    bot_commands = 1033587183866630165
    host = 1060588897928753152
    log = 1060848922320445490

    black_box = 1032355965099573262
    documentation = 1033578447706017812
    ship_manifest = 1033578377220718602
    roles_and_setup = 1033578494803849328
    questions = 1033578604740759622

    pregame = 1033588493970051082
    spoiler_free_memes = 1034148202221420633
    spectator_chat = 1034452807933239327
    spectator_memes = 1034452839797370880
    spectator_vc = 1055260684117606440
    
    deep_ocean = 1056309690147012628
    hydrophone_receiver = 1062457114724937859
    
    port = 1034459912228589671
    starboard = 1056299139501150329

    hackers = 1056246170814533772
    deep_sea_microphone = 1056312335066734724
    wiretap_receiver = 1056312449017589850
    recruitment = 1056313294450868264

    engine_rooms = 1037883491653787649


class CategoryIDs(Enum):
    host_only = 1033586559645126687
    the_control_room = 1032355965099573260
    the_periscope = 1033580965060161536
    out_at_sea = 1056309546886381598
    the_cafeteria = 1034457845242019940
    weaponry_room = 1055256226839134343
    crew_quarters = 1033584997585662012
    engine_rooms = 1032356102936997908


class RoleIDs(Enum):
    host = 1033581915560738846
    recruit = 1032357180806017076
    overboard = 1032357236934197248
    spectator = 1032357306748371006


MegaMessages = {
    "votes": 1133117814555824269,
    "actions": 1133117821686136922
}

identifier_sorting_key = lambda x: int(x, base=16)

targetcount_by_role = {
    ("circuit operator", True): (3, 0, False),
    ("door rigger", True): (1, 0, True),
    ("radio specialist", False): (4, 0, False),
    ("proximity engineer", True): (2, 0, True),
    ("intubation specialist", True): (1, 0, False),
    ("naval responder", True): (1, 0, False),
    ("ambusher", True): (2, 0, False),
    ("retired infantryman", True): (1, 0, True),
    ("backstairs broker", False): (1, 0, True),
    ("recon agent", True): (1, 0, False),
    ("conflict manager", False): (3, 0, True),
    ("bug operator", True): (2, 0, True),
    ("oceanic cartographer", True): (1, 0, False),
    ("course charter", True): (1, 0, True),
    ("wiring expert", True): (1, 0, False),
    ("reflection engineer", True): (1, 0, False),
    ("contingency specialist", True): (1, 0, False),

    ("logistics manager", True): (1, 1, True),
    ("special operations unit", True): (1, 1, True),
    ("turbulence driver", True): (0, 1, True),
    ("naval commander", True): (2, 0, True)
}


alignment_by_role = {
    "circuit operator": 0,
    "radio specialist": 0,
    "proximity engineer": 0,
    "backstairs broker": 0,
    "recon agent": 0,
    "bug operator": 0,
    "oceanic cartographer": 0,
    "conflict manager": 0,
    "door rigger": 0,
    "ambusher": 0,
    "retired infantryman": 0,
    "intubation specialist": 0,
    "naval responder": 0,
    "reflection engineer": 0,
    "course charter": 0,
    "hydrophone manager": 0,
    "wiring expert": 0,
    "contingency specialist": 0,

    "shield tech": 1,
    "commanding officer": 1,
    "interrogation specialist": 1,
    "covert unit": 1,
    "assassin": 1,
    "hull maintenance operator": 1,
    "reactor machinist": 1,

    "logistics manager": 2,
    "special operations unit": 2,
    "scuba diver": 2,
    "turbulence driver": 2,
    "naval commander": 2
}

hacker_ability_names = ["Basic Attack",
                        "Protective Seal",
                        "Data Corruption",
                        "Switch",
                        "Misinformation",
                        "Data Forensics",
                        "Door Logger",
                        "Wiretap",
                        "Vote Interception",
                        "Locked Door",
                        "Mask",
                        "Information-Theoretic-Erasure"
                        ]

help_command_text_global = """
# Bot Commands - General
- `>target [*players]` (use to target players with day/night actions)
- `>message [player]` (use once per day to open a DM with a player)
- `>vote [player]` (use during the day to vote to lynch a player)"""

help_command_text_hackers = """
# Bot Commands - Hackers Only
- `>hacker plan` (use to see the current team plan for the night)
- `>hacker ability [1-13] [mafia member ID][target's ID]` (use to take actions)"""

help_command_text_me = """
# Bot Commands - Game Progression
- `>manual_reminder` (use to manually trigger the phase reminder)
- `>manual_night_end` (use to manually trigger the end of phase)
- `>manual_phasechange` (use to manually trigger the start of the next phase)
- `>toggleloop` (use to control whether phases shift automatically)

# Bot Commands - Viewing Data
- `>export` (use to export the current player data to disk)
- `>import [timestamp]` (use to import the player data as of timestamp)
- `>deleteall` (use to wipe the database clean)
- `>change_data [id] [property] [data]` (use to edit entries in a database)
- `>view_player [id]` (use to view a player's data)
- `>view_actions` (use to view all actions and votes this phase)
- `>view_global` (use to view the game state as of now)

# Bot Commands - General Administration
- `>say [text]` (use to make the bot repeat what you say)
- `>execute [code]` (use to execute code at will)
- `>shutdown` (use to shut down the bot)
"""