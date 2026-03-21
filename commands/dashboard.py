import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
import os
import logging
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import qrcode

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

from backend.supabase_client import (
    get_wallet,
    update_last_accessed,
    update_currency,
    update_pin,
    delete_wallet,
)
from backend.price_feed import get_prices, get_sol_balance, get_ltc_balance
from backend.security import verify_pin, hash_pin
from utils.checks import ensure_wallet


BRAND_COLOR = 0x5865F2
SUCCESS_COLOR = 0x57F287
ERROR_COLOR = 0xED4245
WARN_COLOR = 0xFEE75C
INFO_COLOR = 0x00B0F4

CARD_W, CARD_H = 900, 520

FONT_PATH = "assets/fonts/NotoSans-Regular.ttf"
FONT_BOLD_PATH = "assets/fonts/NotoSans-Bold.ttf"

CURRENCY_SYMBOLS = {"usd": "$", "gbp": "£", "eur": "€"}
CURRENCY_NAMES = {"usd": "USD ($)", "gbp": "GBP (£)", "eur": "EUR (€)"}

TIMEOUT = 60

_FONT_CACHE = {}

def get_system_font_path(bold: bool = False) -> str:

    if bold:
        paths = [
            "C:\\Windows\\Fonts\\ariblk.ttf", 
            "C:\\Windows\\Fonts\\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        paths = [
            "C:\\Windows\\Fonts\\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    
    for path in paths:
        if os.path.exists(path):
            return path
            
    logger.warning("No suitable system font found, will likely fallback to default.")
    return None

def load_cached_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    global _FONT_CACHE
    
    cache_key = (size, bold)
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]
        
    font_path = get_system_font_path(bold)
    
    if font_path:
        try:
            font = ImageFont.truetype(font_path, size)
            _FONT_CACHE[cache_key] = font
            return font
        except OSError as e:
            logger.warning(f"Could not load font from {font_path}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error when loading font: {e}", exc_info=True)
            
    logger.info("Falling back to default PIL font.")
    font = ImageFont.load_default()
    _FONT_CACHE[cache_key] = font
    return font

class PriceFeedException(Exception): pass

async def fetch_coin_history(coin_id: str) -> tuple:
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {
        "vs_currency": "usd",
        "days": "7",
        "interval": "daily"
    }
    
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        prices_data = data["prices"][-7:]
                        prices = [p[1] for p in prices_data]
                        timestamps = [p[0] for p in prices_data]
                        return (prices, timestamps) if prices else ([], [])
                    elif resp.status == 429:
                        logger.warning("Hit CoinGecko rate limit, dropping chart data for this render")
                        return ([], [])
                    else:
                        logger.warning(f"CoinGecko API returned status {resp.status} for {coin_id}")
                        
            except asyncio.TimeoutError:
                logger.warning(f"Timeout while fetching history for {coin_id} via aiohttp")
            except Exception as e:
                logger.error(f"Error fetching {coin_id} via aiohttp: {e}")
    except ImportError:
        logger.warning("aiohttp not installed, falling back to synchronous urllib request for price history!")
        import urllib.request
        import json
        query_str = "&".join([f"{k}={v}" for k, v in params.items()])
        full_url = f"{url}?{query_str}"
        req = urllib.request.Request(full_url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read())
                    prices_data = data["prices"][-7:]
                    prices = [p[1] for p in prices_data]
                    timestamps = [p[0] for p in prices_data]
                    return (prices, timestamps) if prices else ([], [])
        except urllib.error.URLError as e:
            logger.error(f"URLError fetching {coin_id} via urllib: {e.reason}")
        except Exception as e:
            logger.error(f"Unexpected error fetching {coin_id} via urllib: {e}", exc_info=True)
            
    return ([], [])

def render_comix_card_bg(draw, coords, radius=15, fill="white", outline="white", width=2):
    x0, y0, x1, y1 = coords
    r = radius
    
    for i in range(width):
        offset = i
        draw.arc([x0 + offset, y0 + offset, x0 + 2*r + offset, y0 + 2*r + offset], 180, 270, fill=outline, width=1)
        draw.arc([x1 - 2*r - offset, y0 + offset, x1 - offset, y0 + 2*r + offset], 270, 360, fill=outline, width=1)
        draw.arc([x1 - 2*r - offset, y1 - 2*r - offset, x1 - offset, y1 - offset], 0, 90, fill=outline, width=1)
        draw.arc([x0 + offset, y1 - 2*r - offset, x0 + 2*r + offset, y1 - offset], 90, 180, fill=outline, width=1)
    
    draw.rectangle([x0 + r, y0, x1 - r, y1], fill=fill)
    draw.rectangle([x0, y0 + r, x1, y1 - r], fill=fill)
    draw.chord([x0, y0, x0 + 2*r, y0 + 2*r], 180, 270, fill=fill)
    draw.chord([x1 - 2*r, y0, x1, y0 + 2*r], 270, 360, fill=fill)
    draw.chord([x1 - 2*r, y1 - 2*r, x1, y1], 0, 90, fill=fill)
    draw.chord([x0, y1 - 2*r, x0 + 2*r, y1], 90, 180, fill=fill)

