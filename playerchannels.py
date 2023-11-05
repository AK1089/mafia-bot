from disnake.ext import commands
import disnake
from datetime import datetime
import pymongo
from player import *
from serverdata import *
from random import randint
import shelve

# to connect to the database
database_client_connection = pymongo.MongoClient("mongodb+srv://Code:yjES0pSQ2uAHgaiK@minr-mafia.je9dmog.mongodb.net/?retryWrites=true&w=majority")["everything"]
database_players = database_client_connection["players"]

# all intents, help command gone to remove spoilers
bot: commands.Bot = commands.Bot(">", intents=disnake.Intents.all())
bot.remove_command("help")

# list of players and their discord IDs along with roles to give them
data = """
""".splitlines()

# the role descriptions!
with open("flavour.md") as f:
    role_descriptions = f.read().split("\n\n\n")

# self.IDENTIFIER: str = data[0]
# self.NICKNAME: str = data[1]
# self.DISCORD_ID: int = int(data[2])
# self.BOUND_CHANNEL: int = int(data[3])
# self.ALIVE: bool = (data[4].strip().lower() == "true")
# self.ROLENAME: str = data[5]
# self.NOTES: str = data[6].strip()
# self.LOG: str = data[7].strip()


all_players = []

# when the bot starts up, it's time to remake player channels
@bot.event
async def on_ready():

    await bot.change_presence(activity=disnake.Game(name="Setting Up Game"))

    # gets all the channels in category 6 (player channels)
    guild = bot.guilds[0]
    category = guild.categories[6]
    channels = category.channels

    # deletes them in turn
    for channel in channels:
        try: await channel.delete() 
        except AttributeError: pass


    await guild.get_channel(ChannelIDs.black_box.value).send(f"Player channels are now opening, and your roles will be sent out! <@&{RoleIDs.recruit.value}>")


    # gets all the channels in category 6 (player channels)
    dm_channels = guild.categories[7].channels[1:]

    # deletes them in turn
    for channel in dm_channels:
        try: await channel.delete() 
        except AttributeError: pass

    # overwrite for the player channel
    ovw_view = disnake.PermissionOverwrite(view_channel=True, send_messages=True, send_messages_in_threads=True, create_public_threads=True, manage_messages=True)

    player_strings = []

    # for each player 
    for d in data:
        player_identifier, player, discord_id, rolename = d.split(" ", 3)
        discord_id = int(discord_id)

        # gets a random three digit hex code
        # player_identifier = hex(randint(0, 4095))[2:].zfill(3)

        # make a private player channel that only they can see
        await guild.create_text_channel(name=f"{player_identifier}-{player}", category=category,
                                        topic=f"This is your private player channel, where information about your role, actions, and such goes. You can also ask questions here, as well as using various commands.",
                                        overwrites={guild.get_member(discord_id): ovw_view})

        # give the player the Recruit role
        member = guild.get_member(discord_id)
        await member.add_roles(guild.get_role(RoleIDs.recruit.value))
        await member.remove_roles(guild.get_role(RoleIDs.overboard.value))

        # make a player string for them
        player_strings.append(f"{player_identifier} | {player} | {discord_id} | $ | True | {rolename} |  | Log")
        
    # add the player object with the bound channel
    for ps, channel in zip(player_strings, category.channels):
        all_players.append(Player(ps.replace("$", str(channel.id))))

        await channel.send(f"Welcome to your player channel, <@{ps.split()[4]}>!")
        await channel.send(([i for i in role_descriptions if ps.split(" | ")[5] in i.lower()]+[f"error: missing role description for {ps.split(' | ')[5]}"])[0])

        if alignment_by_role[ps.split(' | ')[5]] == 1:
            await guild.get_channel(ChannelIDs.hackers.value).set_permissions(target=guild.get_member(int(ps.split(' | ')[2])), view_channel=True)
            await guild.get_channel(ChannelIDs.wiretap_receiver.value).set_permissions(target=guild.get_member(int(ps.split(' | ')[2])), view_channel=True)

        if ps.split(' | ')[5] == "interrogation specialist":
            await guild.get_channel(ChannelIDs.deep_sea_microphone.value).set_permissions(target=guild.get_member(int(ps.split(' | ')[2])), overwrite=ovw_view)
        if ps.split(' | ')[5] == "hydrophone manager":
            await guild.get_channel(ChannelIDs.hydrophone_receiver.value).set_permissions(target=guild.get_member(int(ps.split(' | ')[2])), overwrite=ovw_view)

        await bot.get_message(channel.last_message_id).pin()


    # finds the message to edit and replaces it with the player list
    message = await guild.get_channel(ChannelIDs.ship_manifest.value).fetch_message(1060605899661660250)
    playerlist = "\n".join(map(str, all_players))
    count = f"{len([i for i in all_players if i.ALIVE])}/{len(all_players)}"

    content = f"# List of All Players\n*(players struck through are dead)*\n\n{playerlist}\n\n**Living Players**: {count}\n​"
    await message.edit(content=content)

            
    save_players_to_database()
    quit()


# reads in player data from the database
def save_players_to_database() -> int:

    # a UNIX timestamp as an integer - this is returned
    timestamp = int(datetime.now().timestamp())

    # for each player, insert 
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

    database_players.update_one(
        {"latest": True},
        {"$set": {"time": timestamp}}
        )

    with shelve.open("savestring") as db:
        db['CURRENT_PHASE'] = 0
        db['wiretaps'] = []
        db['timestamp'] = timestamp
        db['RUN_GAME_ON_LOOP'] = 0
        db['private_channels'] = {}
        db['players_with_created_dms'] = []
        db['wiretapped_players'] = []

    print(f"Saved player data state with timestamp {timestamp}.")

bot.run("MTAzNDU0NzcwMTg0MjQ1MjU0MA.GMy80j.sh0mv7CK_fgmZ4XD-rq3LB0Xn4-YdYeYywNB5s")
