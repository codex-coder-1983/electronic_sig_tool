from flask import Flask, request, render_template, redirect, url_for, jsonify
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
import os
import sqlite3
import uuid
from pdf2image import convert_from_path
import fitz  # PyMuPDF
import smtplib
from email.message import EmailMessage
from PIL import Image

app = Flask(__name__)

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
    if request.method == 'POST':
        pdf_file = request.files['pdf']
        if not pdf_file or not pdf_file.filename.endswith('.pdf'):
            return "Please upload a valid PDF."

        pdf_filename = secure_filename(pdf_file.filename)
        pdf_path = os.path.join(app.config['PDF_UPLOAD_FOLDER'], pdf_filename)
        pdf_file.save(pdf_path)

        try:
            POPPLER_PATH = r'C:\Poppler\poppler-24.08.0\Library\bin'
            images = convert_from_path(pdf_path, first_page=1, last_page=1, poppler_path=POPPLER_PATH)
            preview_name = os.path.splitext(pdf_filename)[0] + '_preview.jpg'
            preview_path = os.path.join('static', preview_name)
            images[0].save(preview_path, 'JPEG')
        except Exception as e:
            return f"❌ Error converting PDF to image: {e}"

        return redirect(url_for('set_signature_positions', pdf=pdf_filename))

    return render_template('admin.html')

# Signature placement
@app.route('/set_positions/<pdf>', methods=['GET', 'POST'])
def set_signature_positions(pdf):
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        x = int(request.form['x'])
        y = int(request.form['y'])
        signer_id = str(uuid.uuid4())

        conn = sqlite3.connect('signers.db')
        c = conn.cursor()
        c.execute('INSERT INTO signers (id, name, email, x, y, pdf_filename) VALUES (?, ?, ?, ?, ?, ?)',
                  (signer_id, name, email, x, y, pdf))
        conn.commit()
        conn.close()

        return '', 204

    conn = sqlite3.connect('signers.db')
    c = conn.cursor()
    c.execute('SELECT id, name, email FROM signers')
    signers = c.fetchall()
    conn.close()
    return render_template('click_to_place.html', pdf=pdf, signers=signers)

@app.route('/sign/<signer_id>', methods=['GET', 'POST'])
def sign_document(signer_id):
    import sqlite3
    import os
    from flask import request, render_template
    from werkzeug.utils import secure_filename
    from PIL import Image
    import fitz  # PyMuPDF

    # Fetch signer info (x, y, pdf_filename)
    conn = sqlite3.connect('signers.db')
    c = conn.cursor()
    c.execute('SELECT x, y, pdf_filename FROM signers WHERE id=?', (signer_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return '❌ Signer not found', 404

    x_raw, y_raw, pdf_filename = row
    preview_name = os.path.splitext(pdf_filename)[0] + '_preview.jpg'

    if request.method == 'POST':
        file = request.files['signature']
        filename = f"{signer_id}_{secure_filename(file.filename)}"
        signature_path = os.path.join('static/signatures', filename)
        file.save(signature_path)

        # Update DB
        conn = sqlite3.connect('signers.db')
        c = conn.cursor()
        c.execute('UPDATE signers SET signature_path=?, has_signed=1 WHERE id=?',
                  (signature_path, signer_id))
        conn.commit()
        conn.close()

        # Prepare PDF merge
        original_pdf_path = os.path.join('uploads', pdf_filename)
        output_pdf_path = os.path.join('signed', f'signed_{pdf_filename}')
        os.makedirs('signed', exist_ok=True)

        try:
            doc = fitz.open(original_pdf_path)
            page = doc[0]
            page_width = page.rect.width
            page_height = page.rect.height

            # Load preview image for scaling
            preview_path = os.path.join('static', preview_name)
            preview_image = Image.open(preview_path)
            img_width, img_height = preview_image.size

            scale_x = page_width / img_width
            scale_y = page_height / img_height

            # Convert coordinates from image to PDF space
            x_pdf = float(x_raw) * scale_x
            y_pdf = (img_height - float(y_raw)) * scale_y  # Invert Y

            # Load signature image
            sig_img = Image.open(signature_path)
            sig_width_px, sig_height_px = sig_img.size

            sig_width_pts = sig_width_px * scale_x
            sig_height_pts = sig_height_px * scale_y

            # Center signature on clicked point
            x_pdf -= sig_width_pts / 2
            y_pdf -= sig_height_pts / 2

            # Clamp within page
            x_pdf = max(0, min(x_pdf, page_width - sig_width_pts))
            y_pdf = max(0, min(y_pdf, page_height - sig_height_pts))

            rect = fitz.Rect(x_pdf, y_pdf, x_pdf + sig_width_pts, y_pdf + sig_height_pts)
            page.insert_image(rect, filename=signature_path)
            doc.save(output_pdf_path)
            doc.close()

            print(f"✅ Signed PDF saved at: {output_pdf_path}")
            return '✅ Signature uploaded and merged into PDF!'

        except Exception as e:
            print(f"❌ ERROR merging signature: {e}")
            return f'❌ Failed to merge signature: {e}', 500

    # GET request: show upload form with red dot
    return render_template(
        'sign.html',
        signer_id=signer_id,
        x=float(x_raw),
        y=float(y_raw),
        preview_image=preview_name
    )


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

# Email sending
def send_signing_email(to_email, signer_id):
    msg = EmailMessage()
    msg['Subject'] = 'Please Sign the Document'
    msg['From'] = EMAIL
    msg['To'] = to_email
    link = f'http://localhost:8080/sign/{signer_id}'
    msg.set_content(f"Hello,\n\nPlease sign the document at: {link}\n\nThank you.")
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(EMAIL, PASSWORD)
        smtp.send_message(msg)

@app.route('/send_emails')
def send_emails():
    conn = sqlite3.connect('signers.db')
    c = conn.cursor()
    c.execute('SELECT id, name, email FROM signers')
    signers = c.fetchall()
    conn.close()
    for signer_id, name, email in signers:
        send_signing_email(email, signer_id)
    return '✅ Emails sent successfully!'

if __name__ == '__main__':
    app.run(debug=True, port=8080)
