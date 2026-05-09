import os
import json
import smtplib
import tempfile
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from flask import Flask, request, jsonify
import anthropic
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from moviepy import ImageSequenceClip, concatenate_videoclips

app = Flask(__name__)

WIDTH, HEIGHT = 1080, 1920
FPS = 30

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PASSWORD = os.environ.get("GMAIL_PASSWORD")
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL")

PALETTES = [
    {"bg1": (10, 10, 10), "bg2": (20, 20, 30), "accent": (255, 80, 80)},
    {"bg1": (5, 15, 25), "bg2": (10, 25, 45), "accent": (80, 180, 255)},
    {"bg1": (15, 10, 5), "bg2": (30, 20, 5), "accent": (255, 200, 50)},
]

def generate_scripts():
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = """Tu es un expert en marketing TikTok pour le e-commerce.
Genere 3 scripts de videos TikTok pour vendre une brosse anti-poil a 14,99 EUR.
Chaque video doit avoir 6 slides de texte court (max 3 lignes, max 15 mots par slide).
Les 3 angles : 1) Probleme/Solution 2) Preuve sociale 3) Offre directe.
Reponds UNIQUEMENT en JSON valide, sans markdown, sans backticks, ce format exact:
{
  "videos": [
    {"angle": "Probleme/Solution", "slides": ["texte slide 1", "texte slide 2", "texte slide 3", "texte slide 4", "texte slide 5", "texte slide 6"]},
    {"angle": "Preuve sociale", "slides": ["texte slide 1", "texte slide 2", "texte slide 3", "texte slide 4", "texte slide 5", "texte slide 6"]},
    {"angle": "Offre directe", "slides": ["texte slide 1", "texte slide 2", "texte slide 3", "texte slide 4", "texte slide 5", "texte slide 6"]}
  ]
}
Pas d'emojis. Texte en francais uniquement."""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = message.content[0].text.strip()
    return json.loads(raw)

def make_gradient_frame(color1, color2):
    frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    for y in range(HEIGHT):
        t = y / HEIGHT
        r = int(color1[0] * (1 - t) + color2[0] * t)
        g = int(color1[1] * (1 - t) + color2[1] * t)
        b = int(color1[2] * (1 - t) + color2[2] * t)
        frame[y, :] = [r, g, b]
    return frame

def draw_text_on_frame(frame_array, text, accent_color, font_size=85):
    img = Image.fromarray(frame_array)
    draw = ImageDraw.Draw(img)
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    font = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except:
                continue
    if font is None:
        font = ImageFont.load_default()

    lines = text.split('\n')
    line_height = font_size + 20
    total_height = len(lines) * line_height
    start_y = (HEIGHT - total_height) // 2

    for i, line in enumerate(lines):
        text_width = draw.textlength(line, font=font)
        x = (WIDTH - text_width) // 2
        y = start_y + i * line_height
        draw.text((x + 4, y + 4), line, font=font, fill=(0, 0, 0))
        color = accent_color if i == 0 else (255, 255, 255)
        draw.text((x, y), line, font=font, fill=color)

    bar_y = HEIGHT - 80
    bar_width = 200
    bar_x = (WIDTH - bar_width) // 2
    draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + 8], radius=4, fill=accent_color)
    return np.array(img)

def create_video(slides, palette, output_path):
    bg1 = palette["bg1"]
    bg2 = palette["bg2"]
    accent = palette["accent"]
    clips = []
    for slide_text in slides:
        duration = 2.5
        frames_count = int(duration * FPS)
        base_frame = make_gradient_frame(bg1, bg2)
        text_frame = draw_text_on_frame(base_frame.copy(), slide_text, accent)
        frames = []
        for f in range(frames_count):
            if f < 10:
                alpha = f / 10.0
                faded = (base_frame * (1 - alpha) + text_frame * alpha).astype(np.uint8)
                frames.append(faded)
            elif f > frames_count - 10:
                alpha = (frames_count - f) / 10.0
                faded = (base_frame * (1 - alpha) + text_frame * alpha).astype(np.uint8)
                frames.append(faded)
            else:
                frames.append(text_frame)
        clip = ImageSequenceClip(frames, fps=FPS)
        clips.append(clip)
    final = concatenate_videoclips(clips, method="compose")
    final.write_videofile(output_path, fps=FPS, codec='libx264', audio=False, preset='ultrafast', logger=None)
    final.close()

def send_email_with_videos(video_paths):
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = RECIPIENT_EMAIL
    msg['Subject'] = "Tes 3 videos TikTok du jour - Brosse Anti-Poil"
    body = "Bonjour,\n\nVoici tes 3 videos TikTok generees automatiquement pour aujourd'hui.\nAjoute la musique lo-fi dans CapCut et poste !\n\nBonne journee."
    msg.attach(MIMEText(body, 'plain'))
    for video_path in video_paths:
        with open(video_path, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(video_path)}"')
            msg.attach(part)
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.send_message(msg)

@app.route('/')
def index():
    return jsonify({"status": "ok", "message": "TikTok Generator API"})

import threading

@app.route('/generate', methods=['POST'])
def generate():
    def run_in_background():
        try:
            scripts_data = generate_scripts()
            video_paths = []
            with tempfile.TemporaryDirectory() as tmpdir:
                for i, video_data in enumerate(scripts_data['videos']):
                    slides = video_data['slides']
                    palette = PALETTES[i % len(PALETTES)]
                    output_path = os.path.join(tmpdir, f"video_{i+1}.mp4")
                    create_video(slides, palette, output_path)
                    video_paths.append(output_path)
                send_email_with_videos(video_paths)
        except Exception as e:
            print(f"Erreur background: {e}")
    
    thread = threading.Thread(target=run_in_background)
    thread.start()
    return jsonify({"status": "success", "message": "Generation en cours, tu recevras un mail dans quelques minutes"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
