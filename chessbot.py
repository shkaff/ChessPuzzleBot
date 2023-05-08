import os
import json
import logging
from datetime import time
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

import chess
import chess.svg
import pandas as pd
import cairosvg

with open('token.txt') as f:
    TOKEN = f.readlines()

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


def send_puzzle(update: Update, context: CallbackContext, puzzle):

    chat_id = update.effective_chat.id
    # ...

    if chat_id not in chat_puzzles:
        chat_puzzles[chat_id] = []
    chat_puzzles[chat_id].append(puzzle['PuzzleId'])
    png_path = generate_png(puzzle)
    save_used_puzzles()

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
    moves = puzzle['Moves'].split()
    spoiler_text = f"|| {', '.join(moves)} ||"

    # Compose the caption
    caption = f"*{first_move} moves first, mate in {turns_till_mate}*\n"\
              f"*Solution:* {spoiler_text}\n"\
              "*Puzzle URL:*" + escape_md_v2("https://lichess.org/training/" + f"{puzzle['PuzzleId']}") + "\n"

    with open(png_path, "rb") as f:
        context.bot.send_photo(chat_id=update.effective_chat.id, photo=f, caption=caption, parse_mode='MarkdownV2')
    os.remove(png_path)
    # Save the updated chat_puzzles dictionary to a file

def today_puzzle(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    if chat_id in chat_puzzles and chat_puzzles[chat_id]:
        puzzle_id = chat_puzzles[chat_id][-1]
        puzzle = puzzles.loc[puzzles['PuzzleId'] == puzzle_id].iloc[0]
        send_puzzle(update, context, puzzle)
    else:
        update.message.reply_text("There's no puzzle for today yet. Please wait for the daily puzzle or use the /random command.")

def daily_puzzle(context: CallbackContext):
    global puzzles
    unposted_puzzles = puzzles.loc[puzzles["posted"] == False]
    if not unposted_puzzles.empty:
        puzzle = unposted_puzzles.iloc[0]
        send_puzzle(context.job.context, context, puzzle)
        puzzles.at[puzzle.name, "posted"] = True

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


def help_command(update: Update, context: CallbackContext):
    help_text = (
        "This bot sends chess puzzles to solve with mate in 1,2,3 moves.\n Here are the available commands:\n"
        "\n"
        "/random - Sends a random puzzle\n"
        "/random 1,2,3 - Specifies the number of moves till mate\n"
        "/today - Shows today's puzzle\n"
        "/help - Displays this help message\n"
        "\n"
        "A daily puzzle will be posted automatically at 9 AM every day."
    )
    update.message.reply_text(help_text)

def main():
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Add command handlers
    dp.add_handler(CommandHandler("random", random_puzzle))
    dp.add_handler(CommandHandler("today", today_puzzle))
    dp.add_handler(CommandHandler("help", help_command))

    

    # Schedule daily_puzzle job
    job_queue = updater.job_queue
    job_queue.run_daily(daily_puzzle, time(hour=9, minute=0), days=(0, 1, 2, 3, 4, 5, 6), context=dp)

    # Start the bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
