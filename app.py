from flask import Flask, render_template, request, redirect, url_for, flash, send_file
import sqlite3, os
from datetime import datetime
from werkzeug.utils import secure_filename
import bleach

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
app.secret_key = 'aplikasi-untuk-shanaz'


ALLOWED_TAGS = ['p', 'br', 'b', 'i', 'u', 'em', 'strong', 'ul', 'ol', 'li', 'blockquote', 'span', 'img']
ALLOWED_ATTRIBUTES = {
    'span': ['style'],
    'p': ['style'],
    'ul': ['style'],
    'li': ['style'],
    'img': ['src', 'alt', 'style']
}


def get_db_connection():
    conn = sqlite3.connect('food.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS entries (
        id INTEGER PRIMARY KEY,
        title TEXT,
        description TEXT,
        food_type TEXT,
        timestamp TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY,
        entry_id INTEGER,
        filename TEXT
    )''')
    conn.close()

@app.before_request
def before_request():
    if not hasattr(app, 'db_initialized'):
        init_db()
        app.db_initialized = True

@app.route('/')
def index():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM entries ORDER BY timestamp DESC")
    entries = c.fetchall()
    conn.close()
    return render_template('index.html', entries=entries, get_images=get_images)

def get_images(entry_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM images WHERE entry_id=?", (entry_id,))
    images = c.fetchall()
    conn.close()
    return images

@app.route('/add', methods=['GET', 'POST'])
def add_entry():
    if request.method == 'POST':
        title = request.form['title']
        description_raw = request.form['description']
        food_type = request.form['food_type']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Sanitize rich text HTML
        description = bleach.clean(description_raw, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO entries (title, description, food_type, timestamp) VALUES (?, ?, ?, ?)",
                  (title, description, food_type, timestamp))
        entry_id = c.lastrowid

        for file in request.files.getlist('images'):
            if file and file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                c.execute("INSERT INTO images (entry_id, filename) VALUES (?, ?)", (entry_id, filename))

        conn.commit()
        conn.close()
        flash('Entry added successfully!')
        return redirect(url_for('index'))
    return render_template('add_entry.html')

@app.route('/edit/<int:entry_id>', methods=['GET', 'POST'])
def edit_entry(entry_id):
    conn = get_db_connection()
    c = conn.cursor()

    if request.method == 'POST':
        title = request.form['title']
        description_raw = request.form['description']
        food_type = request.form['food_type']

        # Sanitize updated description
        description = bleach.clean(description_raw, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)

        c.execute("UPDATE entries SET title=?, description=?, food_type=? WHERE id=?",
                  (title, description, food_type, entry_id))
        conn.commit()
        conn.close()
        flash('Entry updated successfully!')
        return redirect(url_for('index'))

    c.execute("SELECT * FROM entries WHERE id=?", (entry_id,))
    entry = c.fetchone()
    conn.close()
    return render_template('edit_entry.html', entry=entry)

@app.route('/delete/<int:entry_id>', methods=['POST'])
def delete_entry(entry_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM entries WHERE id=?", (entry_id,))
    c.execute("DELETE FROM images WHERE entry_id=?", (entry_id,))
    conn.commit()
    conn.close()
    flash('Entry deleted!')
    return redirect(url_for('index'))

@app.route('/calendar')
def calendar_view():
    return render_template('calendar.html')

@app.route('/stats')
def stats():
    conn = get_db_connection()
    cursor = conn.execute('SELECT food_type, COUNT(*) as count FROM entries GROUP BY food_type')
    stats_data = cursor.fetchall()
    conn.close()

    stats = {row['food_type']: row['count'] for row in stats_data}
    return render_template('stats.html', stats=stats)



@app.route('/export')
def export_csv():
    import csv
    conn = get_db_connection()
    with open("export.csv", "w", newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Title", "Description", "Type", "Timestamp"])
        for row in conn.execute("SELECT * FROM entries"):
            writer.writerow(row)
    conn.close()
    return send_file("export.csv", as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
