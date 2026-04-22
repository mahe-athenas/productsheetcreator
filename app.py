#!/usr/bin/env python3
"""
Athenas Produktblad PDF Generator
==================================
Generates a product sheet PDF following the Athenas template design,
populated with content extracted from a given URL.

Usage:
    python generate_produktblad.py <url> [--output filename.pdf]
    
The script uses Claude API to intelligently extract and structure
content from the URL into the template format.
"""

import sys
import os
import json
import argparse
import textwrap
import requests
from bs4 import BeautifulSoup

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import Color, HexColor, white, black
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import Paragraph, Frame
from reportlab.lib.styles import ParagraphStyle

# ──────────────────────────────────────────────
# DESIGN TOKENS (extracted from template PDF)
# ──────────────────────────────────────────────

# Colors
DARK_BLUE = HexColor("#2D3E50")       # Primary dark background
DARK_BLUE_ALT = HexColor("#334455")   # Slightly lighter variant
LIGHT_GRAY_TEXT = HexColor("#B0BEC5") # Subtitle / secondary text on dark bg
WHITE = HexColor("#FFFFFF")
DARK_TEXT = HexColor("#2D3E50")       # Body text on white
ACCENT_LINE = HexColor("#2D3E50")     # Separator lines / accents
SECTION_TAG_BG = HexColor("#2D3E50")  # Section tag background

# Page dimensions
PAGE_W, PAGE_H = A4  # 595.27 x 841.89 points
MARGIN_LEFT = 50
MARGIN_RIGHT = 50
MARGIN_TOP = 50
MARGIN_BOTTOM = 50
CONTENT_W = PAGE_W - MARGIN_LEFT - MARGIN_RIGHT

# Register fonts — matching the original Athenas template
# Overpass Bold: Cover title (str. 47)
# Open Sans Condensed Light: Tagline / subtitle on cover (str. 18) — substitutes "Cloud Condensed"
# Open Sans Light: Section tags, body text (str. 11-12)
# Open Sans Regular: Section headings (str. 20.5)
# Open Sans Bold: Bold accents
# Abril Fatface: Module numbers 01-04 (str. 42.9)
CUSTOM_FONT_DIR = "/home/claude/fonts/"
OPENSANS_DIR = "/usr/share/fonts/truetype/open-sans/"

