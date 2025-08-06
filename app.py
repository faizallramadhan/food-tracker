from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
import sqlite3, os, base64, uuid
from datetime import datetime
from werkzeug.utils import secure_filename
import bleach
import re

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

def get_images(entry_id):
    print(f"\n=== DEBUG get_images for entry_id {entry_id} ===")
    conn = get_db_connection()
    c = conn.cursor()
    
    # First, let's see what's in the images table
    c.execute("SELECT COUNT(*) as total FROM images")
    total_images = c.fetchone()
    print(f"Total images in database: {total_images['total']}")
    
    # Now get images for this specific entry
    c.execute("SELECT * FROM images WHERE entry_id=?", (entry_id,))
    images = c.fetchall()
    print(f"Images found for entry {entry_id}: {len(images)}")
    
    # Print details of each image
    for i, img in enumerate(images):
        print(f"  Image {i}: ID={img['id']}, filename={img['filename']}")
        # Check if file actually exists
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], img['filename'])
        exists = os.path.exists(filepath)
        print(f"    File exists on disk: {exists}")
        if exists:
            size = os.path.getsize(filepath)
            print(f"    File size: {size} bytes")
    
    # Also check what's in the entries table
    c.execute("SELECT title, LENGTH(description) as desc_len FROM entries WHERE id=?", (entry_id,))
    entry_info = c.fetchone()
    if entry_info:
        print(f"Entry info - Title: '{entry_info['title']}', Description length: {entry_info['desc_len']}")
    else:
        print(f"No entry found with ID {entry_id}")
    
    conn.close()
    print("=== END DEBUG get_images ===\n")
    return images

def get_all_images(description_html, entry_id):
    """Extract all images from description HTML - DO NOT include separate uploads to avoid duplication"""
    print(f"\n=== DEBUG get_all_images for entry {entry_id} ===")
    print(f"Description HTML: {description_html[:200] if description_html else 'None'}...")
    
    images = []
    
    # Parse HTML to find embedded images using regex
    if description_html:
        # Pattern to match img tags
        img_pattern = r'<img[^>]*src=["\']([^"\']+)["\'][^>]*(?:alt=["\']([^"\']*)["\'])?[^>]*>'
        img_matches = re.findall(img_pattern, description_html, re.IGNORECASE)
        
        print(f"Found {len(img_matches)} embedded images")
        for i, match in enumerate(img_matches):
            src = match[0]
            alt = match[1] if len(match) > 1 and match[1] else f'Food image {i+1}'
            print(f"  Embedded image {i}: src='{src}', alt='{alt}'")
            images.append({
                'src': src,
                'alt': alt,
                'type': 'embedded'
            })
    
    # DO NOT add separate uploaded images here to avoid duplication
    # Since we're processing everything through the rich text editor now,
    # all images should be embedded in the description HTML
    
    print(f"Total images: {len(images)}")
    for i, img in enumerate(images):
        print(f"  Image {i}: {img}")
    
    print("=== END DEBUG ===\n")
    return images

def get_description_without_images(description_html):
    """Remove img tags from description HTML"""
    if not description_html:
        return ""
    
    # Remove all img tags using regex
    description_without_images = re.sub(r'<img[^>]*>', '', description_html, flags=re.IGNORECASE)
    
    # Clean up any empty paragraphs that might be left
    description_without_images = re.sub(r'<p>\s*</p>', '', description_without_images)
    description_without_images = re.sub(r'<p>\s*<br\s*/?>\s*</p>', '', description_without_images)
    
    return description_without_images.strip()

