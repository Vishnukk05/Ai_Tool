import os
import logging
import datetime
import uuid
import time
from flask import Flask, render_template, request, jsonify, Response
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from gtts import gTTS
from xhtml2pdf import pisa
from io import BytesIO
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_AUTO_SIZE
import speech_recognition as sr
from dotenv import load_dotenv
import psutil
import PIL.Image

# --- LOAD ENV ---
basedir = os.path.abspath(os.path.dirname(__file__))
env_path = os.path.join(basedir, '.env')
load_dotenv(env_path)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
API_KEY = os.environ.get("GOOGLE_API_KEY")
DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"
STATIC_FOLDER = os.path.join(basedir, 'static')
if not os.path.exists(STATIC_FOLDER): os.makedirs(STATIC_FOLDER)

# --- MODEL LIST ---
AVAILABLE_MODELS = [
    'gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.0-flash-lite', 
    'gemini-2.5-pro', 'gemini-2.0-flash', 'gemini-flash-latest', 'gemini-1.5-flash'
]

# --- STATS TRACKING ---
global_stats = {
    "text_gen": 5, "audio_gen": 2, "transcribe": 3, "pdf_gen": 4, 
    "chat_msgs": 0, "image_analysis": 0, "code_review": 0, "quiz_gen": 0
}

def increment_stat(field_name):
    try:
        if field_name in global_stats: global_stats[field_name] += 1
    except: pass

# --- AI FUNCTIONS ---
def configure_genai():
    if API_KEY: genai.configure(api_key=API_KEY)

def get_safe_ai_response(prompt, image=None):
    configure_genai()
    settings = {
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE
    }

    for model_name in AVAILABLE_MODELS:
        try:
            model = genai.GenerativeModel(model_name)
            if image:
                response = model.generate_content([prompt, image], safety_settings=settings)
            else:
                response = model.generate_content(prompt, safety_settings=settings)
            if response.text: return response.text
        except Exception as e:
            continue 
    return None

# --- ROUTES ---

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/stats')
def get_stats():
    try: c, r = psutil.cpu_percent(0.1), psutil.virtual_memory().percent
    except: c, r = 0, 0
    return jsonify({"cpu": c, "ram": r, "usage": global_stats})

@app.route('/download-report')
def download_report():
    try:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try: cpu, ram = psutil.cpu_percent(None), psutil.virtual_memory().percent
        except: cpu, ram = 0, 0
        
        report_text = f"""
================================================
       AI WORKSPACE - SYSTEM HEALTH REPORT
================================================
Generated on:   {now}
Server Status:  Active & Online

[ SYSTEM RESOURCES ]
------------------------------------------------
CPU Usage:      {cpu}%
RAM Usage:      {ram}%

[ LIFETIME TOOL USAGE ]
------------------------------------------------
PPT Presentations:      {global_stats.get('text_gen', 0)}
Audio Synthesized:      {global_stats.get('audio_gen', 0)}
Transcriptions:         {global_stats.get('transcribe', 0)}
Documents Created:      {global_stats.get('pdf_gen', 0)}
Images Analyzed:        {global_stats.get('image_analysis', 0)}
Quizzes Generated:      {global_stats.get('quiz_gen', 0)}
Code Reviews:           {global_stats.get('code_review', 0)}
------------------------------------------------
End of Report.
"""
        return Response(report_text, mimetype="text/plain", headers={"Content-disposition": "attachment; filename=system_report.txt"})
    except Exception as e: return str(e), 500

@app.route('/chat', methods=['POST'])
def chat():
    increment_stat('chat_msgs')
    try:
        user_msg = request.form.get('message', '')
        if not user_msg: return jsonify({"success": False, "error": "Empty message"}), 400
        full_prompt = f"You are the AI Workspace Assistant. Keep answers concise.\n\nUser: {user_msg}"
        response = get_safe_ai_response(full_prompt)
        if not response: return jsonify({"success": False, "error": "System Busy."})
        return jsonify({"success": True, "response": response, "demo": False})
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 500

@app.route('/generate-minutes', methods=['POST'])
def generate_minutes():
    increment_stat('text_gen')
    try:
        notes = request.form.get('notes', '')
        prompt = f"Convert to Meeting Minutes (Agenda, Decisions, Actions):\n{notes}"
        content = get_safe_ai_response(prompt)
        return jsonify({"success": True, "minutes": content if content else "Error", "demo": False})
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 500

@app.route('/make-ppt', methods=['POST'])
def make_ppt():
    increment_stat('text_gen')
    try:
        topic = request.form.get('topic', '')
        src_text = request.form.get('source_text', '')
        template_file = request.files.get('template_file')
        
        if template_file and template_file.filename != '':
            temp_path = os.path.join(STATIC_FOLDER, f"temp_{uuid.uuid4().hex}.pptx")
            template_file.save(temp_path)
            prs = Presentation(temp_path)
        else:
            prs = Presentation()

        prompt = (f"Create a presentation about {topic}. {src_text}. "
                  "Format exactly:\nSLIDE_TITLE: [Title]\nBULLET: [Point 1]\nBULLET: [Point 2]")
        
        content = get_safe_ai_response(prompt)
        if not content: content = f"SLIDE_TITLE: {topic}\nBULLET: Content failed."

        lines = content.split('\n')
        curr = None
        
        try:
            slide = prs.slides.add_slide(prs.slide_layouts[0])
            slide.shapes.title.text = topic.upper()
        except: pass

        for line in lines:
            clean = line.strip().replace('*', '').replace('#', '')
            if "SLIDE_TITLE:" in clean:
                try:
                    layout_index = 1 if len(prs.slide_layouts) > 1 else 0
                    curr = prs.slides.add_slide(prs.slide_layouts[layout_index])
                    curr.shapes.title.text = clean.split("SLIDE_TITLE:", 1)[1].strip()
                    curr.placeholders[1].text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
                    curr.placeholders[1].text_frame.word_wrap = True
                except: pass
            elif "BULLET:" in clean and curr:
                try:
                    p = curr.placeholders[1].text_frame.add_paragraph()
                    p.text = clean.split("BULLET:", 1)[1].strip()
                    p.level = 0
                    curr.placeholders[1].text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
                except: pass

        fname = f"ppt_{uuid.uuid4().hex[:10]}.pptx"
        prs.save(os.path.join(STATIC_FOLDER, fname))
        if 'temp_path' in locals() and os.path.exists(temp_path): os.remove(temp_path)
        return jsonify({"success": True, "file_url": f"/static/{fname}", "demo": False})
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 500

