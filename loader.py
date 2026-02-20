# loader.py
import telebot
from config import API_TOKEN

# Initialize Bot Instance
bot = telebot.TeleBot(API_TOKEN, threaded=True, num_threads=20)
