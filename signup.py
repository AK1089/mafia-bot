from disnake.ext import commands
import disnake
from serverdata import ChannelIDs, RoleIDs
from random import randint

# all intents, help command gone to remove spoilers
bot: commands.Bot = commands.Bot(">", intents=disnake.Intents.all(), help_command=None)


@bot.command(name="help")
async def help(ctx: commands.Context, *args):
    await ctx.reply("This command will become available when the game actually starts!")


data = """# List of All Players

**Players Signed Up**: 0/30
​"""

@bot.command(name="signup")
async def signup(ctx: commands.Context, identifier = ""):

    message = await guild.get_channel(ChannelIDs.ship_manifest.value).fetch_message(1060605899661660250)
    playerlist = message.content.split("\n\n")[1].split("\n")

    identifier = "".join([i for i in identifier.lower().strip() if i in "0123456789abcdef"])

    if str(ctx.author.id) in "".join(playerlist):
        await ctx.reply("You're already signed up!")
        return 

    if len(identifier) != 3:
        await ctx.reply("To sign up, you must pick a hex code. This can be three characters from 0-9 or a-f, eg. `7a4`. Use `>signup 7a4` with your code to become a Recruit!")
        return

    try: x = int(identifier, 16)
    except:
        await ctx.reply("This doesn't seem to be a valid code. Remember, you need three characters in `0123456789abcdef`.")
        return
    
    if f"`{identifier}`" in "".join(playerlist):
        await ctx.reply("That code is already taken!")
        return
    
    playerlist.append(f"`{identifier}` - <@{ctx.author.id}>")
    newtext = "\n".join(playerlist)
    
    content = f"# List of All Players\n\n{newtext}\n\n**Players Signed Up**: {newtext.count('` - ')}/30\n​"
    
    await ctx.reply(f"Congratulations on signing up, <@{ctx.author.id}>! You've been given the Recruit role, and added to <#{ChannelIDs.ship_manifest.value}>.")

    member = guild.get_member(ctx.author.id)
    await member.add_roles(guild.get_role(RoleIDs.recruit.value))

    await message.edit(content=content)
    await bot.change_presence(activity=disnake.Game(name=f"{newtext.count('` - ')} Signups!"))


# when the bot starts up, it's time to remake player channels
@bot.event
async def on_ready():

    global guild
    guild = bot.guilds[0]

    message = await guild.get_channel(ChannelIDs.ship_manifest.value).fetch_message(1060605899661660250)
    # await message.edit(content=data)
    playercount = message.content.split()[-2]

    await bot.change_presence(activity=disnake.Game(name=f"{playercount} Signups!"))
    



bot.run("TOKEN")
