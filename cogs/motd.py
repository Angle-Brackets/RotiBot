import random
from discord.ext import commands
from discord_slash import cog_ext, SlashContext
from replit import db
from profanity_check import predict_prob

#TODO: Add for the MOTD to be cycled every 3 hours.
def choose_motd(current_motd = None):
	keys = list(db.keys())

	#Removes current MOTD present on bot (prevents repeats) and blank MOTDs.
	#It's written this way because sets are unordered, meaning the list will be unordered, so this ignores order and just compares strings.
	for key in keys:
		if (current_motd is not None and db[key]["motd"] is current_motd) or not db[key]["motd"]:
			keys.remove(key)
	
	return db[random.choice(keys)]["motd"]
	

class Motd(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	motd_options = [
		{
			"name": "motd",
			"description": "A phrase to be displayed in Roti's status.",
			"required": True,
			"type": 3
		}
	]
	
	@cog_ext.cog_subcommand(base="motd", name="add", description="Add a \"Message of the Day\" to the bot to be displayed in its status", options=motd_options)
	async def _motd_add(self, ctx: SlashContext, motd = str):
		await ctx.defer()
		motd_entry = str(db[str(ctx.guild.id)]["motd"])
		profanity_level = predict_prob([motd])[0]

		if len(motd) > 128:
			await ctx.send(content="Failed to add given MEssage of the Day - Message exceeded max of 128 characters.")
		elif profanity_level <= 0.65:
			db[str(ctx.guild.id)]["motd"] = motd

			#If the motd database entry is empty for a server
			if motd_entry:
				await ctx.send(content="Successfully added new message of the day: \"{0}\"\n Overwrote previous entry: \"{1}\"".format(motd, motd_entry))
			else:
				await ctx.send(content="Successfully added new message of the day: \"{0}\"".format(motd))
		else:
			await ctx.send(content="Failed to add given Message of the Day - Detected Profanity.")
	
	@cog_ext.cog_subcommand(base="motd", name="clear", description="Removes the \"Message of the Day\" associated with this guild.")
	async def _motd_remove(self, ctx: SlashContext):
		await ctx.defer()
		motd_entry = db[str(ctx.guild.id)]["motd"]

		if motd_entry:
			db[str(ctx.guild.id)]["motd"] = ""
			await ctx.send(content="Successfully cleared MOTD associated with this guild: {0}".format(motd_entry))
		else:
			await ctx.send(content="There is no MOTD associated with this server currently, add one using /motd add!")
	
	@cog_ext.cog_subcommand(base="motd", name="show", description="Shows the \"Message of the Day\" associated with this guild.")
	async def _motd_show(self, ctx: SlashContext):
		await ctx.defer()
		if db[str(ctx.guild.id)]["motd"]:
			await ctx.send(content="The current MOTD associated with this server is: \"{0}\"".format(db[str(ctx.guild.id)]["motd"]))
		else:
			await ctx.send(content="There is no MOTD associated with this server currently, add one using /motd add!.")

def setup(bot):
	bot.add_cog(Motd(bot))