def paint_premium_gradient(img: Image.Image, coords, color_top: tuple, color_bottom: tuple, radius: int = 15):
    x0, y0, x1, y1 = coords
    width = x1 - x0
    height = y1 - y0
    
    gradient = Image.new('RGBA', (width, height))
    pixels = gradient.load()
    
    for y in range(height):
        ratio = y / height
        r = int(color_top[0] * (1 - ratio) + color_bottom[0] * ratio)
        g = int(color_top[1] * (1 - ratio) + color_bottom[1] * ratio)
        b = int(color_top[2] * (1 - ratio) + color_bottom[2] * ratio)
        a = int(color_top[3] * (1 - ratio) + color_bottom[3] * ratio) if len(color_top) > 3 else 255
        
        for x in range(width):
            pixels[x, y] = (r, g, b, a)
    
    mask = Image.new('L', (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([(0, 0), (width - 1, height - 1)], radius=radius, fill=255)
    
    img.paste(gradient, (x0, y0), mask)

def draw_vip_text_mask(draw, img, position: tuple, text: str, font, color_top: tuple, color_bottom: tuple):
    x, y = position
    
    temp_size = 500
    temp_img = Image.new('RGBA', (temp_size, temp_size), (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp_img)
    temp_draw.text((50, 50), text, font=font, fill=(255, 255, 255, 255))
    
    bbox = temp_img.getbbox()
    if not bbox:
        return
    
    left, top, right, bottom = bbox
    text_width = right - left
    text_height = bottom - top
    
    if text_width <= 0 or text_height <= 0:
        return
    
    grad_img = Image.new('RGBA', (text_width, text_height), (0, 0, 0, 0))
    grad_pixels = grad_img.load()
    
    for py in range(text_height):
        ratio = py / text_height if text_height > 0 else 0
        r = int(color_top[0] * (1 - ratio) + color_bottom[0] * ratio)
        g = int(color_top[1] * (1 - ratio) + color_bottom[1] * ratio)
        b = int(color_top[2] * (1 - ratio) + color_bottom[2] * ratio)
        
        for px in range(text_width):
            grad_pixels[px, py] = (r, g, b, 255)
    
    text_mask = temp_img.crop(bbox).convert('L')
    
    img.paste(grad_img, (x, y), text_mask)

def make_cosmos_bg_for_user(width: int, height: int) -> Image.Image:
    import random
    import math
    
    img = Image.new("RGB", (width, height), "#0a0611")
    draw = ImageDraw.Draw(img, "RGBA")
    
    random.seed(42)
    
    for _ in range(400):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        size = random.randint(0, 2)
        color = (random.randint(150, 255), random.randint(150, 255), random.randint(100, 220), 255)
        draw.ellipse([x - size, y - size, x + size, y + size], fill=color)
    
    for _ in range(2):
        cx = random.randint(width // 4, 3 * width // 4)
        cy = random.randint(height // 4, 3 * height // 4)
        for size in range(100, 0, -15):
            alpha = int(80 * (1 - size / 100))
            for angle in range(0, 360, 15):
                px = int(cx + size * math.cos(math.radians(angle)))
                py = int(cy + size * math.sin(math.radians(angle)))
                draw.ellipse([px - 2, py - 2, px + 2, py + 2], 
                           fill=(100, 150, 200, alpha))
    
    return img

def render_market_activity_spline(price_history: list, timestamps: list, color: tuple) -> Image.Image:
    try:
        if len(price_history) < 2:
            price_history = [price_history[0]] * 7 if price_history else [0] * 7
            timestamps = list(range(7)) if not timestamps else timestamps
        
        CHART_canvas_w, CHART_canvas_h = 800, 220
        LEFT_MARGIN, RIGHT_MARGIN = 50, 30
        TOP_MARGIN, BOTTOM_MARGIN = 20, 50
        
        plot_width = CHART_canvas_w - LEFT_MARGIN - RIGHT_MARGIN
        plot_height = CHART_canvas_h - TOP_MARGIN - BOTTOM_MARGIN
        
        chart = Image.new("RGBA", (CHART_canvas_w, CHART_canvas_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(chart, 'RGBA')
        
        min_price = min(price_history)
        max_price = max(price_history)
        price_range = max_price - min_price if max_price != min_price else max_price * 0.1
        price_min = min_price - (price_range * 0.1)
        price_max = max_price + (price_range * 0.1)
        price_range_padded = price_max - price_min
        
        def price_to_y(price):
            ratio = (price - price_min) / price_range_padded if price_range_padded > 0 else 0.5
            return int(CHART_canvas_h - BOTTOM_MARGIN - ratio * plot_height)
        
        def index_to_x(idx):
            ratio = idx / (len(price_history) - 1) if len(price_history) > 1 else 0
            return int(LEFT_MARGIN + ratio * plot_width)
        
        num_y_lines = 4
        for i in range(num_y_lines + 1):
            y_ratio = 1 - (i / num_y_lines)
            y_pos = int(TOP_MARGIN + y_ratio * plot_height)
            price_val = price_min + (i / num_y_lines) * price_range_padded
            
            draw.line(
                [(LEFT_MARGIN, y_pos), (CHART_canvas_w - RIGHT_MARGIN, y_pos)],
                fill=(100, 100, 120, 80),
                width=1
            )
            
            label = f"${price_val:.0f}" if price_val >= 1 else f"${price_val:.2f}"
            draw.text((5, y_pos - 8), label, font=load_cached_font(9), fill=(150, 150, 170, 200))
        
        draw.line([(LEFT_MARGIN, TOP_MARGIN), (LEFT_MARGIN, CHART_canvas_h - BOTTOM_MARGIN)],
                  fill=(120, 140, 160, 180), width=2)
        draw.line([(LEFT_MARGIN, CHART_canvas_h - BOTTOM_MARGIN), (CHART_canvas_w - RIGHT_MARGIN, CHART_canvas_h - BOTTOM_MARGIN)],
                  fill=(120, 140, 160, 180), width=2)
        
        def calc_spline_points_math(p0, p1, p2, p3, t):
            t2 = t * t
            t3 = t2 * t
            return (0.5 * (2 * p1 + 
                          (-p0 + p2) * t + 
                          (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + 
                          (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
        
        smooth_points = []
        segments_per_interval = 30
        
        for i in range(len(price_history)):
            p0 = price_history[max(0, i - 1)]
            p1 = price_history[i]
            p2 = price_history[min(len(price_history) - 1, i + 1)]
            p3 = price_history[min(len(price_history) - 1, i + 2)]

            if i < len(price_history) - 1:
                for t in np.linspace(0, 1, segments_per_interval, endpoint=False):
                    y = calc_spline_points_math(p0, p1, p2, p3, t)
                    x = LEFT_MARGIN + ((i + t) / (len(price_history) - 1)) * plot_width
                    smooth_points.append((x, price_to_y(y)))
        
        smooth_points.append((index_to_x(len(price_history) - 1), price_to_y(price_history[-1])))
        
        if len(smooth_points) > 2:
            fill_points = [(pt[0], pt[1]) for pt in smooth_points]
            fill_points.append((CHART_canvas_w - RIGHT_MARGIN, CHART_canvas_h - BOTTOM_MARGIN))
            fill_points.append((LEFT_MARGIN, CHART_canvas_h - BOTTOM_MARGIN))
            draw.polygon(fill_points, fill=(*color[:3], 30))
        
        if len(smooth_points) > 1:
            for i in range(len(smooth_points) - 1):
                draw.line([smooth_points[i], smooth_points[i + 1]], fill=color, width=2)
        
        for i, price in enumerate(price_history):
            x = index_to_x(i)
            y = price_to_y(price)
            draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=color, outline=(255, 255, 255, 150), width=1)
        
        from datetime import datetime
        tick_indices = [0, len(price_history) // 2, len(price_history) - 1]
        for idx in tick_indices:
            x_pos = index_to_x(idx)
            
            if timestamps and len(timestamps) > idx and isinstance(timestamps[idx], (int, float)):
                ts = timestamps[idx]
                ts_int = int(ts // 1000) if ts > 10000000000 else int(ts)
                dt = datetime.fromtimestamp(ts_int)
                label = dt.strftime("%m/%d")
            else:
                label = f"D{idx + 1}"
            
            draw.line([(x_pos, CHART_canvas_h - BOTTOM_MARGIN), (x_pos, CHART_canvas_h - BOTTOM_MARGIN + 4)],
                     fill=(120, 140, 160, 180), width=1)
            draw.text((x_pos - 18, CHART_canvas_h - BOTTOM_MARGIN + 8), label, 
                     font=load_cached_font(9), fill=(150, 150, 170, 200))
        
        return chart
    except Exception:
        return Image.new("RGBA", (800, 220), (0, 0, 0, 0))

def build_dashboard_canvas(
    username_display: str,
    sol_balance_actual: float,
    ltc_balance_actual: float,
    market_prices: dict,
    user_currency_pref: str,
    sol_hist_data: list = None,
    ltc_hist_data: list = None,
    sol_timestamps: list = None,
    ltc_timestamps: list = None,
) -> io.BytesIO:
    pref = user_currency_pref.lower()
    cur = user_currency_pref.lower() 
    sol_price = market_prices["sol"][pref]
    ltc_price = market_prices["ltc"][pref]
    sol_fiat = sol_balance_actual * sol_price
    ltc_fiat = ltc_balance_actual * ltc_price
    total = sol_fiat + ltc_fiat
    symbol = CURRENCY_SYMBOLS.get(cur, "$")
    
    if not sol_hist_data or len(sol_hist_data) < 2:
        sol_hist_data = [sol_price * (0.95 + 0.1 * (i / 6)) for i in range(7)]
    if not ltc_hist_data or len(ltc_hist_data) < 2:
        ltc_hist_data = [ltc_price * (0.95 + 0.1 * (i / 6)) for i in range(7)]
    
    canvas_w = 1800
    canvas_h = 100 
    outer_pad = 40
    inner_wiget_pad = 36
    corner_rad = 24
    
    base_img = make_cosmos_bg_for_user(canvas_w, canvas_h)
    img = base_img.convert("RGBA")
    draw = ImageDraw.Draw(img)
    
    WIDGET_TOP = 105
    WIDGET_canvas_w = (canvas_w - (3 * outer_pad)) // 2
    WIDGET_canvas_h = 520
    sol_widget_x = outer_pad
    ltc_widget_x = outer_pad + WIDGET_canvas_w + outer_pad
    
    render_comix_card_bg(
        draw,
        [sol_widget_x, WIDGET_TOP, sol_widget_x + WIDGET_canvas_w, WIDGET_TOP + WIDGET_canvas_h],
        radius=corner_rad,
        fill=(22, 37, 77, 240),
        outline=(0, 217, 255, 200),
        width=3
    )
    draw.text(
        (sol_widget_x + inner_wiget_pad, WIDGET_TOP + 20),
        "Solana",
        font=load_cached_font(32, bold=True),
        fill=(0, 217, 255, 255)
    )
    balance_text = f"{sol_balance_actual:.4f}"
    draw_vip_text_mask(draw, img, (sol_widget_x + inner_wiget_pad, WIDGET_TOP + 79), balance_text, load_cached_font(70, bold=True), (0, 217, 255, 255), (0, 150, 200, 255))
    draw.text(
        (sol_widget_x + inner_wiget_pad, WIDGET_TOP + 145),
        "SOL",
        font=load_cached_font(18),
        fill=(144, 238, 144, 255)
    )
    draw.text(
        (sol_widget_x + inner_wiget_pad, WIDGET_TOP + 180),
        f"Value: {symbol}{sol_fiat:,.2f}",
        font=load_cached_font(20),
        fill=(144, 238, 144, 255)
    )
    draw.text(
        (sol_widget_x + inner_wiget_pad, WIDGET_TOP + 216),
        f"Price: {symbol}{sol_price:,.2f}",
        font=load_cached_font(18),
        fill=(218, 165, 32, 255)
    )
    
    sol_pct = ((sol_hist_data[-1] - sol_hist_data[0]) / sol_hist_data[0] * 100) if sol_hist_data[0] > 0 else 0
    pct_color = (96, 187, 107, 255) if sol_pct >= 0 else (255, 107, 107, 255)
    pct_text = f"7d: {sol_pct:+.1f}%"
    draw.text(
        (sol_widget_x + inner_wiget_pad, WIDGET_TOP + 250),
        pct_text,
        font=load_cached_font(18),
        fill=pct_color
    )
    
    sol_chart = render_market_activity_spline(sol_hist_data, sol_timestamps or [], (0, 217, 255, 220))
    sol_chart_resized = sol_chart.resize((WIDGET_canvas_w - 72, 240))
    img.paste(sol_chart_resized, (sol_widget_x + inner_wiget_pad, WIDGET_TOP + 270), sol_chart_resized)
    
    render_comix_card_bg(
        draw,
        [ltc_widget_x, WIDGET_TOP, ltc_widget_x + WIDGET_canvas_w, WIDGET_TOP + WIDGET_canvas_h],
        radius=corner_rad,
        fill=(45, 26, 10, 240),
        outline=(255, 152, 0, 200),
        width=3
    )
    draw.text(
        (ltc_widget_x + inner_wiget_pad, WIDGET_TOP + 20),
        "Litecoin",
        font=load_cached_font(32, bold=True),
        fill=(255, 152, 0, 255)
    )
    balance_text = f"{ltc_balance_actual:.4f}"
    draw_vip_text_mask(draw, img, (ltc_widget_x + inner_wiget_pad, WIDGET_TOP + 79), balance_text, load_cached_font(70, bold=True), (255, 152, 0, 255), (200, 100, 0, 255))
    draw.text(
        (ltc_widget_x + inner_wiget_pad, WIDGET_TOP + 145),
        "LTC",
        font=load_cached_font(18),
        fill=(144, 238, 144, 255)
    )
    draw.text(
        (ltc_widget_x + inner_wiget_pad, WIDGET_TOP + 180),
        f"Value: {symbol}{ltc_fiat:,.2f}",
        font=load_cached_font(20),
        fill=(144, 238, 144, 255)
    )
    draw.text(
        (ltc_widget_x + inner_wiget_pad, WIDGET_TOP + 216),
        f"Price: {symbol}{ltc_price:,.2f}",
        font=load_cached_font(18),
        fill=(218, 165, 32, 255)
    )
    
    ltc_pct = ((ltc_hist_data[-1] - ltc_hist_data[0]) / ltc_hist_data[0] * 100) if ltc_hist_data[0] > 0 else 0
    pct_color = (96, 187, 107, 255) if ltc_pct >= 0 else (255, 107, 107, 255)
    pct_text = f"7d: {ltc_pct:+.1f}%"
    draw.text(
        (ltc_widget_x + inner_wiget_pad, WIDGET_TOP + 250),
        pct_text,
        font=load_cached_font(18),
        fill=pct_color
    )
    
    ltc_chart = render_market_activity_spline(ltc_hist_data, ltc_timestamps or [], (255, 152, 0, 220))
    ltc_chart_resized = ltc_chart.resize((WIDGET_canvas_w - 72, 240))
    img.paste(ltc_chart_resized, (ltc_widget_x + inner_wiget_pad, WIDGET_TOP + 270), ltc_chart_resized)
    
    BALANCE_TOP = WIDGET_TOP + WIDGET_canvas_h + 36
    BALANCE_canvas_w = 700
    BALANCE_X = (canvas_w - BALANCE_canvas_w) // 2
    BALANCE_canvas_h = canvas_h - BALANCE_TOP - outer_pad
    
    render_comix_card_bg(
        draw,
        [BALANCE_X, BALANCE_TOP, BALANCE_X + BALANCE_canvas_w, BALANCE_TOP + BALANCE_canvas_h],
        radius=corner_rad,
        fill=(15, 20, 40, 240),
        outline=(74, 95, 127, 200),
        width=2
    )
    
    draw.text(
        (BALANCE_X + 30, BALANCE_TOP + 28),
        "Total Portfolio Value",
        font=load_cached_font(26, bold=True),
        fill=(255, 255, 255, 255)
    )
    
    total_text = f"{symbol}{total:,.2f}"
    draw_vip_text_mask(draw, img, (BALANCE_X + 30, BALANCE_TOP + 79), total_text, load_cached_font(64, bold=True), (0, 255, 136, 255), (0, 200, 100, 255))
    
    draw.text(
        (BALANCE_X + 30, BALANCE_TOP + 145),
        f"SOL: {symbol}{sol_fiat:,.2f}  •  LTC: {symbol}{ltc_fiat:,.2f}",
        font=load_cached_font(18),
        fill=(176, 196, 222, 255)
    )
    
    final_img = img.convert("RGB")
    buf = io.BytesIO()
    final_img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def make_deposit_qr_png(address: str, coin: str) -> io.BytesIO:
    action_qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=9,
        border=3,
    )
    action_qr.add_data(address)
    action_qr.make(fit=True)
    qr_img = action_qr.make_image(fill_color="#a78bfa", back_color="#0a0a1a").convert("RGBA")

    w, h = qr_img.size
    canvas = Image.new("RGBA", (w + 40, h + 56), "#0d0d2b")
    canvas.paste(qr_img, (20, 16))
    ImageDraw.Draw(canvas).text((20, h + 26), f"{coin} Deposit Address", font=load_cached_font(12), fill="#64748b")

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    return buf

class CoinPickerView(discord.ui.View):
    def __init__(self, on_pick):
        super().__init__(timeout=TIMEOUT)
        self.on_pick = on_pick

    @discord.ui.button(label="Solana (SOL)", style=discord.ButtonStyle.primary)
    async def sol(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            self.stop()
            await self.on_pick(interaction, "SOL")
        except Exception as e:
            logger.exception(f"Exception triggered in button interaction: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Something went wrong processing your request.", ephemeral=True)

    @discord.ui.button(label="Litecoin (LTC)", style=discord.ButtonStyle.secondary)
    async def ltc(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            self.stop()
            await self.on_pick(interaction, "LTC")
        except Exception as e:
            logger.exception(f"Exception triggered in button interaction: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Something went wrong processing your request.", ephemeral=True)

class SendPickerView(discord.ui.View):
    def __init__(self, wallet: dict, prices: dict):
        super().__init__(timeout=TIMEOUT)
        self.wallet = wallet
        self.prices = prices

    @discord.ui.button(label="Solana (SOL)", style=discord.ButtonStyle.primary)
    async def send_solana(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            self.stop()
            await interaction.response.send_modal(SendCryptoModal("SOL", self.wallet, self.prices))
        except Exception as e:
            logger.exception(f"Exception triggered in button interaction: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Something went wrong processing your request.", ephemeral=True)

    @discord.ui.button(label="Litecoin (LTC)", style=discord.ButtonStyle.secondary)
    async def send_litecoin(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            self.stop()
            await interaction.response.send_modal(SendCryptoModal("LTC", self.wallet, self.prices))
        except Exception as e:
            logger.exception(f"Exception triggered in button interaction: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Something went wrong processing your request.", ephemeral=True)


class SendCryptoModal(discord.ui.Modal):
    def __init__(self, coin: str, wallet: dict, prices: dict):
        super().__init__(title=f"Send {coin}")
        self.coin = coin
        self.wallet = wallet
        self.prices = prices

        cur = wallet.get("currency", "usd")
        symbol = CURRENCY_SYMBOLS.get(cur, "$")
        self.address = discord.ui.TextInput(
            label="Recipient Address",
            placeholder="Paste the destination wallet address",
            min_length=20,
            max_length=110,
        )
        self.amount = discord.ui.TextInput(
            label=f"Amount ({symbol})",
            placeholder=f"e.g. 25.00",
            min_length=1,
            max_length=20,
        )
        self.pin = discord.ui.TextInput(
            label="Your PIN",
            placeholder="Enter your PIN to authorize",
            min_length=4,
            max_length=6,
        )
        self.add_item(self.address)
        self.add_item(self.amount)
        self.add_item(self.pin)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if not verify_pin(self.pin.value.strip(), self.wallet["pin_hash"]):
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Wrong PIN",
                    description="That PIN is incorrect. Transaction cancelled.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        raw = self.amount.value.strip().lstrip("$£€").strip()
        try:
            fiat_amount = float(raw)
            if fiat_amount <= 0:
                raise ValueError
        except ValueError:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Invalid Amount",
                    description=f"`{self.amount.value}` is not a valid number. Enter something like `25.00`.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        cur = self.wallet.get("currency", "usd")
        coin_key = "sol" if self.coin == "SOL" else "ltc"
        price = self.prices[coin_key][cur]

        if price <= 0:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Price Unavailable",
                    description="Could not get the current price. Please try again in a moment.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        crypto_amount = fiat_amount / price
        symbol = CURRENCY_SYMBOLS.get(cur, "$")
        recipient = self.address.value.strip()

        if self.coin == "SOL" and len(recipient) < 32:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Invalid SOL Address",
                    description="That does not look like a valid Solana address. It should be around 44 characters.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        if self.coin == "LTC":
            if not (recipient.startswith("L") or recipient.startswith("M") or recipient.startswith("ltc1")):
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="Invalid LTC Address",
                        description="Litecoin addresses start with L, M, or ltc1. Double check the address.",
                        color=ERROR_COLOR,
                    ),
                    ephemeral=True,
                )
                return

        await interaction.followup.send(
            embed=discord.Embed(
                title="Confirm Transaction",
                description=(
                    f"**Sending:** {crypto_amount:.6f} {self.coin}\n"
                    f"**Value:** {symbol}{fiat_amount:,.2f}\n"
                    f"**To:** `{recipient}`\n\n"
                    "Crypto transactions cannot be reversed. Make sure the address is correct."
                ),
                color=WARN_COLOR,
            ),
            view=SendConfirmView(
                coin=self.coin,
                recipient=recipient,
                crypto_amount=crypto_amount,
                fiat_amount=fiat_amount,
                symbol=symbol,
                wallet=self.wallet,
            ),
            ephemeral=True,
        )


class SendConfirmView(discord.ui.View):
    def __init__(self, coin, recipient, crypto_amount, fiat_amount, symbol, wallet):
        super().__init__(timeout=30)
        self.coin = coin
        self.recipient = recipient
        self.crypto_amount = crypto_amount
        self.fiat_amount = fiat_amount
        self.symbol = symbol
        self.wallet = wallet

    @discord.ui.button(label="Confirm Send", style=discord.ButtonStyle.danger)
    async def ok(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.defer(ephemeral=True)

        await interaction.followup.send(
            embed=discord.Embed(
                title="Send Queued",
                description=(
                    f"**{self.crypto_amount:.6f} {self.coin}** ({self.symbol}{self.fiat_amount:,.2f})\n"
                    f"To: `{self.recipient}`\n\n"
                    "On-chain broadcasting is coming in the next update. "
                    "The private key is decrypted and ready to sign."
                ),
                color=INFO_COLOR,
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.send_message(
            embed=discord.Embed(
                title="Transaction Cancelled",
                description="No funds were sent.",
                color=ERROR_COLOR,
            ),
            ephemeral=True,
        )

class ResetPinModal(discord.ui.Modal, title="Reset Your PIN"):
    cur = discord.ui.TextInput(
        label="Current PIN",
        placeholder="Your existing PIN",
        min_length=4,
        max_length=6,
    )
    new = discord.ui.TextInput(
        label="New PIN",
        placeholder="4 to 6 digit PIN",
        min_length=4,
        max_length=6,
    )
    conf = discord.ui.TextInput(
        label="Confirm New PIN",
        placeholder="Type your new PIN again",
        min_length=4,
        max_length=6,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        wallet = await get_wallet(str(interaction.user.id))
        if not wallet:
            await interaction.followup.send(
                embed=discord.Embed(title="Wallet not found", color=ERROR_COLOR),
                ephemeral=True,
            )
            return
        if not verify_pin(self.cur.value.strip(), wallet["pin_hash"]):
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Wrong PIN",
                    description="Your current PIN is incorrect.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        if not self.new.value.strip().isdigit():
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Invalid PIN",
                    description="Your new PIN must only contain numbers.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        if self.new.value.strip() != self.conf.value.strip():
            await interaction.followup.send(
                embed=discord.Embed(
                    title="PINs Do Not Match",
                    description="The new PIN and confirmation do not match. Try again.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        await update_pin(str(interaction.user.id), hash_pin(self.new.value.strip()))

        await interaction.followup.send(
            embed=discord.Embed(
                title="PIN Updated",
                description="Your PIN has been changed successfully.",
                color=SUCCESS_COLOR,
            ),
            ephemeral=True,
        )

class DeleteConfirmView(discord.ui.View):
    def __init__(self, user_id: str):
        super().__init__(timeout=30)
        self.user_id = user_id

    @discord.ui.button(label="Yes, delete my wallet", style=discord.ButtonStyle.danger)
    async def ok_del(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.defer(ephemeral=True)
        try:
            await delete_wallet(self.user_id)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Wallet Deleted",
                    description=(
                        "Your wallet has been permanently removed from Comix.\n\n"
                        "Your funds are still on the blockchain. As long as you have your "
                        "seed phrase, you can recover them in any compatible wallet app."
                    ),
                    color=SUCCESS_COLOR,
                ),
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Something went wrong",
                    description=f"Could not delete wallet: {e}",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def no_del(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.send_message(
            embed=discord.Embed(
                title="Cancelled",
                description="Your wallet is safe. Nothing was deleted.",
                color=INFO_COLOR,
            ),
            ephemeral=True,
        )

class SettingsView(discord.ui.View):
    def __init__(self, user_id: str):
        super().__init__(timeout=TIMEOUT)
        self.user_id = user_id

    @discord.ui.select(
        placeholder="Change display currency...",
        options=[
            discord.SelectOption(label="USD - US Dollar", value="usd"),
            discord.SelectOption(label="GBP - British Pound", value="gbp"),
            discord.SelectOption(label="EUR - Euro", value="eur"),
        ],
    )
    async def cur(self, interaction: discord.Interaction, select: discord.ui.Select):
        chosen = select.values[0]
        await interaction.response.defer(ephemeral=True)
        try:
            await update_currency(self.user_id, chosen)
            name = CURRENCY_NAMES[chosen]
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Currency Updated",
                    description=f"Your display currency is now **{name}**. Run `/dashboard` again to see it.",
                    color=SUCCESS_COLOR,
                ),
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(
                embed=discord.Embed(title="Failed to update currency", description=str(e), color=ERROR_COLOR),
                ephemeral=True,
            )

    @discord.ui.button(label="Reset PIN", style=discord.ButtonStyle.secondary, row=1)
    async def reset_pin(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ResetPinModal())

    @discord.ui.button(label="Delete Wallet", style=discord.ButtonStyle.danger, row=1)
    async def delete_wallet(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=discord.Embed(
                title="Are you sure you want to delete your wallet?",
                description=(
                    "This permanently removes your wallet from Comix.\n\n"
                    "Your funds stay on the blockchain. You can still recover them "
                    "with your 12-word seed phrase in any compatible app.\n\n"
                    "This action cannot be undone."
                ),
                color=WARN_COLOR,
            ),
            view=DeleteConfirmView(self.user_id),
            ephemeral=True,
        )

class DashboardView(discord.ui.View):
    def __init__(self, wallet: dict, prices: dict):
        super().__init__(timeout=180)
        self.wallet = wallet
        self.prices = prices

    @discord.ui.button(label="Send", style=discord.ButtonStyle.primary, row=0)
    async def action_send(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Send Crypto",
                    description="Which currency would you like to send?",
                    color=BRAND_COLOR,
                ),
                view=SendPickerView(self.wallet, self.prices),
                ephemeral=True,
            )
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            except Exception:
                pass

    @discord.ui.button(label="Receive", style=discord.ButtonStyle.secondary, row=0)
    async def action_receive(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            async def addr(inter: discord.Interaction, coin: str):
                try:
                    a = self.wallet["sol_address"] if coin == "SOL" else self.wallet["ltc_address"]
                    await inter.followup.send(
                        embed=discord.Embed(
                            title=f"Your {coin} Deposit Address",
                            description=(
                                f"`{a}`\n\n"
                                f"Only send **{coin}** to this address. "
                                "Sending any other coin will result in permanent loss."
                            ),
                            color=INFO_COLOR,
                        ),
                        ephemeral=True,
                    )
                except Exception as e:
                    logger.exception(f"Unhandled exception in followup component callback: {e}")
                    await inter.followup.send(f"❌ Something went wrong.", ephemeral=True)
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Receive Crypto",
                    description="Pick which address you want to use.",
                    color=BRAND_COLOR,
                ),
                view=CoinPickerView(addr),
                ephemeral=True,
            )
        except Exception as e:
            logger.exception(f"Exception triggered in button interaction: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Something went wrong processing your request.", ephemeral=True)

    @discord.ui.button(label="QR Code", style=discord.ButtonStyle.secondary, row=0)
    async def action_qr(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            async def qrc(inter: discord.Interaction, coin: str):
                try:
                    a = self.wallet["sol_address"] if coin == "SOL" else self.wallet["ltc_address"]
                    qr_buf = await asyncio.to_thread(make_deposit_qr_png, a, coin)
                    await inter.followup.send(
                        embed=discord.Embed(
                            title=f"{coin} Deposit QR Code",
                            description=f"`{a}`",
                            color=BRAND_COLOR,
                        ).set_image(url="attachment://action_qr.png"),
                        file=discord.File(qr_buf, filename="action_qr.png"),
                        ephemeral=True,
                    )
                except Exception as e:
                    logger.exception(f"Unhandled exception in followup component callback: {e}")
                    await inter.followup.send(f"❌ Something went wrong.", ephemeral=True)
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="QR Code",
                    description="Which address do you want a QR code for?",
                    color=BRAND_COLOR,
                ),
                view=CoinPickerView(qrc),
                ephemeral=True,
            )
        except Exception as e:
            logger.exception(f"Exception triggered in button interaction: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Something went wrong processing your request.", ephemeral=True)

    @discord.ui.button(label="Settings", style=discord.ButtonStyle.secondary, row=0)
    async def action_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Settings",
                    description=(
                        "**Change Currency** - Switch between USD, GBP, and EUR\n"
                        "**Reset PIN** - Change your security PIN\n"
                        "**Delete Wallet** - Permanently remove your wallet"
                    ),
                    color=BRAND_COLOR,
                ),
                view=SettingsView(str(interaction.user.id)),
                ephemeral=True,
            )
        except Exception as e:
            logger.exception(f"Exception triggered in button interaction: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Something went wrong processing your request.", ephemeral=True)

class Dashboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="dashboard", description="Open your Comix Wallet dashboard UI.")
    async def dashboard(self, interaction: discord.Interaction) -> None:
        if not await ensure_wallet(interaction):
            return

        await interaction.response.defer()

        user_id_str = str(interaction.user.id)
        wallet = await get_wallet(str(interaction.user.id))
        if not wallet:
            await interaction.followup.send(
                embed=discord.Embed(title="Wallet not found", color=ERROR_COLOR)
            )
            return

        await update_last_accessed(str(interaction.user.id))

        prices = await get_prices()
        currency = wallet.get("currency", "usd")
        sol_balance, ltc_balance, sol_data, ltc_data = await asyncio.gather(
            get_sol_balance(wallet["sol_address"]),
            get_ltc_balance(wallet["ltc_address"]),
            fetch_coin_history("solana"),
            fetch_coin_history("litecoin"),
        )

        sol_hist_data, sol_timestamps = sol_data if sol_data[0] else (None, [])
        ltc_hist_data, ltc_timestamps = ltc_data if ltc_data[0] else (None, [])

        card_buf = await asyncio.to_thread(
            build_dashboard_canvas,
            interaction.user.name,
            sol_balance,
            ltc_balance,
            prices,
            currency,
            sol_hist_data,
            ltc_hist_data,
            sol_timestamps,
            ltc_timestamps,
        )

        await interaction.followup.send(
            file=discord.File(card_buf, filename="dashboard.png"),
            view=DashboardView(wallet, prices),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Dashboard(bot))
