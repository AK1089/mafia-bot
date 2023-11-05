from disnake.ext import commands, tasks
import disnake
from datetime import datetime, time, timedelta, timezone
from re import findall
import pymongo
from player import *
from serverdata import *
from wts import *
import shelve



# all intents because why not, and prefix > for commands
bot: commands.Bot = commands.Bot(">", intents=disnake.Intents.all(), help_command=None)
CURRENT_PHASE = 0
all_players: list[Player] = []


# scheduled task times
tz = timezone(timedelta(hours=0))
times_reminder          = [time(18, 0, 0, tzinfo=tz)]
times_phasechange_start = [time(21, 0, 0, tzinfo=tz)]
times_phasechange_end   = [time(22, 0, 0, tzinfo=tz)]



# database client connection with my MongoDB credentials (code version)
# objects are created to connect to the votes table
database_client_connection = pymongo.MongoClient("YOUR MONGODB ACCESS CODE GOES HERE")["everything"]
database_votes = database_client_connection["votes"]
database_players = database_client_connection["players"]
database_actions = database_client_connection["actions"]



# gets a phase identifier (eg. Day 0 or N2) from a phase number - long is the difference between Day 0 and D0
def get_phase_identifier(phase: int, long: bool = True):
    if long: return ("Night ", "Day ")[phase % 2] + str(phase // 2)
    return f"{'ND'[phase % 2]}{phase // 2}"



# gets a player object from any identifiable data
def get_player(data) -> Player | None:
    for player in all_players:

        if str(data).lower() in (
            str(player.IDENTIFIER),
            str(player.NICKNAME).lower(),
            str(player.DISCORD_ID),
            str(player.BOUND_CHANNEL)):
            
            return player



# logs a message
async def log(data: str):
    await bot.get_channel(ChannelIDs.log.value).send(data)



# permission overwrites for locking and unlocking channels
async def set_permissions(player: int = None, role: int = None, channel: int = None, category: bool = False, unlocked: bool | None = True) -> None:

    # the trifecta of permissions: True if we're unlocking, None to lock down
    overwrite = disnake.PermissionOverwrite(send_messages=unlocked, send_messages_in_threads=unlocked, create_public_threads=unlocked)

    # the specified role, and the channel we're looking for
    target = guild.get_role(role) if role else guild.get_member(player)
    discord_channel: disnake.TextChannel = bot.get_channel(channel)

    # set permissions for either the channel or the whole category
    if not category: await discord_channel.set_permissions(target=target, overwrite=overwrite)
    else: await discord_channel.category.set_permissions(target=target, overwrite=overwrite)



# filters the message to only categories we might need to deal with things
def category_filter(message: disnake.Message, strict: bool = False) -> bool:

    # return False if an admin is doing it just in case we need to (?)
    if message.author.guild_permissions.administrator: return False

    # first three categories have commands possible inside them, last two are only important for redirects
    accepts_commands = (
        "host",
        "crew",
        "weaponry"
    )
    redirects_possible = (
        "out",
        "engine"
    )

    # text to process, appropriately filtered
    category = message.channel.category.name.lower().strip().split()[0]

    # returns True unless we're:
    # in Host Only [Host] / Crew Quarters [player channels] / Weaponry Room [mafia]
    # in Out at Sea [dead] / Engine Rooms [dms] and strict is set to False
    return not (category in accepts_commands or (category in redirects_possible and not strict))



# updates the ship manifest
async def update_manifest() -> None:

    # finds the message to edit and replaces it with the player list
    message = await guild.get_channel(ChannelIDs.ship_manifest.value).fetch_message(PLAYER_LIST_MESSAGE_ID)
    playerlist = "\n".join(map(str, all_players))
    count = f"{len([i for i in all_players if i.ALIVE])}/{len(all_players)}"

    content = f"# List of All Players\n*(players struck through are dead)*\n\n{playerlist}\n\n**Living Players**: {count}\n​"
    await message.edit(content=content)



# reads in player data from the database
def save_players_to_database() -> int:

    # a UNIX timestamp as an integer - this is returned
    timestamp = int(datetime.now().timestamp())

    # for each player, insert all their data
    if all_players:
        database_players.insert_many([
            {
                "identifier": player.IDENTIFIER,
                "nickname": player.NICKNAME,
                "discord_id": player.DISCORD_ID,
                "bound_channel": player.BOUND_CHANNEL,
                "alive": player.ALIVE,
                "rolename": player.ROLENAME,
                "notes": player.NOTES.replace("no notes yet", ""),
                "log": player.LOG,
                "timestamp": timestamp
            }
            for player in all_players
        ])

    # writes the current data of the bot to a file so we can reload it on startup
    global CURRENT_PHASE, wiretaps

    with shelve.open("savestring") as db:
        db['CURRENT_PHASE'] = CURRENT_PHASE
        db['wiretaps'] = wiretaps
        db['timestamp'] = timestamp
        db['RUN_GAME_ON_LOOP'] = RUN_GAME_ON_LOOP
        db['private_channels'] = private_channels
        db['players_with_created_dms'] = players_with_created_dms
        db['wiretapped_players'] = wiretapped_players

    return timestamp



# reads the player data for all players from the database at a moment in time
def load_players_from_database(timestamp: int = 0):
    global all_players, CURRENT_PHASE, wiretaps, RUN_GAME_ON_LOOP, private_channels, players_with_created_dms, wiretapped_players

    # gets timestamp if none provided according to the savestring
    if not timestamp:
        with shelve.open("savestring") as db:
            CURRENT_PHASE = db['CURRENT_PHASE']
            wiretaps = db['wiretaps']
            timestamp = db['timestamp']
            RUN_GAME_ON_LOOP = db['RUN_GAME_ON_LOOP']
            private_channels = db['private_channels']
            players_with_created_dms = db['players_with_created_dms']
            wiretapped_players = db['wiretapped_players']


    # find all the players at the provided instant in time
    query = database_players.find({"timestamp": timestamp})
    
    # build a list of players based on the data points found in the query
    all_players = [
        Player(" | ".join((str(q[datapoint]) for datapoint in
        ("identifier", "nickname", "discord_id", "bound_channel", "alive", "rolename", "notes", "log"))))
        for q in query
    ]

    # sort this list into our standard order
    all_players = sorted(all_players, key = lambda x: identifier_sorting_key(x.IDENTIFIER))


 
# handles all redirects - deep sea microphone, wiretap receiver, and spy.
async def handle_redirects(message: disnake.Message):
    global wiretaps

    if message.channel.category.name.lower().split()[0] not in ("out", "engine"): return

    # dead chat -> mafia listener to dead chat and town listener to dead chat (anonymously)
    if message.channel.id == ChannelIDs.deep_ocean.value:
        await bot.get_channel(ChannelIDs.deep_sea_microphone.value).send(
            f"[Dead] {message.author.name}: {message.content}"
        )
        await bot.get_channel(ChannelIDs.hydrophone_receiver.value).send(
            f"{'[Dead] AK' if message.author.id == HOST_PLAYER_ID else '[Dead] Spirit'}: {message.content}"
        )

    # handle all custom wiretaps
    for wiretap in wiretaps:

        # anonymous vs named wiretaps
        name = "Anonymous" if wiretap.anonymous else message.author.name
        if message.channel.id == wiretap.source:
            await bot.get_channel(wiretap.destination).send(
                f"[{bot.get_channel(wiretap.source).name}] {name}: {message.content}"
            )



# repeats after you in case you want a message somewhere
@bot.command(name="say")
@commands.has_permissions(administrator=True)
async def say(ctx: commands.Context, channel: str, *text):
    if not text: return
    await guild.get_channel(int(channel[2:-1])).send(" ".join(text))



# repeats after you in case you want a message somewhere
@bot.command(name="add_emm_to_priv_channels")
@commands.has_permissions(administrator=True)
async def add_user_to_priv_channels(ctx: commands.Context, user: str):

    user_id = get_player(user).DISCORD_ID
    user = get_player(user).IDENTIFIER

    for channel_id in private_channels:
        for player in private_channels[channel_id]:
            identifier = player.IDENTIFIER if isinstance(player, Player) else player
            if identifier == user:
                await guild.get_channel(channel_id).set_permissions(target=guild.get_member(user_id), overwrite=disnake.PermissionOverwrite(view_channel=True))
                await ctx.send(f"Added {user} to <#{channel_id}>")


@bot.command(name="execute")
@commands.is_owner()
async def execute(ctx: commands.Context, *text):
    exec(" ".join(text))



# exports player data from current state
@bot.command(name="export")
@commands.has_permissions(administrator=True)
async def export_player_data(ctx: commands.Context):

    timestamp = save_players_to_database()
    await ctx.reply(f"Saved player data state with timestamp {timestamp}.")



# imports player data from a specified timestamp provided
@bot.command(name="import")
@commands.has_permissions(administrator=True)
async def import_player_data(ctx: commands.Context, timestamp: int):

    load_players_from_database(timestamp)
    await update_manifest()
    await ctx.reply(f"Loaded players from database with timestamp {timestamp}.")



# wipes all player data
@bot.command(name="deleteall")
@commands.has_permissions(administrator=True)
async def delete_player_data(ctx: commands.Context):

    # deletes every record in the database
    database_players.delete_many({})
    database_votes.delete_many({})
    database_actions.delete_many({})
    await ctx.reply(f"Deleted all data in the database!")



# allows us to change any player data
@bot.command(name="change_data")
@commands.has_permissions(administrator=True)
async def change_player_data(ctx: commands.Context, target: str, prop: int, *data):

    # gets the name of the attribute and what we're putting in it
    data = " ".join(data)
    attribute = "IDENTIFIER NICKNAME DISCORD_ID BOUND_CHANNEL ALIVE ROLENAME NOTES LOG".split()[prop]
    await ctx.reply(f"assigning {data} to {target} property {prop} (player.{attribute})")

    # actually sets the attribute, using the right data type
    get_player(target).__setattr__(attribute, (str, str, int, int, bool, str, str, str)[prop](data))
    await update_manifest()
    


# allows us to view any player data
@bot.command(name="view_player")
@commands.has_permissions(administrator=True)
async def view_player_command(ctx: commands.Context, identifier: str):

    # gets a player from the provided identifier
    player = get_player(identifier)
    if player is None:
        await ctx.send(f"No player by that identifier found!")
        return
    
    # replies with the found player data!
    await ctx.send(f"Found a player matching that identifier!\n\
                   `{player.IDENTIFIER}` (<@{player.DISCORD_ID}>)\n\
                   Rolename: {player.ROLENAME} ({'Town Mafia Neutral'.split()[alignment_by_role[player.ROLENAME.lower()]]})\n\
                   Player Channel: <#{player.BOUND_CHANNEL}>\n\
                   Alive: {player.ALIVE} (Notes: {player.NOTES})")



# allows us to view all actions
@bot.command(name="view_actions")
@commands.has_permissions(administrator=True)
async def view_actions_command(ctx: commands.Context, phase: int = -1):

    # default value is -1, use CURRENT_PHASE value if so
    if phase == -1: phase = CURRENT_PHASE

    # gets all actions fulfilling this
    all_actions = database_actions.find({"phase": phase})
    all_votes = database_votes.find({"phase": phase})

    await ctx.send("All votes:\n" + "\n".join([f"`{x['submitter']}` voted for `{x['target']}`" for x in all_votes]))
    await ctx.send("All actions:\n" + "\n".join([f"`{x['submitter']}` submitted action `{x['target']}`" for x in all_actions]))


# allows us to view global game data
@bot.command(name="view_global")
@commands.has_permissions(administrator=True)
async def view_global_command(ctx: commands.Context):
    await ctx.reply(f"All current data for the ongoing game (on autoplay: {RUN_GAME_ON_LOOP}):\n\
                    Phase {CURRENT_PHASE} ({get_phase_identifier(CURRENT_PHASE)})\n\
                    Wiretaps: {wiretaps} (WT'd players: {wiretapped_players})")
    await ctx.reply("Private Channels:\n" + "\n".join([f"{', '.join([f'`{participant.IDENTIFIER if isinstance(participant, Player) else participant}`' for participant in private_channels[channel_id]])}" for channel_id in private_channels]))
    await ctx.reply(f"DMs created: {players_with_created_dms}")
    

# records an instance of submitter voting for target in the database, given the identifier of both
def record_vote(submitter: str, target: str):

    # finds any previous votes the submitter has locked in the database for this phase (this returns None appropriately) 
    previous_vote = database_votes.find_one({
        "submitter": submitter,
        "phase": CURRENT_PHASE
        })

    # if there isn't a previous vote, insert a vote with the current data
    if previous_vote is None:
        database_votes.insert_one({
            "submitter": submitter,
            "target": target,
            "phase": CURRENT_PHASE,
            "time": datetime.now()
        })
        return
    
    # if there is, update the database entry accordingly (new target, updated time)
    database_votes.update_one(
        {
            "submitter": submitter,
            "phase": CURRENT_PHASE
        },
        {
            "$set": {"target": target},
            "$currentDate": {"time": True}
        }
    )



# records an instance of submitter voting for target in the database, given the identifier of both
def record_action(submitter: str, targets: str | list[str]):

    # joins up the list if needed
    if isinstance(targets, list):
        targets = " ".join(targets)

    # finds any previous actions the submitter has locked in the database for this phase (this returns None appropriately) 
    previous_action = database_actions.find_one({
        "submitter": submitter,
        "phase": CURRENT_PHASE
        })

    # if there isn't a previous action, insert an action with the current data
    if previous_action is None:
        database_actions.insert_one({
            "submitter": submitter,
            "target": targets,
            "phase": CURRENT_PHASE,
            "time": datetime.now()
        })
        return
    
    # if there is, update the database entry accordingly (new targets, updated time)
    database_actions.update_one(
        {
            "submitter": submitter,
            "phase": CURRENT_PHASE
        },
        {
            "$set": {"target": targets},
            "$currentDate": {"time": True}
        }
    )



# command to vote during the day
@bot.command(name="vote")
async def vote(ctx: commands.Context, *targets):

    # only player channel voting is allowed
    if ctx.channel.category.id != CategoryIDs.crew_quarters.value:
        await ctx.send("You can only vote in your player channel!")
        return
    
    # submitter is the player whose channel we're in, error stores what went wrong
    error: str = ""
    submitter: str = get_player(ctx.channel.id).IDENTIFIER

    # if we're trying to see the action
    if targets[0] in ("view", "plan"):
        previous_action = database_votes.find_one({
            "submitter": submitter,
            "phase": CURRENT_PHASE
        })
        await ctx.send("You haven't yet submitted a vote this phase!" if previous_action is None
                       else f"Your submitted vote: <@{get_player(previous_action['target']).DISCORD_ID}>")
        return
    
    # depending on what they provided as arguments, log an appropriate error / record the vote
    match targets:

        case _ if not get_player(submitter).ALIVE:                      # you have to be alive to vote
            error = f"You can't vote after you've died!"
        case []:                                                        # you have to provide an argument
            error = f"You need to provide a player to vote for!"

        case _ if not CURRENT_PHASE % 2:                                # phase must be 1 mod 2 (day)
            error = f"You can only vote during day phases!"
        case _ if CURRENT_PHASE == 1:                                   # but not 1 exactly (day 0)
            error = f"There's no lynch on Day 0!"

        case _ if datetime.now().hour == 21:                            # can't vote after 9pm
            error = f"Voting has now concluded!"

        case [_, *extra] if extra:                                      # can't provide multiple arguments
            error = f"You can only vote for 1 player, but you voted for {len(extra) + 1}!"

        case ["nobody"]:                                                # voting for "nobody": confirm, log, record
            await ctx.send(f"Successfully voted for nobody!")
            await log(f"{submitter} voted for nobody")
            record_vote(submitter, "nobody")
            return

        case ["abstain"]:                                               # voting for "nobody": confirm, log, record
            await ctx.send(f"Successfully removed your vote!")
            await log(f"{submitter} voted for abstain")
            record_vote(submitter, "abstain")
            return

        case [identifier] if (target := get_player(identifier)) is None:    # voting for an invalid target
            error = f"No player by that identifier was found - please use a code from #ship-manifest or a Discord ID, or use 'nobody' / 'abstain'."

        case _ if not target.ALIVE:                                     # can't vote for a dead player 
            error = f"You can't vote for a dead player!"

    # if there's an error, log it and quit
    if error:
        await ctx.send(error)
        return

    # records the vote in the database
    record_vote(submitter, target.IDENTIFIER)
    
    # if successful, log the vote and confirm it to the player
    await ctx.send(f"Successfully voted for <@{target.DISCORD_ID}>!")
    await log(f"{submitter} voted for {target.IDENTIFIER}")



# further validates a player's selection of target(s) for a night action
def validate_targets(submitter: Player, targets: list[str]):

    rolename = submitter.ROLENAME.lower().strip()

    # hacker check - this command is only for town and neutrals
    if alignment_by_role[rolename] == 1:
        return "The Hackers shouldn't be using this command - use >hacker instead!"

    # why are you using this command!
    if (rolename, ((CURRENT_PHASE % 2) == 0)) not in targetcount_by_role:
        return "It looks like you don't have an action targetting a player at this time. Does this seem wrong? Feel free to ping AK."

    targetcount, extra_arguments, can_self_target = targetcount_by_role[(rolename, ((CURRENT_PHASE % 2) == 0))]

    # you've provided the wrong number of targets
    if len(targets) != targetcount and not extra_arguments:
        return f"From your ability, this command expected {targetcount} target{'s' if targetcount != 1 else ''}, but received {len(targets)}. Is there a mistake here? Ping AK if so."

    # stores the list of targets as player names / "nobody"s
    cleaned_targets = []

    # are all of these targets valid - correct, alive, and (unless allowed) not yourself...
    for target in targets[:targetcount]:
        if (tp := get_player(target)) is None and target != "nobody":
            return f"Couldn't find player {target} - please use a code from #ship-manifest, a Discord ID, or the word \"nobody\"."
        if target != "nobody" and not tp.ALIVE:
            return f"Player {target} is dead and cannot be targeted."
        cleaned_targets.append("nobody" if target == "nobody" else f"<@{tp.DISCORD_ID}>")

    # self-targeting seems disallowed
    if f"<@{submitter.DISCORD_ID}>" in cleaned_targets and not can_self_target:
        return f"Acting on player(s): [{', '.join(cleaned_targets)}]\nNote that you are yourself included, which appears to not be allowed. Please check this!"
    
    # self-targeting seems allowed
    if f"<@{submitter.DISCORD_ID}>" in cleaned_targets and can_self_target:
        return f"Acting on player(s): [{', '.join(cleaned_targets)}]\nNote that you are yourself included, which appears to be allowed but may not be intended. Please check this!"

    # same target twice!
    if len(set(cleaned_targets)) != len(cleaned_targets):
        return f"Acting on player(s): [{', '.join(cleaned_targets)}]\nNote that you've chosen the same target multiple times, which may not be allowed. Please check this!"

    # success without self-targeting
    if f"<@{submitter.DISCORD_ID}>" not in cleaned_targets:
        return f"Acting on player(s): [{', '.join(cleaned_targets)}]"
        


# command to submit actions during the night
@bot.command(name="target")
async def target(ctx: commands.Context, *targets):

    # only player channel submission is allowed
    if ctx.channel.category.id != CategoryIDs.crew_quarters.value:
        await ctx.send("You can only submit actions in your player channel!")
        return
    
    # submitter is the player whose channel we're in, error stores what went wrong
    error: str = ""
    submitter: Player = get_player(ctx.channel.id).IDENTIFIER

    # if we're trying to see the action
    if targets[0] in ("view", "plan"):
        previous_action = database_actions.find_one({
            "submitter": submitter,
            "phase": CURRENT_PHASE
        })
        await ctx.send("You haven't yet submitted an action this phase!" if previous_action is None
                       else f"Your submitted action: {previous_action['target']}")
        return

    # strips the text
    targets = [t.strip() for t in targets]

    # depending on what they provided as arguments, log an appropriate error / record the vote
    match targets:
        case _ if not get_player(ctx.channel.id).ALIVE:
            error = f"You can't submit actions once you've died!"
        case []:
            error = f"You need to provide the player you're targeting!"
        case _:
            error = validate_targets(get_player(submitter), targets)

    # if there's an error, log it and quit
    if "Acting" not in error:
        await ctx.send(error)
        return

    # records the action in the database
    record_action(submitter, targets)
    
    # if successful, log the action and confirm it to the player
    await ctx.send(error)
    await log(f"{submitter} selected targets {targets}")



# command to submit actions during the night
@bot.command(name="message")
async def create_direct_message(ctx: commands.Context, target: str):

    # only player channel submission is allowed
    if ctx.channel.category.id != CategoryIDs.crew_quarters.value:
        await ctx.send("You can only create DMs from your player channel!")
        return
    
    # the player who is creating a DM
    submitter = get_player(ctx.channel.id)

    # no dead players!
    if not submitter.ALIVE:
        await ctx.send("You can't create DMs once you have died!")
        return
    
    # DMs can only be created during day phase.
    if not CURRENT_PHASE % 2:
        await ctx.send("You can only create DMs during the day phase.")
        return
    
    # you can only make one DM a day!
    if submitter.IDENTIFIER in players_with_created_dms[-1]:
        await ctx.send("You've already created your one allowed DM per day phase!")
        return
    
    # who are they trying to DM?
    target: Player = get_player(target)

    # that's not a valid target
    if target is None or target.IDENTIFIER == submitter.IDENTIFIER or not target.ALIVE:
        await ctx.send("That isn't a valid target: please pick a living player who isn't you.")
        return
    
    # logs it and makes the channel
    await log(f"{submitter.NICKNAME} created dm with {target.NICKNAME}")

    dms_category = bot.get_channel(ChannelIDs.engine_rooms.value).category

    await guild.create_text_channel(name=f"{get_phase_identifier(CURRENT_PHASE, False)}-{submitter.IDENTIFIER}-{target.IDENTIFIER}",
                                    overwrites={
                                        guild.get_member(target.DISCORD_ID): disnake.PermissionOverwrite(view_channel=True, send_messages=None),
                                        guild.get_member(submitter.DISCORD_ID): disnake.PermissionOverwrite(view_channel=True, send_messages=None),
                                        guild.get_role(RoleIDs.recruit.value): disnake.PermissionOverwrite(send_messages=True)
                                    },
                                    category=dms_category, topic=f"This DM was created by {submitter.IDENTIFIER} on {get_phase_identifier(CURRENT_PHASE)}.")
    
    channel_id = bot.get_channel(ChannelIDs.engine_rooms.value).category.channels[-1].id
    if target.IDENTIFIER in wiretapped_players or submitter.IDENTIFIER in wiretapped_players:
        wiretaps.append(ChannelWiretap(channel_id, ChannelIDs.wiretap_receiver.value, False))
    
    # logs the created dm in the master list
    players_with_created_dms[-1].append(submitter.IDENTIFIER)
    private_channels[channel_id] = [submitter, target]
    await ctx.send(f"Successfully created private channel <#{dms_category.channels[-1].id}> with <@{target.DISCORD_ID}>!")



# the main mafia command: >hacker *args
@bot.command(name="hacker")
async def hacker(ctx: commands.Context, subcommand: str, action_id: int | str = 0, actor: str = "", target: str = ""):
    
    # only usable in mafia chat!
    if ctx.channel.id != ChannelIDs.hackers.value: return

    # the ping case
    if subcommand == "ping":
        await ctx.send(f"<@&{RoleIDs.recruit.value}>")
        return

    # it's not the right phase for this
    if CURRENT_PHASE % 2 or not CURRENT_PHASE:
        await ctx.send("This command should only be used during the night.")
        return

    # only two subcommands
    if subcommand not in ("plan", "ability", "ping"):
        await ctx.send("Invalid command! The valid commands are `>hacker plan`, `>hacker ping` and `>hacker ability ...`.")
        return
    
    # the plan case
    if subcommand == "plan":

        # gets the previous action, assuming it exists
        previous_hacker_action = database_actions.find_one({"submitter": "hackers", "phase": CURRENT_PHASE})
        if previous_hacker_action is None or previous_hacker_action["target"] == "":
            await ctx.send("You haven't yet submitted any actions this phase!")
            return
        
        # replies with the current action plan
        response = f"## Hacker Action Plan - {get_phase_identifier(CURRENT_PHASE)}\n"
        for act in previous_hacker_action["target"].split("\n"):
            action_id, actor, target = act.split()
            response = response + "\n" + f"1. <@{get_player(actor).DISCORD_ID}> uses *{hacker_ability_names[int(action_id)]} [{int(action_id) + 1}]* on <@{get_player(target).DISCORD_ID}>"
        
        await ctx.send(response, allowed_mentions=disnake.AllowedMentions(replied_user=False, users=False))
        return


    # one of the provided players is not real
    if (actor := get_player(actor)) is None or (int(action_id) != 0 and (target := get_player(target)) is None):
        await ctx.send("Please make sure you use valid target IDs from #ship-manifest.")
        return
    
    # the successful case: the action says "stay home".
    if (action_id := int(action_id) - 1) < 0:
        await ctx.send(f"<@{actor.DISCORD_ID}> will not perform an action tonight.", allowed_mentions=disnake.AllowedMentions(replied_user=False, users=False))
        target = actor

    # one of those players isn't alive
    elif not (actor.ALIVE and target.ALIVE):
        await ctx.send("Please make sure you only choose living players.")
        return

    # you can't just make a random townie do this lol
    elif alignment_by_role[actor.ROLENAME.lower()] != 1:
        await ctx.send("Only mafia members can perform these abilities.")
        return

    # valid case: the action is an ability from 0-11 (down from 1-12)
    elif action_id in range(12):

        # these four abilities can't self-target
        if actor.IDENTIFIER == target.IDENTIFIER and action_id in (0, 1, 2, 5):
            await ctx.send(f"You can't target yourself with *{hacker_ability_names[action_id]}*.")
            return

        # these two abilities can't target other mafia
        elif alignment_by_role[target.ROLENAME.lower()] and action_id in (3, 6):
            await ctx.send(f"You can't target a mafia member with *{hacker_ability_names[action_id]}*.")
            return                
    
    # unsuccessful case of the action ID being invalid.
    else: await ctx.send(f"Action ID {action_id} is not valid. Please use a number between 1 and 12, or 0 to not perform an action.")

    # if this is the only submitted ability, this is easy
    previous_hacker_action = database_actions.find_one({"submitter": "hackers", "phase": CURRENT_PHASE})
    if previous_hacker_action is None:
        record_action("hackers", f"{action_id} {actor.IDENTIFIER} {target.IDENTIFIER}")

    # otherwise, we'll have to parse all of them.
    else:
        previous_hacker_action = previous_hacker_action["target"].split("\n")
        previous_hacker_action = [i for i in previous_hacker_action if i and i.split()[1] != actor.IDENTIFIER]

        # checking and stopping if we've re-used an ability
        if str(action_id) in [x.split(" ")[0] for x in previous_hacker_action]:
            await ctx.send("You've used that ability already - you can only use each ability once per night.")
            return
        
        # new ability usage
        if action_id >= 0:
            await ctx.send(f"<@{actor.DISCORD_ID}> will now use *{hacker_ability_names[action_id]}* on <@{target.DISCORD_ID}>.", allowed_mentions=disnake.AllowedMentions(replied_user=False, users=False))
        
        # records it in database
        previous_hacker_action.append(f"{action_id} {actor.IDENTIFIER} {target.IDENTIFIER}")
        record_action("hackers", "\n".join([i for i in previous_hacker_action if "-1" not in i]))
        

        
# manually runs distribute_messages
@bot.command(name="manual_distribute_messages")
@commands.has_permissions(administrator=True)
async def manual_distribute_messages(ctx: commands.Context):
    await log(f"Distributing messages based on manual trigger")
    await distribute_messages()
        

    
    


# distributes messages according to _messages.txt
async def distribute_messages():
    await log(f"Distributing messages for phase {CURRENT_PHASE}")
    
    # read in from text file input
    with open("_messages.txt") as f:
        messages = f.read().split("§")
        
    # for each message in the stack, separated by section character,
    for message in messages:

        # to save us getting hit by weird errors
        if "\n" not in message:
            continue

        # pull out and tidy up its recipient channel 
        target, content = message.split("\n", 1)
        target = target.lower().strip().split()[0]
        content = content.strip()

        # find the target channel based on target and content
        target_channel_id = 0
        recipient = None

        # ignore blank messages
        match target, content:
            case _, "": continue

            # sends to the specified channel names (with aliases)
            case "log", _:
                target_channel_id = ChannelIDs.log.value
            case ("main" | "black_box" | "announcements"), _:
                target_channel_id = ChannelIDs.black_box.value
            case ("waitlist" | "waitlisters" | "waitlist_chat"), _:
                target_channel_id = ChannelIDs.waitlist_chat.value
            case ("spec" | "specs" | "spectators" | "spectator_chat"), _:
                target_channel_id = ChannelIDs.spectator_chat.value
            case ("hackers" | "mafia"), _:
                target_channel_id = ChannelIDs.hackers.value

            # if it's a piece of player-identifying data, get the channel associated with that player
            case identifier, _:
                if (recipient := get_player(identifier)) is not None:
                    target_channel_id = recipient.BOUND_CHANNEL
                    content = content + f"\n\n<@{recipient.DISCORD_ID}>"

        # tidying up content
        for pattern in findall("%[a-zA-Z0-9_]+", content):
            if (pingable := get_player(pattern[1:].lower())) is not None:
                content = content.replace(pattern, f"<@{pingable.DISCORD_ID}>")
        content = content.replace("%recruit", f"<@&{RoleIDs.recruit.value}>")

        # actually send the message and pin it
        try:
            await bot.get_channel(target_channel_id).send(content)
            await bot.get_channel(target_channel_id).last_message.pin()
        except:
            await log(f"<@&{RoleIDs.host.value}> Error processing message {content}")

        # forward messages meant for hackers to the hacker results channel
        if recipient is not None and alignment_by_role[recipient.ROLENAME] == 1:
            await bot.get_channel(ChannelIDs.hacker_results.value).send(f"Results for <@{recipient.DISCORD_ID}>:\n\n" + content)



# handles deaths according to _deaths.txt
async def handle_deaths():
    await log(f"Handling deaths")

    # read in from text file input
    with open("_deaths.txt") as f:
        deaths = f.read().splitlines()
    deaths = [i for i in deaths if i and (not i.startswith("#"))]
    
    # for each death, get the player who died, what they died to (for the log), and their manifest notes
    for death in deaths:
        try:
            player, notes = death.split(maxsplit=1)
            player = get_player(player)

            # if they're already dead, there's no point
            if player is None or not player.ALIVE: continue

            # otherwise, set them to not-alive, and set their notes field for manifest 
            player.ALIVE = False
            player.NOTES = f"- {notes}, died {get_phase_identifier(CURRENT_PHASE - 1, False)}"

            # then log this
            await log(f"{player.NICKNAME} died: setting notes to `{player.NOTES}`")

            # add role Overboard // remove role Recruit
            member: disnake.Member = guild.get_member(player.DISCORD_ID)
            await member.add_roles(guild.get_role(RoleIDs.overboard.value))
            await member.remove_roles(guild.get_role(RoleIDs.recruit.value))
        
        # if something goes wrong while handing a death, log it
        except: await log(f"<@&{RoleIDs.host.value}> encountered error while handling death: {death}")

    # update the ship manifest to deal with the new roles
    await update_manifest()



# processes tasks according to _tasks.txt
async def process_tasks():
    await log(f"Processing tasks")

    # read in from text file input
    with open("_tasks.txt") as f:
        tasks = f.readlines()

    for task in tasks:
        try:
            await process_individual_task(task)
        except: await log(f"<@&{RoleIDs.host.value}> encountered error while handling task: {task}")

# process each of these
async def process_individual_task(task):
    
    global wiretaps, wiretapped_players
    match task.strip().split():

        # a comment or blank line - do nothing!
        case ["#", *_]: pass
        case ["§", *_]: pass
        case []: pass

        # marks the target for wiretapping
        case ["WIRETAP", target_id, "enable"]:
            await log(f"adding wiretap on {target_id}")
            wiretapped_players.append(get_player(target_id).IDENTIFIER)

        # unmarks the target for wiretapping
        case ["WIRETAP", target_id, "disable"]:
            await log(f"removing wiretap on {target_id}")
            wiretapped_players.remove(get_player(target_id).IDENTIFIER)

        # makes a night chat with the specified name and targets
        case ["MAKE-NIGHT-CHAT", channel_name, *targets]:
            await log(f"creating night chat: {targets}")
            main_category = bot.get_channel(ChannelIDs.engine_rooms.value).category    
            await guild.create_text_channel(name=channel_name, category=main_category,
                                    overwrites={
                                        guild.get_member(get_player(target).DISCORD_ID): disnake.PermissionOverwrite(view_channel=True)
                                        for target in targets
                                    })
            private_channels[main_category.channels[-1].id] = targets
            await bot.get_channel(main_category.channels[-1].id).set_permissions(guild.get_role(role_id=RoleIDs.recruit.value), overwrite=disnake.PermissionOverwrite(send_messages=True))
            if set([get_player(target).IDENTIFIER for target in targets]).intersection(set(wiretapped_players)):
                wiretaps.append(ChannelWiretap(main_category.channels[-1].id, ChannelIDs.wiretap_receiver.value, False))
            


# reminder before phasechange loop: runs every day at 6pm
async def reminder():

    await bot.wait_until_ready()

    # the reminder for end of phase approaching
    await log(f"Sending reminder for phase {CURRENT_PHASE}")
    message = ""

    match CURRENT_PHASE:
        case 0:
            return
        case 1:
            message = f"<@&{RoleIDs.recruit.value}> Night 1 is starting soon!"
        case phase if phase % 2:
            message = f"<@&{RoleIDs.recruit.value}> {get_phase_identifier(CURRENT_PHASE)} is ending in 3 hours! Remember to submit your votes using `>vote` in your player channel." 
        case phase if not phase % 2:
            message = f"<@&{RoleIDs.recruit.value}> {get_phase_identifier(CURRENT_PHASE)} is ending in 3 hours! Remember to submit your actions using `>target` in your player channel." 

    await bot.get_channel(ChannelIDs.black_box.value).send(message)



# end of night phase: runs every day at 9pm
async def night_end():

    await bot.wait_until_ready()

    # the reminder for end of phase approaching
    await log(f"Sending phasechange start warning for phase {CURRENT_PHASE}")
    if CURRENT_PHASE > 1 and not CURRENT_PHASE % 2:
        await bot.get_channel(ChannelIDs.black_box.value).send(f"{get_phase_identifier(CURRENT_PHASE)} has ended! All night results will be sent out and the game will resume in 1 hour. Channels are being locked now.")

    elif CURRENT_PHASE >= 1:
        await bot.get_channel(ChannelIDs.black_box.value).send(f"{get_phase_identifier(CURRENT_PHASE)} has ended! Day results will be posted and night will begin in 1 hour.")

    # lock all channels which shouldn't have night communications
    await set_permissions(role=RoleIDs.recruit.value, channel=ChannelIDs.port.value, unlocked=False)
    await set_permissions(role=RoleIDs.recruit.value, channel=ChannelIDs.starboard.value, unlocked=False)

    for channel in guild.get_channel(ChannelIDs.engine_rooms.value).category.channels:
        if channel.name.startswith(get_phase_identifier(CURRENT_PHASE, False).lower()):
            await set_permissions(role=RoleIDs.recruit.value, channel=channel.id, unlocked=False)




# end of phasechange loop: runs every day at 10pm
async def phasechange():

    await bot.wait_until_ready()

    # sets the global CURRENT_PHASE variable to the phase number
    # 1, 3, 5, 7 etc. are D0, D1, D2, D3... and 2, 4, 6, 8 etc. are N1, N2, N3, N4...
    global CURRENT_PHASE

    # actually sets the value
    await log(f"Changing phase from {get_phase_identifier(CURRENT_PHASE, False)} to {get_phase_identifier(CURRENT_PHASE + 1, False)}")
    CURRENT_PHASE += 1

    # distribute all necessary messages
    await distribute_messages()

    # handle relevant deaths
    await handle_deaths()

    # process tasks
    await process_tasks()

    # sends and pins a message announcing that a phase has started
    await bot.get_channel(ChannelIDs.port.value).send(f"Start of {get_phase_identifier(CURRENT_PHASE)}.")
    await bot.get_message(bot.get_channel(ChannelIDs.port.value).last_message_id).pin()

    # resets the list of players who have made a DM this phase
    players_with_created_dms.append([])

    # night phase!
    if not CURRENT_PHASE % 2:
            
        # ping players that the new phase has begun
        await bot.get_channel(ChannelIDs.black_box.value).send(f"<@&{RoleIDs.recruit.value}> {get_phase_identifier(CURRENT_PHASE)} has begun! Head to your player channels to submit your actions within the next 23 hours.")

    # day phase!
    else:

        # unlock all channels that can be unlocked
        await set_permissions(role=RoleIDs.recruit.value, channel=ChannelIDs.port.value, unlocked=True)
        await set_permissions(role=RoleIDs.recruit.value, channel=ChannelIDs.starboard.value, unlocked=True)

        # ping players
        if CURRENT_PHASE == 1:
            await bot.get_channel(ChannelIDs.black_box.value).send(f"<@&{RoleIDs.recruit.value}> The game has begun! Day 0 will last for 24 hours, during which <#{ChannelIDs.port.value}> is open for discussion.")
            return

        await bot.get_channel(ChannelIDs.black_box.value).send(f"<@&{RoleIDs.recruit.value}> {get_phase_identifier(CURRENT_PHASE)} has begun! <#{ChannelIDs.port.value}> is now open, and your night results are available in your player channels.")



# for all three loops, allows them to be run as commands as well as on schedule!

# loops at the correct times for each of the three:
@tasks.loop(time=times_reminder)
async def loop_helper_reminder():
    if RUN_GAME_ON_LOOP: await reminder()
    else: await log("time for reminder, but game looping is off. use `>manual_reminder` to run this!")

@tasks.loop(time=times_phasechange_start)
async def loop_helper_night_end():
    if RUN_GAME_ON_LOOP: await night_end()
    else: await log("time for night end, but game looping is off. use `>manual_night_end` to run this!")

@tasks.loop(time=times_phasechange_end)
async def loop_helper_phasechange():
    if RUN_GAME_ON_LOOP: await phasechange()
    else: await log("time for phase change, but game looping is off. use `>manual_phasechange` to run this!")


# allows each of the three to be run manually whenever
@bot.command(name="manual_reminder")
@commands.has_permissions(administrator=True)
async def manual_helper_reminder(ctx: commands.Context): await reminder()

@bot.command(name="manual_night_end")
@commands.has_permissions(administrator=True)
async def manual_helper_night_end(ctx: commands.Context): await night_end()

@bot.command(name="manual_phasechange")
@commands.has_permissions(administrator=True)
async def manual_helper_phasechange(ctx: commands.Context): await phasechange()


# do we want to run the game on a loop?
@bot.command(name="toggleloop")
@commands.has_permissions(administrator=True)
async def toggle_running_game_on_loop(ctx: commands.Context):

    # flips the value and confirms in chat
    global RUN_GAME_ON_LOOP
    RUN_GAME_ON_LOOP = not RUN_GAME_ON_LOOP
    await ctx.reply(f"Set automatic looping to {RUN_GAME_ON_LOOP}.")


# shows the help command
@bot.command(name="help")
async def display_help_command(ctx: commands.Context):

    if ctx.channel.category_id in (CategoryIDs.crew_quarters.value, CategoryIDs.weaponry_room.value):
        await ctx.send(help_command_text_global)
    if ctx.channel.category_id == CategoryIDs.weaponry_room.value:
        await ctx.send(help_command_text_hackers)
    if ctx.author.guild_permissions.administrator:
        await ctx.send(help_command_text_me)
    



# the main process which runs for every message on the server
@bot.event
async def on_message(message: disnake.Message):
    
    # step 1: do nothing if a bot sent the message
    if message.author.bot: return

    # step 2: do nothing if not in a category we might need to deal with at all
    if category_filter(message, strict=False): return

    # step 3: if the message needs to be redirected, do so
    await handle_redirects(message)

    # step 4: do nothing if not in a category we might need to deal with for commands
    if category_filter(message, strict=True): return

    # step 5: handle all commands in the message
    await bot.process_commands(message)



# startup sequence
@bot.event
async def on_ready():

    global all_players, wiretaps, RUN_GAME_ON_LOOP, CURRENT_PHASE

    # sets the bot's status
    await bot.change_presence(activity=disnake.Game(name="Rebooting..."))

    # do we run the game on an automatic loop, or are we just doing this manually?
    RUN_GAME_ON_LOOP = False

    load_players_from_database()

    # sets guild to the discord server, and removes the help command to avoid spoilers
    global guild
    guild = bot.get_guild(SERVER_ID)

    # if the current phase is an even number (night), turn off talking in port, otherwise allow it
    await set_permissions(role=RoleIDs.recruit.value, channel=ChannelIDs.port.value, unlocked=bool(CURRENT_PHASE%2))
    await set_permissions(role=RoleIDs.recruit.value, channel=ChannelIDs.starboard.value, unlocked=bool(CURRENT_PHASE%2))
    
    # updates the ship-manifest
    await update_manifest()
    await log("------- STARTUP SEQUENCE FINISHED: BOT RESTARTED -------")

    # sets the bot's status
    await bot.change_presence(activity=disnake.Game(name="Minr Mafia"))


# if administrator requests a shutdown, trigger it as normal
@bot.command(name="shutdown")
@commands.has_permissions(administrator=True)
async def shutdown(ctx: commands.Context):

    # raising a KeyboardInterrupt does the same thing as interrupting from console
    await ctx.reply(f"Disconnecting! Running quit process.")
    raise KeyboardInterrupt


# starts the loops
loop_helper_phasechange.start()
loop_helper_night_end.start()
loop_helper_reminder.start()

# runs the bot
try: bot.run("YOUR DISCORD TOKEN GOES HERE")

# exit / shutoff code
finally:

    print("\nShutting down bot!")

    timestamp = save_players_to_database()
    print(f"Saved player data state with timestamp {timestamp}.")

    print("Completed shutdown process, exiting program.")
