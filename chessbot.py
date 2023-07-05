import os
import json
import re
import logging
from datetime import time, datetime,timedelta
from telegram import Update
from apscheduler.schedulers.background import BackgroundScheduler
from telegram.ext import Updater, CommandHandler, CallbackContext
from pytz import timezone, utc
import chess
import chess.svg
import pandas as pd
import cairosvg

with open('token.txt') as f:
    TOKEN = f.read().strip()

chat_puzzles = {}

def save_used_puzzles():
    with open("used_puzzles.json", "w") as f:
        json.dump(chat_puzzles, f)

def load_used_puzzles():
    try:
        with open("used_puzzles.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

chat_puzzles = load_used_puzzles()

# Read the top 1000 puzzles CSV file
puzzles = pd.read_csv("top_1000_puzzles.csv")
puzzles["posted"] = False


def escape_md_v2(text):
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return "".join([f"\\{char}" if char in escape_chars else char for char in text])

def get_first_move(fen, moves):
    board = chess.Board(fen)
    first_move_uci = moves.split()[0]
    first_move = chess.Move.from_uci(first_move_uci)
    return first_move

def generate_png(puzzle):
    board = chess.Board(puzzle['FEN'])
    file_name = f"puzzle_{puzzle['PuzzleId']}.png"

    # Apply the first move
    first_move = get_first_move(puzzle['FEN'], puzzle['Moves'])
    board.push(first_move)

    # Check if it's Black's turn
    if board.turn == chess.BLACK:
        svg = chess.svg.board(board=board, size=400, flipped=True)
    else:
        svg = chess.svg.board(board=board, size=400)

    with open(file_name, "w") as f:
        f.write(svg)

    png_path = file_name.replace(".svg", ".png")
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=png_path)
    return png_path

