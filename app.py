from flask import Flask, request, render_template, redirect, url_for, jsonify, send_from_directory, session, flash
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

##logging.basicConfig(
##    level=logging.INFO,  # or logging.DEBUG for more detail
##    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
##    datefmt='%Y-%m-%d %H:%M:%S'
##)

load_dotenv()  # Loads variables from .env file
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

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

        # Optionally, log the signer link
        base_url = request.host_url.strip('/')
        signing_link = f"{base_url}/sign/{pdf_filename}/{signer_id}"
        logger.info(f"✅ Signing link for {name} ({email}): {signing_link}")

        return '', 204  # Silent success for JS frontend

    # 🔁 GET: Show signer management page
    conn = sqlite3.connect('signers.db')
    c = conn.cursor()
    c.execute('SELECT id, name, email FROM signers WHERE pdf_filename = ?', (pdf_filename,))
    signers = c.fetchall()
    conn.close()

    # Generate signing links for each signer
    base_url = request.host_url.strip('/')
    signers_with_links = [
        {
            'id': row[0],
            'name': row[1],
            'email': row[2],
            'link': f"{base_url}/sign/{pdf_filename}/{row[0]}"
        }
        for row in signers
    ]

    # 🖼 Ensure preview exists
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



@app.route('/sign/<pdf>/<signer_id>', methods=['GET', 'POST'])
def sign_document(pdf, signer_id):
    import logging
    logger = logging.getLogger(__name__)

    # Fetch signer info
    conn = sqlite3.connect('signers.db')
    c = conn.cursor()
    c.execute('SELECT x, y, has_signed FROM signers WHERE id=? AND pdf_filename=?', (signer_id, pdf))
    row = c.fetchone()
    conn.close()

    if not row:
        return '❌ Signer not found', 404

    x_raw, y_raw, row_has_signed = row

    if row_has_signed:
        return '✅ You have already signed this document.', 400

    # Reconstruct preview image path
    preview_name = os.path.splitext(pdf)[0] + '_preview.jpg'
    preview_path = os.path.join('static', preview_name)

    # Fallback: regenerate preview if it doesn’t exist
    if not os.path.exists(preview_path):
        try:
            logger.warning(f"Preview image not found at {preview_path}. Regenerating from PDF.")
            pdf_path = os.path.join(app.config['PDF_UPLOAD_FOLDER'], pdf)
            POPPLER_PATH = '/usr/bin'  # Adjust if needed
            images = convert_from_path(pdf_path, first_page=1, last_page=1, poppler_path=POPPLER_PATH)
            images[0].save(preview_path, 'JPEG')
            logger.info(f"Preview regenerated at {preview_path}.")
        except Exception as e:
            logger.error(f"Error regenerating preview image: {e}")
            return f"❌ Failed to generate preview image: {e}", 500

    if request.method == 'POST':
        if 'signature' not in request.files or request.files['signature'].filename == '':
            return '❌ No signature file uploaded', 400

        file = request.files['signature']
        base_name = os.path.splitext(pdf)[0]
        filename = f"{base_name}_signer{signer_id}.png"
        signature_path = os.path.join('static/signatures', filename)

        # Save uploaded signature
        file.save(signature_path)

        # Resize signature
        with Image.open(signature_path) as img:
            target_width = xdim  # Make sure xdim is defined globally
            w_percent = target_width / float(img.size[0])
            target_height = int(float(img.size[1]) * w_percent)
            resized = img.resize((target_width, target_height), Image.LANCZOS)
            resized.save(signature_path)

        # Update database
        conn = sqlite3.connect('signers.db')
        c = conn.cursor()
        c.execute('UPDATE signers SET signature_path=?, has_signed=1 WHERE id=? AND pdf_filename=?',
                  (signature_path, signer_id, pdf))
        conn.commit()
        conn.close()

        # Merge into a signed PDF
        signer_data = {
            "x": x_raw,
            "y": y_raw,
            "signature_path": signature_path
        }

        output_filename = merge_signatures_into_pdf(pdf, signers=[signer_data])
        download_url = url_for('download_file', filename=output_filename)

        return render_template('merge_success.html', download_url=download_url)

    # GET request
    return render_template(
        'sign.html',
        signer_id=signer_id,
        x=float(x_raw),
        y=float(y_raw),
        preview_image=preview_name,
        message='',
        download_url=None
    )