pdfmetrics.registerFont(TTFont("OverpassBold", CUSTOM_FONT_DIR + "Overpass-Bold.ttf"))
pdfmetrics.registerFont(TTFont("OverpassRegular", CUSTOM_FONT_DIR + "Overpass-Regular.ttf"))
pdfmetrics.registerFont(TTFont("OpenSans", OPENSANS_DIR + "OpenSans-Regular.ttf"))
pdfmetrics.registerFont(TTFont("OpenSansLight", OPENSANS_DIR + "OpenSans-Light.ttf"))
pdfmetrics.registerFont(TTFont("OpenSansBold", OPENSANS_DIR + "OpenSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("OpenSansSemibold", OPENSANS_DIR + "OpenSans-Semibold.ttf"))
pdfmetrics.registerFont(TTFont("OpenSansCondLight", OPENSANS_DIR + "OpenSans-CondLight.ttf"))
pdfmetrics.registerFont(TTFont("AbrilFatface", CUSTOM_FONT_DIR + "AbrilFatface-Regular.ttf"))

# ──────────────────────────────────────────────
# INTERNATIONALISATION (i18n)
# ──────────────────────────────────────────────

TRANSLATIONS = {
    "dk": {"produktblad":"PRODUKTBLAD","introduktion":"INTRODUKTION","udbytte_kompetencer":"UDBYTTE & KOMPETENCER","udbytte":"UDBYTTE","opbygning":"OPBYGNING","varighed_titel":"Varighed og fleksibilitet","moduler_indhold":"Moduler & indhold","modul":"MODUL","kontakt":"KONTAKT","kontakt_cta_1":"KONTAKT FOR AT","kontakt_cta_2":"HØRE MERE"},
    "se": {"produktblad":"PRODUKTBLAD","introduktion":"INTRODUKTION","udbytte_kompetencer":"RESULTAT & KOMPETENSER","udbytte":"RESULTAT","opbygning":"UPPLÄGG","varighed_titel":"Varaktighet och flexibilitet","moduler_indhold":"Moduler & innehåll","modul":"MODUL","kontakt":"KONTAKT","kontakt_cta_1":"KONTAKTA OSS","kontakt_cta_2":"FÖR MER INFO"},
    "no": {"produktblad":"PRODUKTBLAD","introduktion":"INTRODUKSJON","udbytte_kompetencer":"UTBYTTE & KOMPETANSER","udbytte":"UTBYTTE","opbygning":"OPPBYGGING","varighed_titel":"Varighet og fleksibilitet","moduler_indhold":"Moduler & innhold","modul":"MODUL","kontakt":"KONTAKT","kontakt_cta_1":"KONTAKT OSS","kontakt_cta_2":"FOR MER INFO"},
    "nl": {"produktblad":"PRODUCTBLAD","introduktion":"INTRODUCTIE","udbytte_kompetencer":"RESULTAAT & COMPETENTIES","udbytte":"RESULTAAT","opbygning":"OPBOUW","varighed_titel":"Duur en flexibiliteit","moduler_indhold":"Modules & inhoud","modul":"MODULE","kontakt":"CONTACT","kontakt_cta_1":"NEEM CONTACT","kontakt_cta_2":"MET ONS OP"},
    "com": {"produktblad":"PRODUCT SHEET","introduktion":"INTRODUCTION","udbytte_kompetencer":"OUTCOMES & COMPETENCIES","udbytte":"OUTCOMES","opbygning":"STRUCTURE","varighed_titel":"Duration and flexibility","moduler_indhold":"Modules & content","modul":"MODULE","kontakt":"CONTACT","kontakt_cta_1":"GET IN TOUCH","kontakt_cta_2":"TO LEARN MORE"},
    "de": {"produktblad":"PRODUKTBLATT","introduktion":"EINFÜHRUNG","udbytte_kompetencer":"ERGEBNISSE & KOMPETENZEN","udbytte":"ERGEBNISSE","opbygning":"AUFBAU","varighed_titel":"Dauer und Flexibilität","moduler_indhold":"Module & Inhalte","modul":"MODUL","kontakt":"KONTAKT","kontakt_cta_1":"KONTAKTIEREN","kontakt_cta_2":"SIE UNS"},
}

def get_lang(data):
    return data.get("lang", "dk")

def detect_lang_from_url(url):
    for tld, lang in [(".se/","se"),(".no/","no"),(".nl/","nl"),(".com/","com"),(".de/","de")]:
        if tld in url: return lang
    return "dk"

def t(data, key):
    lang = get_lang(data)
    return TRANSLATIONS.get(lang, TRANSLATIONS["dk"]).get(key, TRANSLATIONS["dk"].get(key, key))

# ──────────────────────────────────────────────
# HELPER FUNCTIONS
# ──────────────────────────────────────────────

def draw_dark_bg(c, y_from, y_to):
    """Draw a dark blue background rectangle from y_from (top) to y_to (bottom)."""
    c.setFillColor(DARK_BLUE)
    c.rect(0, y_to, PAGE_W, y_from - y_to, fill=1, stroke=0)


def draw_section_tag(c, label, x, y):
    """Draw a section label tag (e.g., 'INTRODUKTION') with dark bg."""
    c.setFillColor(SECTION_TAG_BG)
    tag_w = max(len(label) * 8.5 + 30, 200)
    tag_h = 28
    c.rect(x, y - tag_h, tag_w, tag_h, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("OpenSansLight", 11)
    c.drawString(x + 15, y - 19, label)


def draw_separator_line(c, x, y, width=60):
    """Draw a short accent line (like the ones under headings)."""
    c.setStrokeColor(ACCENT_LINE)
    c.setLineWidth(3)
    c.line(x, y, x + width, y)


def draw_numbered_item(c, number, text, x, y, max_width=400, light_text=True):
    """Draw a numbered module item (01, 02, etc.) with large number and text."""
    # Large number — Abril Fatface 42.9pt (matching template)
    c.setFillColor(WHITE)
    c.setFont("AbrilFatface", 42.9)
    c.drawString(x, y - 14, f"{number:02d}")
    
    # Description text — Open Sans Light
    text_color = LIGHT_GRAY_TEXT if light_text else WHITE
    c.setFillColor(text_color)
    c.setFont("OpenSansLight", 12.5)
    
    # Wrap text
    lines = textwrap.wrap(text, width=42)
    text_x = x + 90
    text_y = y - 6
    for line in lines:
        c.drawString(text_x, text_y, line)
        text_y -= 19
    
    # Generous vertical space between items (matches original template)
    return y - 80


def wrap_and_draw(c, text, x, y, max_width, font_name="OpenSansLight", font_size=10.5, 
                  line_height=16, color=None, char_width_factor=0.52):
    """Draw wrapped text and return the new y position."""
    if color:
        c.setFillColor(color)
    c.setFont(font_name, font_size)
    
    chars_per_line = int(max_width / (font_size * char_width_factor))
    lines = textwrap.wrap(text, width=chars_per_line)
    
    for line in lines:
        c.drawString(x, y, line)
        y -= line_height
    
    return y


def draw_bullet_items(c, items, x, y, max_width, font_name="OpenSansLight", font_size=10.5,
                      line_height=16, color=DARK_TEXT, bullet="•"):
    """Draw bullet point items and return new y position."""
    c.setFillColor(color)
    chars_per_line = int((max_width - 20) / (font_size * 0.52))
    
    for item in items:
        lines = textwrap.wrap(item, width=chars_per_line)
        c.setFont(font_name, font_size)
        # Draw a filled circle as bullet instead of text character
        c.saveState()
        c.setFillColor(color)
        c.circle(x + 3, y - 3, 2.5, fill=1, stroke=0)
        c.restoreState()
        c.setFillColor(color)
        c.setFont(font_name, font_size)
        first = True
        for line in lines:
            if first:
                c.drawString(x + 18, y, line)
                first = False
            else:
                c.drawString(x + 18, y, line)
            y -= line_height
        y -= 6  # Extra space between items
    
    return y


# ──────────────────────────────────────────────
# PAGE BUILDERS
# ──────────────────────────────────────────────

def build_cover_page(c, data, logo_path=None):
    """Page 1: Full dark blue cover with title."""
    draw_dark_bg(c, PAGE_H, 0)
    
    # Top left: "PRODUKTBLAD"
    c.setFillColor(WHITE)
    c.setFont("OpenSansBold", 8.5)
    c.drawString(MARGIN_LEFT, PAGE_H - 45, t(data, "produktblad"))
    
    # Top right: Logo (if available)
    if logo_path and os.path.exists(logo_path):
        c.drawImage(logo_path, PAGE_W - 180, PAGE_H - 65, width=130, height=50,
                     preserveAspectRatio=True, mask='auto')
    
    # Main title - Overpass Regular 47pt (not bold), positioned in bottom third
    title_y = 350
    c.setFillColor(WHITE)
    c.setFont("OverpassRegular", 47)
    
    title = data.get("title", "Produktblad Titel")
    title_lines = textwrap.wrap(title, width=18)
    for line in title_lines:
        c.drawString(MARGIN_LEFT, title_y, line)
        title_y -= 58
    
    # Subtitle — Cloud Condensed 18pt (using Open Sans Condensed Light as substitute)
    title_y -= 10
    c.setFillColor(LIGHT_GRAY_TEXT)
    c.setFont("OpenSansCondLight", 18)
    subtitle = data.get("subtitle", "")
    if subtitle:
        sub_lines = textwrap.wrap(subtitle, width=38)
        for line in sub_lines:
            c.drawString(MARGIN_LEFT, title_y, line)
            title_y -= 26
    
    # Type label removed per template update
    
    c.showPage()


def build_intro_page(c, data, decoration_img=None):
    """Page 2: Introduction with section tag, heading, and body text."""
    # Section tag at top
    draw_section_tag(c, t(data, "introduktion"), MARGIN_LEFT - 10, PAGE_H - 35)
    
    # Optional decoration image on left
    if decoration_img and os.path.exists(decoration_img):
        c.drawImage(decoration_img, MARGIN_LEFT - 20, PAGE_H * 0.25,
                     width=160, height=PAGE_H * 0.55,
                     preserveAspectRatio=True, mask='auto')
    
    # Heading (right side or full width)
    heading_x = MARGIN_LEFT + 190 if decoration_img and os.path.exists(decoration_img) else MARGIN_LEFT + 30
    text_width = PAGE_W - heading_x - MARGIN_RIGHT
    
    y = PAGE_H - 100
    c.setFillColor(DARK_TEXT)
    
    # Section heading — Open Sans 20.5pt
    intro_heading = data.get("intro_heading", "BEDRE RESULTATER OG STÆRKERE TILKNYTNING")
    heading_lines = textwrap.wrap(intro_heading.upper(), width=28)
    c.setFont("OpenSans", 20.5)
    c.setFillColor(DARK_TEXT)
    for line in heading_lines:
        c.drawString(heading_x, y, line)
        y -= 28
    
    # Separator line
    y -= 15
    draw_separator_line(c, heading_x, y, width=50)
    y -= 30
    
    # Body paragraphs — Open Sans Light 12pt
    intro_paragraphs = data.get("intro_paragraphs", [])
    c.setFillColor(DARK_TEXT)
    
    for para in intro_paragraphs:
        y = wrap_and_draw(c, para, heading_x, y, text_width, 
                          font_name="OpenSansLight", font_size=12, line_height=17,
                          color=DARK_TEXT)
        y -= 12  # paragraph spacing
    
    c.showPage()


def build_benefits_page(c, data):
    """Page 3: Benefits / Udbytte list."""
    # Section tag
    draw_section_tag(c, t(data, "udbytte_kompetencer"), MARGIN_LEFT - 10, PAGE_H - 35)
    
    y = PAGE_H - 110
    
    # Heading — Open Sans 20.5pt
    c.setFillColor(DARK_TEXT)
    c.setFont("OpenSans", 20.5)
    c.drawString(MARGIN_LEFT + 30, y, t(data, "udbytte"))
    y -= 45
    
    # Sub heading — Open Sans Bold
    c.setFont("OpenSansBold", 11)
    benefits_intro = data.get("benefits_intro", "Workshoppen giver jer:")
    c.drawString(MARGIN_LEFT + 30, y, benefits_intro)
    y -= 30
    
    # Bullet points — Open Sans Light 12pt
    benefits = data.get("benefits", [])
    y = draw_bullet_items(c, benefits, MARGIN_LEFT + 40, y, 
                          CONTENT_W - 40, font_size=12, line_height=17,
                          color=DARK_TEXT)
    
    # Bottom dark section
    dark_section_h = 180
    draw_dark_bg(c, dark_section_h, 0)
    
    c.showPage()


def build_structure_page(c, data):
    """Page 4: Opbygning - structure overview with numbered modules."""
    # Top white section
    y = PAGE_H - 60
    c.setFillColor(DARK_TEXT)
    c.setFont("OpenSans", 20.5)
    c.drawString(MARGIN_LEFT, y, t(data, "opbygning"))
    
    y -= 20
    draw_separator_line(c, MARGIN_LEFT, y, width=50)
    y -= 35
    
    # Varighed og fleksibilitet
    c.setFont("OpenSansBold", 11)
    c.setFillColor(DARK_TEXT)
    c.drawString(MARGIN_LEFT, y, t(data, "varighed_titel"))
    y -= 22
    
    flex_text = data.get("flexibility_text", "")
    if flex_text:
        y = wrap_and_draw(c, flex_text, MARGIN_LEFT, y, CONTENT_W,
                          font_name="OpenSansLight", font_size=12, line_height=16, color=DARK_TEXT)
    y -= 20
    
    # Moduler & indhold
    c.setFont("OpenSansBold", 11)
    c.setFillColor(DARK_TEXT)
    c.drawString(MARGIN_LEFT, y, t(data, "moduler_indhold"))
    y -= 22
    
    modules_intro = data.get("modules_intro", "")
    if modules_intro:
        y = wrap_and_draw(c, modules_intro, MARGIN_LEFT, y, CONTENT_W,
                          font_name="OpenSansLight", font_size=12, line_height=16, color=DARK_TEXT)
    
    # Dark section with numbered modules
    dark_top = y - 30
    draw_dark_bg(c, dark_top, 0)
    
    modules = data.get("modules", [])
    mod_y = dark_top - 50
    
    for i, mod in enumerate(modules):
        if mod_y < 60:
            break
        mod_y = draw_numbered_item(c, i + 1, mod.get("title", ""), 
                                   MARGIN_LEFT + 20, mod_y)
    
    c.showPage()


def build_module_page(c, data, module_data, module_number):
    """Page 5-8: Individual module detail page."""
    # Section tag
    tag_label = f"{t(data, 'modul')} {module_number}"
    draw_section_tag(c, tag_label, MARGIN_LEFT - 10, PAGE_H - 35)
    
    y = PAGE_H - 100
    
    # Module title — Open Sans 20.5pt
    c.setFillColor(DARK_TEXT)
    c.setFont("OpenSans", 20.5)
    
    mod_title = module_data.get("title", "").upper()
    title_lines = textwrap.wrap(mod_title, width=30)
    for line in title_lines:
        c.drawString(MARGIN_LEFT + 30, y, line)
        y -= 32
    
    # Separator
    y -= 5
    draw_separator_line(c, MARGIN_LEFT + 30, y, width=50)
    y -= 30
    
    # Description text — Open Sans Light 12pt
    description = module_data.get("description", "")
    if description:
        y = wrap_and_draw(c, description, MARGIN_LEFT + 30, y, CONTENT_W - 30,
                          font_name="OpenSansLight", font_size=12, line_height=17, color=DARK_TEXT)
        y -= 15
    
    # Bullet points — Open Sans Light 12pt
    objectives = module_data.get("objectives", [])
    if objectives:
        y = draw_bullet_items(c, objectives, MARGIN_LEFT + 40, y,
                              CONTENT_W - 40, font_size=12, line_height=17, color=DARK_TEXT)
    
    # Optional photo at bottom of module page (crop-to-fill, never stretch)
    photo_path = module_data.get("photo", None)
    if photo_path and os.path.exists(photo_path):
        from reportlab.lib.utils import ImageReader
        photo_h = 280
        img = ImageReader(photo_path)
        img_w, img_h = img.getSize()
        # Calculate scale to fill the target area (cover crop)
        scale_w = PAGE_W / img_w
        scale_h = photo_h / img_h
        scale = max(scale_w, scale_h)
        draw_w = img_w * scale
        draw_h = img_h * scale
        # Center the image so overflow is cropped evenly
        offset_x = (PAGE_W - draw_w) / 2
        offset_y = (photo_h - draw_h) / 2
        # Clip to the target area
        c.saveState()
        p = c.beginPath()
        p.rect(0, 0, PAGE_W, photo_h)
        p.close()
        c.clipPath(p, stroke=0)
        c.drawImage(photo_path, offset_x, offset_y, width=draw_w, height=draw_h)
        c.restoreState()
    
    c.showPage()


def build_contact_page(c, data, logo_path=None, phone_icon=None, email_icon=None):
    """Page 9: Contact page with full dark blue background and inverted section tag."""
    # Full dark background covering entire page
    draw_dark_bg(c, PAGE_H, 0)
    
    # Inverted section tag: white background with dark blue text
    tag_label = t(data, "kontakt")
    tag_w = max(len(tag_label) * 8.5 + 30, 200)
    tag_h = 28
    c.setFillColor(WHITE)
    c.rect(MARGIN_LEFT - 10, PAGE_H - 35 - tag_h, tag_w, tag_h, fill=1, stroke=0)
    c.setFillColor(DARK_TEXT)
    c.setFont("OpenSansLight", 11)
    c.drawString(MARGIN_LEFT + 5, PAGE_H - 35 - 19, tag_label)
    
    y = PAGE_H - 200
    
    # "KONTAKT FOR AT HØRE MERE"
    c.setFillColor(WHITE)
    c.setFont("OpenSans", 20.5)
    center_x = PAGE_W / 2
    c.drawCentredString(center_x, y, t(data, "kontakt_cta_1"))
    y -= 28
    c.drawCentredString(center_x, y, t(data, "kontakt_cta_2"))
    
    y -= 20
    # Separator line (centered)
    c.setStrokeColor(WHITE)
    c.setLineWidth(3)
    c.line(center_x - 30, y, center_x + 30, y)
    y -= 50
    
    # Contact details
    contact = data.get("contact", {})
    c.setFillColor(WHITE)
    c.setFont("OpenSansLight", 13)
    
    name = contact.get("name", "")
    if name:
        c.drawCentredString(center_x, y, name)
        y -= 35
    
    # Phone with icon
    phone = contact.get("phone", "")
    if phone:
        icon_size = 18
        text_width = c.stringWidth(phone, "OpenSansLight", 13)
        total_w = icon_size + 10 + text_width
        start_x = center_x - total_w / 2
        if phone_icon and os.path.exists(phone_icon):
            c.drawImage(phone_icon, start_x, y - 3, width=icon_size, height=icon_size,
                        preserveAspectRatio=True, mask='auto')
        c.setFillColor(WHITE)
        c.setFont("OpenSansLight", 13)
        c.drawString(start_x + icon_size + 10, y, phone)
        y -= 30
    
    # Email with icon
    email = contact.get("email", "")
    if email:
        icon_size = 18
        text_width = c.stringWidth(email, "OpenSansLight", 13)
        total_w = icon_size + 10 + text_width
        start_x = center_x - total_w / 2
        if email_icon and os.path.exists(email_icon):
            c.drawImage(email_icon, start_x, y - 3, width=icon_size, height=icon_size,
                        preserveAspectRatio=True, mask='auto')
        c.setFillColor(WHITE)
        c.setFont("OpenSansLight", 13)
        c.drawString(start_x + icon_size + 10, y, email)
    
    # Bottom logo
    if logo_path and os.path.exists(logo_path):
        c.drawImage(logo_path, PAGE_W / 2 - 75, 80, width=150, height=56,
                     preserveAspectRatio=True, mask='auto')
    
    c.showPage()


# ──────────────────────────────────────────────
# CONTENT EXTRACTION
# ──────────────────────────────────────────────

def fetch_url_content(url):
    """Fetch and extract text content from a URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Remove script and style elements
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    
    # Get title
    title = soup.title.string if soup.title else ""
    
    # Get meta description
    meta_desc = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta:
        meta_desc = meta.get("content", "")
    
    # Get main text content
    text_blocks = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        text = tag.get_text(strip=True)
        if text and len(text) > 10:
            text_blocks.append({
                "tag": tag.name,
                "text": text
            })
    
    return {
        "url": url,
        "title": title,
        "meta_description": meta_desc,
        "content_blocks": text_blocks[:60]  # Limit to avoid token overflow
    }


def structure_content_with_claude(raw_content):
    """Use Claude API to intelligently structure the scraped content into template format."""
    
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    
    prompt = f"""Analyze this product/service page content and structure it into a product sheet (produktblad) format.

RAW CONTENT:
Title: {raw_content['title']}
Description: {raw_content['meta_description']}
Content blocks: {json.dumps(raw_content['content_blocks'][:40], ensure_ascii=False)}

Return ONLY valid JSON (no markdown, no backticks) with this exact structure:
{{
    "title": "Main product/service title (short, max 6 words)",
    "subtitle": "A compelling subtitle describing the offering (max 15 words)",
    "type_label": "What type of product/service this is (e.g., 'Et skræddersyet forløb', 'En workshop', 'Et kursus')",
    "intro_heading": "SHORT heading for intro section (max 6 words, compelling)",
    "intro_paragraphs": ["paragraph 1 about the offering (3-4 sentences)", "paragraph 2 (3-4 sentences)", "paragraph 3 about flexibility/customization (2-3 sentences)"],
    "benefits_intro": "Short intro to benefits list (e.g., 'Dette får I ud af det:')",
    "benefits": ["benefit 1", "benefit 2", "benefit 3", "benefit 4", "benefit 5", "benefit 6"],
    "flexibility_text": "Text about duration and flexibility of the offering (2-3 sentences)",
    "modules_intro": "Intro to the modules/content structure (1-2 sentences)",
    "modules": [
        {{"title": "Module 1 title", "description": "Module 1 description (2-3 sentences)", "objectives": ["learning point 1", "learning point 2", "learning point 3"]}},
        {{"title": "Module 2 title", "description": "Module 2 description", "objectives": ["point 1", "point 2", "point 3"]}},
        {{"title": "Module 3 title", "description": "Module 3 description", "objectives": ["point 1", "point 2", "point 3"]}},
        {{"title": "Module 4 title", "description": "Module 4 description", "objectives": ["point 1", "point 2", "point 3"]}}
    ],
    "contact": {{
        "name": "Kontaktperson",
        "phone": "+45 XX XX XX XX",
        "email": "email@example.com"
    }}
}}

IMPORTANT: 
- Write ALL content in Danish
- Make it professional and compelling
- If the source is in English, translate to Danish
- The content should feel natural for a Danish B2B produktblad
- Extract real contact info from the content if available, otherwise use placeholder
- Keep benefits concise (1-2 lines each)
"""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 3000,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        resp.raise_for_status()
        result = resp.json()
        text = result["content"][0]["text"]
        # Clean potential markdown fences
        text = text.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(text)
    except Exception as e:
        print(f"⚠️  Claude API fejl: {e}")
        print("   Bruger fallback-strukturering...")
        return fallback_structure(raw_content)


def fallback_structure(raw_content):
    """Simple fallback if Claude API is not available."""
    blocks = raw_content.get("content_blocks", [])
    
    # Try to extract headings and paragraphs
    headings = [b["text"] for b in blocks if b["tag"] in ("h1", "h2")]
    paragraphs = [b["text"] for b in blocks if b["tag"] == "p"]
    list_items = [b["text"] for b in blocks if b["tag"] == "li"]
    
    title = headings[0] if headings else raw_content.get("title", "Produktblad")
    
    return {
        "title": title[:60],
        "subtitle": raw_content.get("meta_description", "")[:100],
        "type_label": "Et skræddersyet forløb",
        "intro_heading": "OVERBLIK OG INDSIGT",
        "intro_paragraphs": paragraphs[:3] if paragraphs else ["Indhold hentes fra den angivne URL."],
        "benefits_intro": "Dette får I ud af det:",
        "benefits": (list_items or paragraphs)[:6],
        "flexibility_text": "Forløbet kan tilpasses jeres behov og virkelighed.",
        "modules_intro": "Herunder ses den vejledende struktur.",
        "modules": [
            {"title": h, "description": "", "objectives": []}
            for h in headings[1:5]
        ] if len(headings) > 1 else [
            {"title": "Modul 1", "description": "Indhold tilpasses.", "objectives": []}
        ],
        "contact": {
            "name": "Kontaktperson",
            "phone": "+45 XX XX XX XX",
            "email": "kontakt@example.dk"
        }
    }


# ──────────────────────────────────────────────
# MAIN PDF BUILDER
# ──────────────────────────────────────────────

def generate_produktblad(data, output_path, logo_path=None, decoration_img=None,
                         phone_icon=None, email_icon=None):
    """Generate the complete produktblad PDF."""
    
    # Auto-select logo based on language
    lang = get_lang(data)
    LOGO_MAP = {
        "dk": "/home/claude/logo_clean.png",
        "se": "/home/claude/logo_se_clean.png",
        # Add more country logos here as needed:
        # "no": "/home/claude/logo_no_clean.png",
        # "nl": "/home/claude/logo_nl_clean.png",
        # "com": "/home/claude/logo_com_clean.png",
        # "de": "/home/claude/logo_de_clean.png",
    }
    if logo_path is None:
        logo_path = LOGO_MAP.get(lang, LOGO_MAP.get("dk"))
    elif lang in LOGO_MAP and logo_path == LOGO_MAP.get("dk"):
        # If default DK logo was passed but language is different, swap it
        logo_path = LOGO_MAP.get(lang, logo_path)
    
    c = canvas.Canvas(output_path, pagesize=A4)
    c.setTitle(data.get("title", "Produktblad"))
    c.setAuthor("Athenas")
    
    # Page 1: Cover
    build_cover_page(c, data, logo_path)
    
    # Page 2: Introduction
    build_intro_page(c, data, decoration_img)
    
    # Page 3: Benefits
    build_benefits_page(c, data)
    
    # Page 4: Structure overview
    build_structure_page(c, data)
    
    # Pages 5+: Individual modules
    modules = data.get("modules", [])
    for i, mod in enumerate(modules):
        build_module_page(c, data, mod, i + 1)
    
    # Last page: Contact
    build_contact_page(c, data, logo_path, phone_icon=phone_icon, email_icon=email_icon)
    
    c.save()
    print(f"✅ PDF genereret: {output_path}")
    
    # Also generate a cover mockup PNG (733x733, grey bg, cover page as tilted card with shadow)
    _generate_cover_mockup(output_path)


def _generate_cover_mockup(pdf_path):
    """Generate a 733x733 PNG mockup showing the cover page on a grey background with shadow."""
    import subprocess
    
    mockup_path = pdf_path.replace(".pdf", "_cover.png")
    
    try:
        # 1. Extract first page as high-res image
        tmp_prefix = "/tmp/mockup_cover"
        subprocess.run(
            ["pdftoppm", "-png", "-r", "300", "-f", "1", "-l", "1", pdf_path, tmp_prefix],
            check=True, capture_output=True
        )
        
        # Find the generated file
        import glob
        cover_files = sorted(glob.glob(f"{tmp_prefix}*.png"))
        if not cover_files:
            print("⚠️  Kunne ikke generere cover mockup")
            return
        
        cover_img = cover_files[0]
        
        # 2. Create the mockup with ImageMagick:
        #    - 733x733 canvas with grey background (#B0B0B0)
        #    - Cover page resized to fit ~70% of canvas height
        #    - Slight perspective tilt
        #    - Drop shadow
        subprocess.run([
            "convert",
            # Grey background canvas
            "-size", "733x733", "xc:#B0B0B0",
            # Load cover, resize to fit
            "(", cover_img,
                "-resize", "420x594",
                "-background", "none",
                # Add subtle shadow
                "(", "+clone",
                    "-background", "#00000060",
                    "-shadow", "60x8+4+6",
                ")",
                "+swap",
                "-background", "none",
                "-layers", "merge",
            ")",
            # Center on canvas
            "-gravity", "center",
            "-composite",
            mockup_path
        ], check=True, capture_output=True)
        
        print(f"✅ Cover mockup: {mockup_path}")
        
        # Cleanup temp files
        for f in cover_files:
            os.remove(f)
            
    except Exception as e:
        print(f"⚠️  Cover mockup fejl: {e}")


# ──────────────────────────────────────────────
# CLI ENTRY POINT
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generér et Athenas-stil produktblad fra en URL")
    parser.add_argument("url", help="URL til produktsiden der skal konverteres")
    parser.add_argument("--output", "-o", default=None, help="Output filnavn (default: produktblad_output.pdf)")
    parser.add_argument("--logo", default=None, help="Sti til logo-billede (PNG)")
    parser.add_argument("--decoration", default=None, help="Sti til dekorationsbillede (PNG)")
    
    args = parser.parse_args()
    
    output = args.output or "produktblad_output.pdf"
    
    print(f"🔍 Henter indhold fra: {args.url}")
    raw_content = fetch_url_content(args.url)
    print(f"   Fandt {len(raw_content['content_blocks'])} indholdsblokke")
    
    print("🧠 Strukturerer indhold med Claude...")
    structured = structure_content_with_claude(raw_content)
    
    print("📄 Genererer PDF...")
    generate_produktblad(
        structured, 
        output,
        logo_path=args.logo,
        decoration_img=args.decoration
    )


if __name__ == "__main__":
    main()
