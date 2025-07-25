from flask import Flask, request, render_template, redirect, url_for
import os
import sqlite3
import uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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

        # Process signer info from form
        names = request.form.getlist('name[]')
        xs = request.form.getlist('x[]')
        ys = request.form.getlist('y[]')

        # Insert signers into database
        conn = sqlite3.connect('signers.db')
        c = conn.cursor()

        for name, x, y in zip(names, xs, ys):
            signer_id = str(uuid.uuid4())
            c.execute('''
                INSERT INTO signers (id, name, x, y)
                VALUES (?, ?, ?, ?)
            ''', (signer_id, name.strip(), int(x), int(y)))

        conn.commit()
        conn.close()

        return f"✅ PDF uploaded and {len(names)} signers added successfully!"

    return render_template('admin.html')

if __name__ == '__main__':
    # Run on port 8080 for compatibility with your system
    app.run(debug=True, port=8080)
