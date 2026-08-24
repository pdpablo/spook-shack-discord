import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)
bot = commands.Bot(command_prefix="!", intents=intents)