def escape_reserved_characters(san_move):
    reserved_characters = ['+', '*', '_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for character in reserved_characters:
        san_move = san_move.replace(character, '\\' + character)
    
    return san_move

def send_puzzle(update: Update, context: CallbackContext, puzzle, chat_id = None):

    chat_id = str(chat_id if chat_id else update.effective_chat.id)

    board = chess.Board(puzzle['FEN'])
    # ...
    if chat_id in chat_puzzles:
        chat_puzzles[chat_id]["puzzles"].append(puzzle['PuzzleId'])

    png_path = generate_png(puzzle)
    # Save the updated chat_puzzles dictionary to a file
    save_used_puzzles()
    # Determine who moves first
    fen_parts = puzzle['FEN'].split()
    first_move = 'White' if fen_parts[1] == 'b' else 'Black'

    # Determine the number of turns until mate
    turns_till_mate = 0
    if 'mateIn1' in puzzle['Themes']:
        turns_till_mate = 1
    elif 'mateIn2' in puzzle['Themes']:
        turns_till_mate = 2
    elif 'mateIn3' in puzzle['Themes']:
        turns_till_mate = 3

    # Solution under a spoiler
    moves = puzzle['Moves'].split(' ')
    spoiler_text = ""
    last_move = True
    for move in moves:
        if last_move:
            san_move = board.san(chess.Move.from_uci(move))
            board.push(chess.Move.from_uci(move))
            last_move = False
        else:
            san_move = board.san(chess.Move.from_uci(move))
            spoiler_text += san_move + " "
            board.push(chess.Move.from_uci(move))

    spoiler_text = escape_md_v2(spoiler_text)
    # Compose the caption
    caption = f"*{first_move} moves first, mate in {turns_till_mate}*\n"\
              f"*Solution:* ||{spoiler_text}||\n"\
              "*Puzzle URL:*" + escape_md_v2("https://lichess.org/training/" + f"{puzzle['PuzzleId']}") + "\n"

    with open(png_path, "rb") as f:
        context.bot.send_photo(chat_id, photo=f, caption=caption, parse_mode='MarkdownV2')
    os.remove(png_path)
    # Save the updated chat_puzzles dictionary to a file

# def today_puzzle(update: Update, context: CallbackContext):
#     chat_id = str(update.effective_chat.id)
#     if chat_id in chat_puzzles:
#         if chat_puzzles[chat_id]['puzzles']:
#             puzzle_id = chat_puzzles[chat_id]['puzzles'][-1]
#             puzzle = puzzles.loc[puzzles['PuzzleId'] == puzzle_id].iloc[0]
#             send_puzzle(update, context, puzzle)
#         else:
#             update.message.reply_text("There's no puzzle for today yet. Please wait for the daily puzzle or use the /random_puzzle command.")
#     else:
#         update.message.reply_text("This chat is not on the chat list. Please add it using /start_chess command first.")

    
def daily_puzzle(context: CallbackContext):
    global puzzles
    unposted_puzzles = puzzles.loc[puzzles["posted"] == False]
    if not unposted_puzzles.empty:
        puzzle = unposted_puzzles.sample(1).iloc[0]
        for chat_id in chat_puzzles:
            if chat_puzzles[chat_id]['daily']:  # Only send to chats with daily set to True
                send_puzzle(None, context, puzzle, chat_id)
        puzzles.at[puzzle.name, "posted"] = True
        save_used_puzzles()  # Save the updated chat_puzzles dictionary to a file



def parse_args(args):
    if not args:
        return None

    arg = args[0]
    if arg in ["1", "2", "3"]:
        return f"mateIn{arg}"
    else:
        return None
    
def random_puzzle(update: Update, context: CallbackContext):
    mate_type = parse_args(context.args)

    if mate_type:
        filtered_puzzles = puzzles[puzzles['Themes'].str.contains(mate_type)]
        if filtered_puzzles.empty:
            update.message.reply_text(f"No puzzles found for mate in {mate_type[-1]}.")
            return
    else:
        filtered_puzzles = puzzles


    puzzle = filtered_puzzles.sample(1).iloc[0]
    send_puzzle(update, context, puzzle)

def start_command(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    if chat_id not in chat_puzzles:
        chat_puzzles[chat_id] = {"puzzles": [], "daily": False}
        update.message.reply_text("This chat has been added to the list.")
        save_used_puzzles()  # Don't forget to save the updated list to a file
    else:
        update.message.reply_text("This chat is already on the list.")

def add_daily_command(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    if chat_id in chat_puzzles:
        if chat_puzzles[chat_id]["daily"]:
            update.message.reply_text("This chat is already on the daily puzzles list.")
        else:
            chat_puzzles[chat_id]["daily"] = True
            update.message.reply_text("This chat has been added to the daily puzzles list.")
        save_used_puzzles()
    else:
        update.message.reply_text("This chat is not on the chat list. Please add it using /start_chess command first.")

def remove_daily_command(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    if chat_id in chat_puzzles:
        chat_puzzles[chat_id]["daily"] = False
        update.message.reply_text("This chat has been removed from the daily puzzles list.")
        save_used_puzzles()
    else:
        update.message.reply_text("This chat is not on the chat list. Please add it using /start_chess command first.")

def help_command(update: Update, context: CallbackContext):
    help_text = (
        "This bot sends chess puzzles to solve with mate in 1,2,3 moves.\n Here are the available commands:\n"
        "\n"
        "/start_chess - Adds the chat to the chat list to keep track of used puzzles. Without that tracking used puzzles won't work.\n"
        "/add_daily — Adds posting daily puzzle. The puzzle is posted at 9am CEST.\n"
        "/remove_daily — Removes posting daily puzzle. Other commands are still available\n"
        "/random_puzzle - Sends a random puzzle\n"
        "/random_puzzle 1,2,3 - Specifies the number of moves till mate\n"
        "/today_puzzle - Shows today's puzzle\n"
        "/help_chess - Displays this help message\n"
        "\n"
        "A daily puzzle will be posted automatically at 9 AM every day.\n\n"
    )
    update.message.reply_text(help_text)

def start_scheduler(dp):
    scheduler = BackgroundScheduler()
    daily_puzzle_time = time(hour=10, minute=23)
    scheduler.add_job(lambda: daily_puzzle(CallbackContext.from_update(Update(0), dp)), 'cron', hour=daily_puzzle_time.hour, minute=daily_puzzle_time.minute)
    scheduler.start()


def main():
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Add command handlers
    dp.add_handler(CommandHandler("start_chess", start_command))
    dp.add_handler(CommandHandler("add_daily", add_daily_command))
    dp.add_handler(CommandHandler("remove_daily", remove_daily_command))

    dp.add_handler(CommandHandler("random_puzzle", random_puzzle))
    #dp.add_handler(CommandHandler("today_puzzle", today_puzzle))
    dp.add_handler(CommandHandler("daily_puzzle", daily_puzzle))
    dp.add_handler(CommandHandler("help_chess", help_command))

    start_scheduler(dp)    # # Schedule daily_puzzle job

    # Start the bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()

