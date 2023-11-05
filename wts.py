from player import Player

# represents a wiretap from one channel to another
class ChannelWiretap:

    # has a from, to, and whether the names are shown
    def __init__(self, source: int, destination: int, anonymous: bool) -> None:
        self.source = source
        self.destination = destination
        self.anonymous = anonymous

    # check if another wiretap is the same (only when all data is equal)
    def __eq__(self, __o: object) -> bool:
        if not isinstance(__o, ChannelWiretap): return False
        return (self.source == __o.source and self.destination == __o.destination and self.anonymous == __o.anonymous)
    
    # the exact data to reconstruct a wiretap with
    def __repr__(self) -> str:
        return f"WT(src={self.source})"
    
private_channels = {}
players_with_created_dms = [[]]
