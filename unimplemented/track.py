import discord
import time

from discord.ext import commands
from discord import app_commands
from datetime import datetime
from data import db

#THIS IS NOT AN IMPLEMENTED COMMAND DUE TO ISSUES REGARDING FEASIBILITY WITH USER STATUSES BEING EXTREMELY INACCURATE.


ACTIVITY_TRACK_STRUCTURE = {
    "activity_name": str,
    "user_times": {} # Dictionary keyed by USER_ID and valued by time spent.
}

class Track(commands.GroupCog, group_name="track"):
    def __init__(self, bot : commands.Bot):
        super().__init__()
        self.bot = bot

    @app_commands.describe(activity="Name of the activity/game/program you would like to track.")
    @app_commands.command(name="activity", description="Tracks the time spent on a particular game/program by a user.")
    async def _track_activity(self, interaction : discord.Interaction, activity : str):
        await interaction.response.defer()
        for act in db["trackers"]["activities"]:
            if act.casefold() == activity.casefold():
                await interaction.followup.send("Duplicate activity detected! Try a different one.")
                return

        new_activity = ACTIVITY_TRACK_STRUCTURE.copy()
        new_activity["activity_name"] = activity
        # user times is not initialized yet, only when someone updates their status with that activity.

    #This only looks for PLAYING a game, unless it is spotify, then it will correctly detect spotify.
    #Should be on_presence_update
    @commands.Cog.listener()
    async def on_presence_update(self, before : discord.Member, after : discord.Member):
        print(before.activities)
        print(str(after.activities) + "\n\n")

        for a in before.activities:
            if a.type != discord.ActivityType.custom:
                print(a.name + ": " + str(time.time() - a.start.timestamp()))








async def setup(bot: commands.Bot):
    await bot.add_cog(Track(bot))