# Player class, used to store all player data
class Player:

    # initialised with a datastring as found in playerdata.txt
    def __init__(self, data: str = "") -> None:

        # safety catch in case we want to create a blank object
        if not data: return

        # records attributes and converts to right type
        data: list = data.split(" | ", 8)

        self.IDENTIFIER: str = data[0]
        self.NICKNAME: str = data[1]
        self.DISCORD_ID: int = int(data[2])
        self.BOUND_CHANNEL: int = int(data[3])
        self.ALIVE: bool = (data[4].strip().lower() == "true")
        self.ROLENAME: str = data[5]
        self.NOTES: str = data[6].strip()
        self.LOG: str = data[7].strip()
    
    # represents a player object
    def __repr__(self) -> str:
        strikethrough = "" if self.ALIVE else "~~"
        return f"{strikethrough}`{self.IDENTIFIER}` - <@{self.DISCORD_ID}>{strikethrough} {self.NOTES}"


    # equals method - discord ID is unique
    def __eq__(self, __value) -> bool:
        return isinstance(__value, Player) and __value.DISCORD_ID == self.DISCORD_ID
    
    def __hash__(self) -> int:
        return self.DISCORD_ID