def process_base64_images(html_content, entry_id):
    """Extract base64 images from HTML, save them as files, and replace with file URLs"""
    print(f"\n=== DEBUG process_base64_images for entry {entry_id} ===")
    print(f"Input HTML length: {len(html_content) if html_content else 0}")
    print(f"Input HTML preview: {html_content[:300] if html_content else 'None'}...")
    
    if not html_content:
        print("No HTML content, returning empty string")
        return ""
    
    # Pattern to match base64 images
    base64_pattern = r'<img[^>]*src="data:image/([^;]+);base64,([^"]+)"[^>]*>'
    base64_matches = re.findall(base64_pattern, html_content)
    print(f"Found {len(base64_matches)} base64 images")
    
    # Get database connection for this function
    conn = get_db_connection()
    c = conn.cursor()
    
    def replace_base64(match):
        image_format = match.group(1)
        base64_data = match.group(2)
        
        print(f"Processing base64 image: format={image_format}, data_length={len(base64_data)}")
        
        try:
            # Decode base64 image
            image_data = base64.b64decode(base64_data)
            
            # Generate unique filename
            filename = f"{entry_id}_{uuid.uuid4().hex[:8]}.{image_format}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            print(f"Saving image to: {filepath}")
            
            # Save image file
            with open(filepath, 'wb') as f:
                f.write(image_data)
            
            # Verify file was created
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                print(f"File saved successfully: {filename} ({file_size} bytes)")
            else:
                print(f"ERROR: File not created: {filepath}")
                return ""
            
            # Save to database - use the connection from outer scope
            c.execute("INSERT INTO images (entry_id, filename) VALUES (?, ?)", (entry_id, filename))
            print(f"Database record created for: {filename}")
            
            # Replace base64 with file URL - KEEP the image in HTML
            replacement = f'<img src="/static/uploads/{filename}" alt="Food image" style="max-width: 100%; height: auto; border-radius: 8px; margin: 10px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">'
            print(f"Replacement HTML: {replacement}")
            return replacement
        
        except Exception as e:
            print(f"Error processing base64 image: {e}")
            import traceback
            traceback.print_exc()
            return ""  # Remove problematic images
    
    # Replace all base64 images with file URLs
    processed_html = re.sub(base64_pattern, replace_base64, html_content)
    
    # Commit the database changes for this function
    conn.commit()
    conn.close()
    
    print(f"Processed HTML length: {len(processed_html)}")
    print(f"Processed HTML preview: {processed_html[:300]}...")
    print("=== END DEBUG ===\n")
    
    return processed_html

def cleanup_orphaned_images():
    """Clean up any orphaned image records that shouldn't exist"""
    print("=== Cleaning up orphaned images ===")
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get all image records
    c.execute("SELECT * FROM images")
    all_images = c.fetchall()
    print(f"Total image records in database: {len(all_images)}")
    
    for img in all_images:
        entry_id = img['entry_id']
        filename = img['filename']
        
        # Check if the entry exists
        c.execute("SELECT description FROM entries WHERE id=?", (entry_id,))
        entry = c.fetchone()
        
        if entry:
            description = entry['description']
            # Check if this image filename is referenced in the description HTML
            if filename in description:
                print(f"  Image {filename} is properly referenced in entry {entry_id}")
            else:
                print(f"  Image {filename} is NOT referenced in entry {entry_id} - removing")
                # Delete the orphaned record
                c.execute("DELETE FROM images WHERE id=?", (img['id'],))
                # Try to delete the file too
                try:
                    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    print(f"    Deleted file: {filename}")
                except:
                    print(f"    Could not delete file: {filename}")
        else:
            print(f"  Entry {entry_id} doesn't exist - removing image {filename}")
            c.execute("DELETE FROM images WHERE id=?", (img['id'],))
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                print(f"    Deleted file: {filename}")
            except:
                print(f"    Could not delete file: {filename}")
    
    conn.commit()
    conn.close()
    print("=== Cleanup completed ===")

# Add a route to run the cleanup (you can call this once to clean up)
@app.route('/admin/cleanup', methods=['GET'])
def admin_cleanup():
    cleanup_orphaned_images()
    flash('Database cleanup completed!')
    return redirect(url_for('index'))



# Add template context processors to make functions available in templates
@app.context_processor
def utility_processor():
    return dict(
        get_images=get_images,
        get_all_images=get_all_images,
        get_description_without_images=get_description_without_images
    )

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
    return render_template('index.html', entries=entries)

@app.route('/view/<int:entry_id>')
def view_entry(entry_id):
    """New route for viewing entry details on separate page"""
    print(f"\n=== Viewing entry {entry_id} ===")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM entries WHERE id=?", (entry_id,))
    entry = c.fetchone()
    conn.close()
    
    if not entry:
        flash('Entry not found!')
        return redirect(url_for('index'))
    
    print(f"Entry found: {entry['title']}")
    print(f"Description length: {len(entry['description']) if entry['description'] else 0}")
    
    return render_template('view_entry.html', entry=entry)

