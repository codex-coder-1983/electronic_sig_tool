from flask import Flask, request, render_template, redirect, url_for
import os
import sqlite3
import uuid
from werkzeug.utils import secure_filename
from pdf2image import convert_from_path

app = Flask(__name__)

# Configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('static', exist_ok=True)

# Home page
@app.route('/')
def home():
    return '<h2>Welcome</h2><a href="/admin">Go to Admin Panel</a>'

# Admin page to upload PDF and add signers
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        # Save uploaded PDF
        pdf_file = request.files['pdf']
        if not pdf_file or not pdf_file.filename.endswith('.pdf'):
            return "Please upload a valid PDF."

        pdf_filename = secure_filename(pdf_file.filename)
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename)
        pdf_file.save(pdf_path)

        # Convert first page to image preview
        POPPLER_PATH = r'C:\Poppler\poppler-24.08.0\Library\bin'  # Replace with your actual path
        print(f"🔍 Converting {pdf_path} using Poppler from {POPPLER_PATH}")

        try:
            images = convert_from_path(pdf_path, first_page=1, last_page=1, poppler_path=POPPLER_PATH)
            print("✅ PDF converted to image")

            # Save preview image
            os.makedirs('static', exist_ok=True)
            images[0].save(os.path.join('static', 'preview.jpg'), 'JPEG')
            print("✅ Image saved to static/preview.jpg")
        except Exception as e:
            print(f"❌ Error during conversion: {e}")
    
        # Redirect to visual placement
        return redirect(url_for('set_signature_positions', pdf=pdf_filename))

    return render_template('admin.html')

@app.route('/set_positions/<pdf>', methods=['GET', 'POST'])
def set_signature_positions(pdf):
    if request.method == 'POST':
        name = request.form['name']
        x = int(request.form['x'])
        y = int(request.form['y'])

        signer_id = str(uuid.uuid4())

        conn = sqlite3.connect('signers.db')
        c = conn.cursor()
        c.execute('INSERT INTO signers (id, name, x, y) VALUES (?, ?, ?, ?)', (signer_id, name, x, y))
        conn.commit()
        conn.close()

        return f'Signer {name} saved at X={x}, Y={y}. <a href="">Add another</a>'

    return render_template('click_to_place.html', pdf=pdf)


from flask import jsonify

@app.route('/signers')
def get_signers():
    conn = sqlite3.connect('signers.db')
    c = conn.cursor()
    c.execute('SELECT id, name, x, y FROM signers')
    rows = c.fetchall()
    conn.close()
    return jsonify([{'id': r[0], 'name': r[1], 'x': r[2], 'y': r[3]} for r in rows])


@app.route('/delete_signer/<signer_id>', methods=['POST'])
def delete_signer(signer_id):
    conn = sqlite3.connect('signers.db')
    c = conn.cursor()
    c.execute('DELETE FROM signers WHERE id = ?', (signer_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


if __name__ == '__main__':
    # Run on port 8080 for compatibility with your system
    app.run(debug=True, port=8080)