@app.route('/merge/<pdf_filename>', methods=['POST'])
def merge_route(pdf_filename):
    # Server's Downloads folder
    downloads_dir = str(Path.home() / "Downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    # Get all signed signatures
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
        output_path = merge_signatures_into_pdf(pdf_filename, signers, output_folder='signed')
        filename = os.path.basename(output_path)
        download_url = url_for('download_file', filename=filename)
        sms = "✅ Signatures successfully merged into the PDF."
        return render_template("merge_success.html", message=sms, download_url=url_for('download_file', filename=os.path.basename(output_path)))
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


def merge_signatures_into_pdf(pdf_path, signers, output_folder='signed'):
    import fitz  # PyMuPDF
    import os
    import logging
    from datetime import datetime
    from PIL import Image

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    try:
        upload_dir = app.config.get('UPLOAD_FOLDER', 'uploads')
        base_pdf_path = os.path.join(upload_dir, pdf_path)
        logger.info(f"Opening PDF from path: {base_pdf_path}")
        doc = fitz.open(base_pdf_path)
        page = doc[0]  # Assume single-page PDF

        page_width, page_height = page.rect.width, page.rect.height
        logger.info(f"Page size: width={page_width}, height={page_height}")

        img_preview_name = os.path.basename(pdf_path).replace(".pdf", "_preview.png")
        img_preview_path = os.path.join(upload_dir, img_preview_name)

        if not os.path.exists(img_preview_path):
            logger.error(f"Preview image not found: {img_preview_path}")
            raise FileNotFoundError(f"Preview image not found: {img_preview_path}")

        img = Image.open(img_preview_path)
        img_width, img_height = img.size
        scale_x = page_width / img_width
        scale_y = page_height / img_height
        points_offset = 5

        for signer in signers:
            x_raw, y_raw, signature_path = signer["x"], signer["y"], signer["signature_path"]
            x_pdf = float(x_raw) * scale_x
            y_pdf = (img_height - float(y_raw)) * scale_y

            sig_img = Image.open(signature_path)
            sig_width_px, sig_height_px = sig_img.size
            sig_width_pts = sig_width_px * scale_x
            sig_height_pts = sig_height_px * scale_y

            x_pdf = max(0, min(x_pdf - sig_width_pts / 2, page_width - sig_width_pts))
            y_pdf = max(0, min(y_pdf - sig_height_pts / 2, page_height - sig_height_pts))

            rect = fitz.Rect(x_pdf, y_pdf, x_pdf + sig_width_pts, y_pdf + sig_height_pts)

            flip_matrix = fitz.Matrix(1, -1).preTranslate(0, -2 * y_pdf - sig_height_pts)
            page.insert_image(rect, filename=signature_path, matrix=flip_matrix)
            logger.info(f"Inserted signature at: {rect}")

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
            logger.info(f"Inserted date text: {current_date}")

        os.makedirs(output_folder, exist_ok=True)
        output_filename = os.path.join(output_folder, os.path.basename(base_pdf_path))
        doc.save(output_filename)
        doc.close()
        logger.info(f"✅ PDF saved to: {output_filename}")
        return output_filename

    except Exception as e:
        logger.exception("❌ Error while merging signatures into PDF")
        raise  # Optional: re-raise to propagate the error to the calling function or Flask route


def merge_pdf_signatures(base_pdf_path, signers, output_folder='signed'):
    import fitz  # PyMuPDF
    import os
    import logging
    from datetime import datetime
    from PIL import Image

    logger = logging.getLogger(__name__)

    doc = fitz.open(base_pdf_path)
    page = doc[0]  # Single-page

    page_width, page_height = page.rect.width, page.rect.height
    logger.info(f"Page size: width={page_width}, height={page_height}")

    img_preview_name = pdf_path.replace(".pdf", "_preview.png")
    img_preview_name = os.path.basename(base_pdf_path).replace(".pdf", "_preview.png")
    upload_dir = os.path.dirname(base_pdf_path)    
    img_preview_path = os.path.join(upload_dir, img_preview_name)
    img = Image.open(img_preview_path)
    
    img_width, img_height = img.size
    scale_x = page_width / img_width
    scale_y = page_height / img_height
    points_offset = 5

    for x_raw, y_raw, signature_path in signers:
        x_pdf = float(x_raw) * scale_x
        y_pdf = (img_height - float(y_raw)) * scale_y

        sig_img = Image.open(signature_path)
        sig_width_px, sig_height_px = sig_img.size
        sig_width_pts = sig_width_px * scale_x
        sig_height_pts = sig_height_px * scale_y

        x_pdf = max(0, min(x_pdf - sig_width_pts / 2, page_width - sig_width_pts))
        y_pdf = max(0, min(y_pdf - sig_height_pts / 2, page_height - sig_height_pts))

        rect = fitz.Rect(x_pdf, y_pdf, x_pdf + sig_width_pts, y_pdf + sig_height_pts)

        # Flip signature image vertically
        flip_matrix = fitz.Matrix(1, -1).preTranslate(0, -2 * y_pdf - sig_height_pts)
        page.insert_image(rect, filename=signature_path, matrix=flip_matrix)
        logger.info(f"🖊️ Signature inserted at: {rect}")

        # Insert date
        current_date = datetime.now().strftime("%B %d, %Y")
        date_x = x_pdf + sig_width_pts + points_offset
        date_y = y_pdf + sig_height_pts / 2

        date_box_width = 100
        date_box_height = 20
        date_rect = fitz.Rect(date_x, date_y, date_x + date_box_width, date_y + date_box_height)

        logger.info(f"📍 Inserting date at rect: {date_rect}")

        page.insert_textbox(
            date_rect,
            current_date,
            fontsize=10,
            fontname="helv",
            color=(0, 0, 0),
            align=0
        )
        logger.info("📅 Date inserted upright.")

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
    conn = sqlite3.connect("signers.db")
    cur = conn.cursor()
    cur.execute("SELECT name, email, has_signed FROM signers WHERE pdf_filename = ?", (pdf_filename,))
    rows = cur.fetchall()
    conn.close()

    # Combine rows by name: mark as signed if any instance is signed
    status_map = {}
    for name, email, has_signed in rows:
        if name not in status_map:
            status_map[name] = has_signed
        else:
            status_map[name] = status_map[name] or has_signed  # True if any instance is signed

    return jsonify([
        {
            "name": name,
            "email": email,
            "status": "Signed" if has_signed else "Pending",
            "class": "signed" if has_signed else "not-signed"
        }
        for name, email, has_signed in rows
    ])

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


from pyngrok import ngrok, conf

if __name__ == '__main__':
    init_db()
    
    # Only run ngrok in local environment
    if os.environ.get("RENDER") is None:
        from pyngrok import ngrok, conf
        conf.get_default().config_path = "C:/Users/cerilo.cabacoy/AppData/Local/ngrok/ngrok.yml"
        public_url = ngrok.connect(10000)
        print(f"🔗 Public URL: {public_url}")

    app.run(host="0.0.0.0", port=10000, debug=True)