@app.route('/text-to-audio', methods=['POST'])
def text_to_audio():
    increment_stat('audio_gen')
    try:
        text = request.form.get('text', '')
        lang = request.form.get('language', 'en') 
        
        if lang != 'en':
            translated_text = get_safe_ai_response(f"Translate the following text to language code '{lang}'. Return ONLY the translated text:\n\n{text}")
            if translated_text: text = translated_text.strip()

        fname = f"audio_{uuid.uuid4().hex[:10]}.mp3"
        try: tts = gTTS(text=text, lang=lang, slow=False)
        except: tts = gTTS(text=text, lang='en', slow=False)
        tts.save(os.path.join(STATIC_FOLDER, fname))
        return jsonify({"success": True, "file_url": f"/static/{fname}", "demo": False, "translated_text": text})
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 500

@app.route('/audio-to-text', methods=['POST'])
def audio_to_text():
    increment_stat('transcribe')
    try:
        f = request.files['file']
        lang_code = request.form.get('language', 'en-US') 
        fname = f"up_{uuid.uuid4().hex[:10]}.wav"
        fpath = os.path.join(STATIC_FOLDER, fname)
        f.save(fpath)
        r = sr.Recognizer()
        with sr.AudioFile(fpath) as src:
            audio_data = r.record(src)
            txt = r.recognize_google(audio_data, language=lang_code)
        return jsonify({"success": True, "text": txt, "audio_url": f"/static/{fname}", "demo": False})
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 500

@app.route('/translate', methods=['POST'])
def translate():
    increment_stat('text_gen')
    try:
        t, tgt = request.form.get('text', ''), request.form.get('target_language', '')
        res = get_safe_ai_response(f"Translate to {tgt}: {t}")
        return jsonify({"success": True, "translation": res if res else "Busy", "demo": False})
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 500

@app.route('/generate-email', methods=['POST'])
def generate_email():
    increment_stat('text_gen')
    try:
        to, topic = request.form.get('recipient', ''), request.form.get('topic', '')
        res = get_safe_ai_response(f"Write email to {to} about {topic}.")
        return jsonify({"success": True, "email_content": res if res else "Busy", "demo": False})
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 500

@app.route('/text-to-pdf', methods=['POST'])
def text_to_pdf():
    increment_stat('pdf_gen')
    try:
        h = request.form.get('html_content', '')
        if request.form.get('translation_needed') == 'true':
            t = request.form.get('target_language', 'English')
            res = get_safe_ai_response(f"Translate HTML to {t}, keep tags: {h}")
            if res: h = res.replace('```html','').replace('```','')
        fname = f"doc_{uuid.uuid4().hex[:10]}.pdf"
        with open(os.path.join(STATIC_FOLDER, fname), "w+b") as f: pisa.CreatePDF(BytesIO(h.encode('utf-8')), dest=f)
        return jsonify({"success": True, "file_url": f"/static/{fname}", "demo": False})
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 500

@app.route('/analyze-image', methods=['POST'])
def analyze_image():
    increment_stat('image_analysis')
    try:
        if 'image' not in request.files: return jsonify({"success": False, "error": "No image uploaded"}), 400
        image_file = request.files['image']
        prompt = request.form.get('prompt', 'Describe this image.')
        img = PIL.Image.open(image_file)
        response = get_safe_ai_response(prompt, image=img)
        return jsonify({"success": True, "analysis": response if response else "Failed."})
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 500

@app.route('/generate-quiz', methods=['POST'])
def generate_quiz():
    increment_stat('quiz_gen')
    try:
        topic = request.form.get('topic', '')
        count = request.form.get('count', '5')
        
        prompt = f"Create a {count}-question Multiple Choice Quiz about: {topic}. Include the Answer Key at the bottom."
        quiz_text = get_safe_ai_response(prompt)
        
        if not quiz_text: return jsonify({"success": False, "error": "AI Busy"}), 503

        fname = f"quiz_{uuid.uuid4().hex[:10]}.pdf"
        html_content = f"<html><body><h2>Quiz: {topic}</h2><hr><pre style='font-family:Helvetica;font-size:12pt;white-space:pre-wrap;'>{quiz_text}</pre></body></html>"
        
        with open(os.path.join(STATIC_FOLDER, fname), "w+b") as f:
            pisa.CreatePDF(BytesIO(html_content.encode('utf-8')), dest=f)

        return jsonify({"success": True, "quiz": quiz_text, "file_url": f"/static/{fname}", "demo": False})
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 500

@app.route('/review-code', methods=['POST'])
def review_code():
    increment_stat('code_review')
    try:
        code = request.form.get('code', '')
        res = get_safe_ai_response(f"Review this code. Find bugs, suggest improvements:\n\n{code}")
        return jsonify({"success": True, "review": res if res else "Error"})
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)