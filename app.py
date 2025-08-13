from flask import Flask, request, render_template, redirect, url_for, jsonify, send_from_directory, session, flash, send_file
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
import os
import re
import sqlite3
import uuid
from pdf2image import convert_from_path
import fitz  # PyMuPDF
import smtplib
from email.message import EmailMessage
from PIL import Image
from datetime import datetime
from filelock import FileLock, Timeout
import logging
import threading
import time
import secrets
from dotenv import load_dotenv
from pathlib import Path
import signal
import subprocess
from pyngrok import ngrok, conf

##logging.basicConfig(
##    level=logging.INFO,  # or logging.DEBUG for more detail
##    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
##    datefmt='%Y-%m-%d %H:%M:%S'
##)

load_dotenv()  # Loads variables from .env file
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

@app.before_request
def log_incoming():
    app.logger.info(f"Incoming request: {request.method} {request.path}")

xdim = 170
points_offset = 40
size_date_font = 10

# Email setup
EMAIL = 'your_email@gmail.com'
PASSWORD = 'your_app_password'
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = EMAIL
app.config['MAIL_PASSWORD'] = PASSWORD
mail = Mail(app)

# Folder configuration
app.config['PDF_UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['PDF_UPLOAD_FOLDER'], exist_ok=True)

app.config['SIGNATURE_UPLOAD_FOLDER'] = 'static/signatures'
os.makedirs(app.config['SIGNATURE_UPLOAD_FOLDER'], exist_ok=True)

os.makedirs('static', exist_ok=True)
os.makedirs('signed', exist_ok=True)

# temporary route
@app.route('/__routes__')
def show_routes():
    lines = []
    for r in app.url_map.iter_rules():
        methods = ','.join(sorted(r.methods - {'HEAD', 'OPTIONS'}))
        lines.append(f"{r.rule}  ->  methods: {methods}")
    return '<pre>' + '\n'.join(sorted(lines)) + '</pre>'


from flask import send_file  # add this import at the top of your file

@app.route('/sign_document/<signer_name>', methods=['GET', 'POST'])
def sign_document(signer_name):
    import os
    import logging
    import sqlite3
    from flask import request, render_template, redirect, url_for, flash

    logging.warning(f"[sign_document] HIT route — method={request.method}")
    logging.info(f"Accessing sign_document for signer: {signer_name}")

    signer_name = signer_name.lower().replace('_', ' ')

    # DB lookup
    conn = sqlite3.connect('signers.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM signers WHERE LOWER(name) = ?", (signer_name,))
    signer = c.fetchone()
    conn.close()

    # 🔍 Debug: Show exactly what we got from DB
    logging.warning(f"[DEBUG] signer keys: {list(signer.keys()) if signer else 'NO SIGNER'}")
    logging.warning(f"[DEBUG] signer row: {dict(signer) if signer else 'NO SIGNER'}")

    if not signer:
        logging.warning(f"Signer '{signer_name}' not found in DB")
        return "Invalid signer link", 404

    if request.method == 'POST':
        sig_file = request.files.get('signature')
        if not sig_file:
            flash("Please upload a signature image.")
            return redirect(request.url)

        upload_folder = 'uploads/signatures'
        os.makedirs(upload_folder, exist_ok=True)
        sig_basename = f"{signer_name}_signature.png"
        sig_path = os.path.join(upload_folder, sig_basename)
        sig_file.save(sig_path)

        page_val = int(signer['page']) if signer['page'] is not None else 0
        signer_x = float(signer['x']) if signer['x'] is not None else 0.0
        signer_y = float(signer['y']) if signer['y'] is not None else 0.0
        sig_width_val = float(signer['sig_width']) if signer['sig_width'] is not None else 100.0
        sig_height_val = float(signer['sig_height']) if signer['sig_height'] is not None else 50.0

        signer_data = {
            "name": signer_name,
            "page": page_val,
            "x": signer_x,
            "y": signer_y,
            "signature_path": sig_path,
            "sig_width": sig_width_val,
            "sig_height": sig_height_val
        }

        # ✅ Always resolve PDF path/filename first
        pdf_path = None
        if 'pdf_path' in signer.keys() and signer['pdf_path']:
            pdf_path = signer['pdf_path']
        elif 'pdf_filename' in signer.keys() and signer['pdf_filename']:
            pdf_filename = signer['pdf_filename']
            if not pdf_filename.startswith("uploads/"):
                pdf_path = os.path.join("uploads", pdf_filename)
            else:
                pdf_path = pdf_filename
        else:
            logging.error("PDF information missing for signer in DB.")
            flash("Server error: PDF not found for this signer.")
            return redirect(request.url)

        logging.warning(f"[sign_document] Using PDF path: {pdf_path}")

        if not os.path.exists(pdf_path):
            logging.error(f"❌ PDF file not found: {pdf_path}")
            flash("Server error: PDF file is missing.")
            return redirect(request.url)

        try:
            output_filename = merge_pdf_signatures(pdf_path, signers=[signer_data])
        except Exception:
            logging.exception("Error while merging signature into PDF")
            flash("An error occurred while processing your signature. Please try again.")
            return redirect(request.url)

        try:
            conn = sqlite3.connect('signers.db')
            c = conn.cursor()
            c.execute("UPDATE signers SET has_signed = 1 WHERE LOWER(name) = ?", (signer_name,))
            conn.commit()
            conn.close()
            logging.info(f"Status updated to 'signed' for {signer_name}")
        except Exception:
            logging.exception("Failed to update signer status in DB")

        logging.info(f"Signature merged successfully for {signer_name} into {output_filename}")

        # ✅ Instead of sending file directly, show success page with countdown + download
        return render_template(
            'success.html',
            pdf_url=url_for('download_file', filename=os.path.basename(output_filename))
        )

    # GET request part remains unchanged
    x_val = int(signer['x']) if signer['x'] is not None else None
    y_val = int(signer['y']) if signer['y'] is not None else None
    page_val = int(signer['page']) if signer['page'] is not None else 0

    pdf_filename = None
    if 'pdf_filename' in signer.keys() and signer['pdf_filename']:
        pdf_filename = signer['pdf_filename']
    elif 'pdf_path' in signer.keys() and signer['pdf_path']:
        pdf_filename = os.path.basename(signer['pdf_path'])

    preview_image = None
    if pdf_filename:
        preview_name = os.path.splitext(pdf_filename)[0] + '_preview.jpg'
        preview_full = os.path.join('static', preview_name)
        if os.path.exists(preview_full):
            preview_image = preview_name
        else:
            logging.warning(f"Preview image not found: {preview_full} -- template will receive preview_image=None")

    return render_template(
        'sign.html',
        signer=signer,
        signer_name=signer_name,
        x=x_val,
        y=y_val,
        page=page_val,
        preview_image=preview_image
    )


# Home
@app.route('/')
def home():
    return '<h2>Welcome</h2><a href="/admin">Go to Admin Panel</a>'

# Admin panel
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    import logging
    logger = logging.getLogger(__name__)

    if request.method == 'POST':
        pdf_file = request.files.get('pdf')
        if not pdf_file or not pdf_file.filename.lower().endswith('.pdf'):
            return "❌ Please upload a valid PDF."

        pdf_filename = secure_filename(pdf_file.filename)
        pdf_path = os.path.join(app.config['PDF_UPLOAD_FOLDER'], pdf_filename)
        pdf_file.save(pdf_path)

        try:
            # Check if preview image already exists
            preview_name = os.path.splitext(pdf_filename)[0] + '_preview.jpg'
            preview_path = os.path.join('static', preview_name)

            if not os.path.exists(preview_path):
                logger.info(f"Generating preview for: {pdf_filename}")
                POPPLER_PATH = '/usr/bin'  # Adjust if necessary
                images = convert_from_path(pdf_path, first_page=1, last_page=1, poppler_path=POPPLER_PATH)
                images[0].save(preview_path, 'JPEG')
                logger.info(f"Preview saved at {preview_path}")
            else:
                logger.info(f"Preview already exists at {preview_path}")

        except Exception as e:
            logger.error(f"Error converting PDF to preview image: {e}")
            return f"❌ Error converting PDF to image: {e}"

        return redirect(url_for('set_signature_positions', pdf=pdf_filename))

    return render_template('admin.html')


@app.route('/set_positions/<pdf>', methods=['GET', 'POST'])
def set_signature_positions(pdf):
    import logging
    logger = logging.getLogger(__name__)
    pdf_filename = secure_filename(pdf)
    pdf_path = os.path.join(app.config['PDF_UPLOAD_FOLDER'], pdf_filename)
    preview_name = os.path.splitext(pdf_filename)[0] + '_preview.jpg'
    preview_path = os.path.join('static', preview_name)

    if request.method == 'POST':
        try:
            name = request.form['name'].strip()
            email = request.form['email'].strip()
            x = int(request.form['x'])
            y = int(request.form['y'])
        except (KeyError, ValueError) as e:
            logger.error(f"Invalid form data: {e}")
            return "❌ Invalid input data", 400

        conn = sqlite3.connect('signers.db')
        c = conn.cursor()

        # Get next signer ID for this PDF
        c.execute('SELECT MAX(CAST(id AS INTEGER)) FROM signers WHERE pdf_filename = ?', (pdf_filename,))
        row = c.fetchone()
        next_id = (row[0] or 0) + 1
        signer_id = str(next_id)

        # Insert signer record
        c.execute('INSERT INTO signers (id, name, email, x, y, pdf_filename) VALUES (?, ?, ?, ?, ?, ?)',
                  (signer_id, name, email, x, y, pdf_filename))
        conn.commit()
        conn.close()

        # Generate signer link with correct route and normalized name
        base_url = request.host_url.rstrip('/')
        signer_name_for_url = name.lower().replace(' ', '_')
        signing_link = f"{base_url}/sign_document/{signer_name_for_url}"
        logger.info(f"✅ Signing link for {name} ({email}): {signing_link}")

        print(f"Signer link: {signing_link}")  # For logs

        return '', 204  # Silent success for JS frontend

    # GET: Show signer management page
    conn = sqlite3.connect('signers.db')
    c = conn.cursor()
    c.execute('SELECT id, name, email FROM signers WHERE pdf_filename = ?', (pdf_filename,))
    signers = c.fetchall()
    conn.close()

    base_url = request.host_url.rstrip('/')
    signers_with_links = [
        {
            'id': row[0],
            'name': row[1],
            'email': row[2],
            'link': f"{base_url}/sign_document/{row[1].lower().replace(' ', '_')}"
        }
        for row in signers
    ]

    # Ensure preview image exists
    if not os.path.exists(preview_path):
        try:
            POPPLER_PATH = '/usr/bin'
            images = convert_from_path(pdf_path, first_page=1, last_page=1, poppler_path=POPPLER_PATH)
            images[0].save(preview_path, 'JPEG')
            logger.info(f"Preview generated at {preview_path}")
        except Exception as e:
            logger.error(f"Error generating preview image: {e}")
            return f"❌ Error generating preview: {e}"

    return render_template('click_to_place.html', pdf=pdf_filename, signers=signers_with_links)


@app.route('/merge/<pdf_filename>', methods=['POST'])
def merge_route(pdf_filename):
    downloads_dir = str(Path.home() / "Downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    conn = sqlite3.connect('signers.db')
    c = conn.cursor()
    c.execute('SELECT x, y, signature_path FROM signers WHERE pdf_filename=? AND has_signed=1', (pdf_filename,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        flash("❌ No signed signatures to merge yet.")
        return redirect(url_for('get_signers', pdf_filename=pdf_filename))

    signers = [{"x": x, "y": y, "signature_path": sig} for x, y, sig in rows]

    try:
        # Convert to (x, y, path) tuples for merge_pdf_signatures
        signer_data = [(s["x"], s["y"], s["signature_path"]) for s in signers]

        output_path = merge_pdf_signatures(pdf_filename, signer_data, output_folder='signed')
        filename = os.path.basename(output_path)
        download_url = url_for('download_file', filename=filename)
        sms = "✅ Signatures successfully merged into the PDF."
        return render_template("merge_success.html", message=sms, download_url=download_url)
    except Exception as e:
        logging.exception("❌ Merge failed:")
        flash(f"❌ Merge failed: {str(e)}")
        return redirect(url_for('get_signers', pdf_filename=pdf_filename))
 


@app.route('/set_merge_folder', methods=['POST'])
def set_merge_folder():
    uploaded_files = request.files.getlist('merge_folder')
    if uploaded_files:
        # Get parent folder from first uploaded file
        first_file = uploaded_files[0]
        folder_path = os.path.dirname(first_file.filename)  # this gets the client-side path
        session['merge_folder'] = folder_path  # store in session (or use a more persistent method)
    return redirect(request.referrer or url_for('admin_panel'))


@app.route('/done/<pdf>')
def done_placing_signers(pdf):
    conn = sqlite3.connect('signers.db')
    c = conn.cursor()
    c.execute('SELECT name, email, x, y, has_signed FROM signers WHERE pdf_filename = ?', (pdf,))
    signers = c.fetchall()
    conn.close()

    return render_template('signer_summary.html', pdf=pdf, signers=signers)


def merge_pdf_signatures(base_pdf_path, signers, output_folder='signed'):
    import fitz  # PyMuPDF
    import os
    import logging
    from datetime import datetime
    from PIL import Image

    logger = logging.getLogger(__name__)

    # 🛠 Fix accidental double 'uploads/uploads'
    if base_pdf_path.startswith("uploads/uploads/"):
        logger.warning(f"[merge_pdf_signatures] Fixing double uploads in path: {base_pdf_path}")
        base_pdf_path = base_pdf_path.replace("uploads/uploads/", "uploads/", 1)    

    # Ensure absolute path to the PDF
    upload_dir = app.config.get('UPLOAD_FOLDER', 'uploads')
    # Only prepend upload_dir if path is not absolute AND not already starting with uploads/
    if not os.path.isabs(base_pdf_path) and not base_pdf_path.startswith(upload_dir + "/"):
        base_pdf_path = os.path.join(upload_dir, base_pdf_path)

    logger.info(f"📄 Resolving PDF path: {base_pdf_path}")

    if not os.path.exists(base_pdf_path):
        logger.error(f"❌ PDF file not found: {base_pdf_path}")
        raise FileNotFoundError(f"PDF not found: {base_pdf_path}")

    # Open PDF
    doc = fitz.open(base_pdf_path)

    # Determine preview image path
    img_preview_name = os.path.basename(base_pdf_path).replace(".pdf", "_preview.png")
    img_preview_path = os.path.join(os.path.dirname(base_pdf_path), img_preview_name)

    # ✅ Regenerate preview image if missing
    if not os.path.exists(img_preview_path):
        logger.warning(f"⚠️ Preview image not found. Attempting to regenerate: {img_preview_path}")
        try:
            from pdf2image import convert_from_path
            POPPLER_PATH = '/usr/bin'  # Adjust for your environment
            images = convert_from_path(base_pdf_path, first_page=1, last_page=1, poppler_path=POPPLER_PATH)
            images[0].save(img_preview_path, 'PNG')
            logger.info(f"✅ Preview image regenerated: {img_preview_path}")
        except Exception as e:
            logger.error(f"❌ Failed to regenerate preview image: {e}")
            raise FileNotFoundError(f"Could not regenerate preview image: {img_preview_path}")

    # Load preview to get scaling reference
    img = Image.open(img_preview_path)
    img_width, img_height = img.size
    points_offset = 5

    # Loop through all signers
    for signer in signers:
        page_number = signer['page']
        x = signer['x']
        y = signer['y']
        sig_path = signer['signature_path']
        sig_width = signer['sig_width']
        sig_height = signer['sig_height']

        page = doc[page_number]
        page_width = page.rect.width
        page_height = page.rect.height

        # Convert pixel coords to PDF points
        x_pdf = x * page_width / img_width
        y_pdf = y * page_height / img_height

        # Signature size in PDF points
        sig_width_pts = sig_width * page_width / img_width
        sig_height_pts = sig_height * page_height / img_height

        # Place signature
        sig_rect = fitz.Rect(
            x_pdf,
            y_pdf - sig_height_pts,
            x_pdf + sig_width_pts,
            y_pdf
        )
        page.insert_image(sig_rect, filename=sig_path)
        logger.info(f"🖊️ Signature inserted at: {sig_rect}")

        # Add date to the right of signature
        current_date = datetime.now().strftime("%B %d, %Y")
        date_x = x_pdf + sig_width_pts + points_offset
        date_y = y_pdf + sig_height_pts / 2

        date_box_width = 100
        date_box_height = 20
        date_rect = fitz.Rect(date_x, date_y, date_x + date_box_width, date_y + date_box_height)

        page.insert_textbox(
            date_rect,
            current_date,
            fontsize=10,
            fontname="helv",
            color=(0, 0, 0),
            align=0
        )
        logger.info(f"📅 Date inserted at rect: {date_rect}")

    # Save final signed PDF
    os.makedirs(output_folder, exist_ok=True)
    output_filename = os.path.join(output_folder, os.path.basename(base_pdf_path))
    doc.save(output_filename)
    doc.close()
    logger.info(f"✅ Final signed PDF saved to: {output_filename}")

    return output_filename


@app.route('/download/<filename>')
def download_signed_pdf(filename):
    return send_from_directory('signed', filename, as_attachment=True)

@app.route('/success')
def success():
    pdf_filename = request.args.get('file')  # example: 'signed_output.pdf'
    pdf_url = url_for('static', filename=f'signed/{pdf_filename}')
    return render_template('success.html', pdf_url=pdf_url)

# API: List of signers
@app.route('/signers')
def get_signers():
    conn = sqlite3.connect('signers.db')
    c = conn.cursor()
    c.execute('SELECT id, name, email, x, y FROM signers')
    signers = [{'id': row[0], 'name': row[1], 'email': row[2], 'x': row[3], 'y': row[4]} for row in c.fetchall()]
    conn.close()
    return jsonify(signers)

# API: Delete signer
@app.route('/delete_signer/<signer_id>', methods=['POST'])
def delete_signer(signer_id):
    conn = sqlite3.connect('signers.db')
    c = conn.cursor()
    c.execute('DELETE FROM signers WHERE id = ?', (signer_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route("/api/signer-statuses/<pdf_filename>")
def signer_statuses_api(pdf_filename):
    import sqlite3
    from flask import jsonify

    conn = sqlite3.connect("signers.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT name, email, 
               COALESCE(has_signed, 0) AS has_signed
        FROM signers
        WHERE pdf_filename = ?
    """, (pdf_filename,))
    rows = cur.fetchall()
    conn.close()

    result = []
    for row in rows:
        signed = bool(row["has_signed"])
        result.append({
            "name": row["name"],
            "email": row["email"],
            "has_signed": signed,
            "class": "signed" if signed else "not-signed"
        })

    return jsonify(result)


@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory('signed', filename, as_attachment=True)

def init_db():
    conn = sqlite3.connect('signers.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS signers (
            id TEXT,
            name TEXT,
            email TEXT,
            x INTEGER,
            y INTEGER,
            pdf_filename TEXT,
            signature_path TEXT,
            has_signed INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

with app.test_request_context():
    for rule in app.url_map.iter_rules():
        print(rule, "->", "methods:", ",".join(rule.methods))

# temporary route
@app.errorhandler(404)
def page_not_found(e):
    app.logger.warning(f"404: {request.method} {request.path}")
    return "Not Found", 404
        

if __name__ == '__main__':
    init_db()

    USE_NGROK = False  # Change to True if you want ngrok to run

    if USE_NGROK and os.environ.get("RENDER") is None:
        conf.get_default().config_path = r"C:/Users/cerilo.cabacoy/AppData/Local/ngrok/ngrok.yml"
        public_url = ngrok.connect(10000)
        print(f"🔗 Public URL: {public_url}")
    else:
        print("🚫 Ngrok is disabled.")

    try:
        app.run(host="0.0.0.0", port=10000, debug=True)
    finally:
        # Kill any running ngrok process
        try:
            subprocess.run(["taskkill", "/F", "/IM", "ngrok.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("✅ Ngrok process terminated.")
        except Exception as e:
            print(f"⚠️ Could not terminate ngrok: {e}")