@app.route('/add', methods=['GET', 'POST'])
def add_entry():
    if request.method == 'POST':
        title = request.form['title']
        description_raw = request.form['description']
        food_type = request.form['food_type']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        print(f"\n=== Adding new entry ===")
        print(f"Title: {title}")
        print(f"Food type: {food_type}")
        print(f"Raw description length: {len(description_raw) if description_raw else 0}")
        print(f"Raw description preview: {description_raw[:300] if description_raw else 'None'}...")

        # First, create the entry to get the ID
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO entries (title, description, food_type, timestamp) VALUES (?, ?, ?, ?)",
                  (title, "", food_type, timestamp))  # Empty description for now
        entry_id = c.lastrowid
        conn.commit()  # IMPORTANT: Commit here to ensure entry exists
        print(f"Created entry with ID: {entry_id}")
        
        # Process base64 images and update description
        processed_description = process_base64_images(description_raw, entry_id)
        
        # Sanitize the processed HTML
        description = bleach.clean(processed_description, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)
        print(f"Final description length: {len(description)}")
        print(f"Final description preview: {description[:300]}...")
        
        # Update the entry with processed description
        c.execute("UPDATE entries SET description=? WHERE id=?", (description, entry_id))

        # REMOVE THIS SECTION - we don't want to process file uploads separately
        # since images are already processed from the rich text editor
        # 
        # # Handle additional file uploads (if any)
        # for file in request.files.getlist('images'):
        #     if file and file.filename:
        #         filename = secure_filename(file.filename)
        #         # Make filename unique
        #         filename = f"{entry_id}_{uuid.uuid4().hex[:8]}_{filename}"
        #         file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        #         c.execute("INSERT INTO images (entry_id, filename) VALUES (?, ?)", (entry_id, filename))
        #         print(f"Saved additional file upload: {filename}")

        conn.commit()  # Final commit for all changes
        conn.close()

        print("=== Entry creation completed ===\n")
        
        # Debug: Verify data was saved
        verify_conn = get_db_connection()
        verify_c = verify_conn.cursor()
        verify_c.execute("SELECT * FROM entries WHERE id=?", (entry_id,))
        saved_entry = verify_c.fetchone()
        verify_c.execute("SELECT COUNT(*) as count FROM images WHERE entry_id=?", (entry_id,))
        image_count = verify_c.fetchone()
        verify_conn.close()
        
        print(f"Verification - Entry {entry_id}:")
        print(f"  - Title: {saved_entry['title'] if saved_entry else 'NOT FOUND'}")
        print(f"  - Description length: {len(saved_entry['description']) if saved_entry and saved_entry['description'] else 0}")
        print(f"  - Images in DB: {image_count['count'] if image_count else 0}")
        
        flash('Entry added successfully!')
        return redirect(url_for('view_entry', entry_id=entry_id))
    return render_template('add_entry.html')

@app.route('/edit/<int:entry_id>', methods=['GET', 'POST'])
def edit_entry(entry_id):
    conn = get_db_connection()
    c = conn.cursor()

    if request.method == 'POST':
        title = request.form['title']
        description_raw = request.form['description']
        food_type = request.form['food_type']

        # Process base64 images in the updated description
        processed_description = process_base64_images(description_raw, entry_id)
        
        # Sanitize updated description
        description = bleach.clean(processed_description, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)

        c.execute("UPDATE entries SET title=?, description=?, food_type=? WHERE id=?",
                  (title, description, food_type, entry_id))
        conn.commit()
        conn.close()
        flash('Entry updated successfully!')
        return redirect(url_for('view_entry', entry_id=entry_id))  # Redirect to view page

    c.execute("SELECT * FROM entries WHERE id=?", (entry_id,))
    entry = c.fetchone()
    conn.close()
    return render_template('edit_entry.html', entry=entry)

@app.route('/delete/<int:entry_id>', methods=['POST'])
def delete_entry(entry_id):
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get image filenames to delete files
    c.execute("SELECT filename FROM images WHERE entry_id=?", (entry_id,))
    images = c.fetchall()
    
    # Delete image files
    for image in images:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], image['filename']))
        except:
            pass  # File might not exist
    
    # Delete from database
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

@app.route('/api/images/<int:entry_id>')
def get_entry_images(entry_id):
    """API endpoint to get images for a specific entry"""
    images = get_images(entry_id)
    return jsonify([{'filename': img['filename'], 'id': img['id']} for img in images])

if __name__ == '__main__':
    app.run(debug=True)